"""Core logic: turn an audio file + a still image into a video.

The heavy lifting is done by ffmpeg. By default the ffmpeg binary bundled
with the ``imageio-ffmpeg`` package is used, so nothing has to be installed
system-wide. Set the ``AUDIO_TO_VIDEO_FFMPEG`` environment variable to use a
different binary.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff")
OUTPUT_FORMATS = ("mp4", "mkv")

# Bitrate used when audio has to be re-encoded to AAC (MP4 + WAV/FLAC input).
# 320k is the practical maximum for AAC and is transparent for music.
AAC_BITRATE = "320k"

ProgressCallback = Callable[[float], None]


class ConversionError(Exception):
    """Raised when inputs are invalid or ffmpeg fails."""


class ConversionCancelled(ConversionError):
    """Raised when the conversion was cancelled by the user."""


@dataclass
class ConversionOptions:
    """Settings for one conversion.

    Attributes:
        output_format: ``"mp4"`` (plays everywhere) or ``"mkv"`` (audio is
            copied bit-for-bit, including FLAC/WAV).
        max_width: Downscale the image to at most this width (keeps aspect
            ratio). ``None`` keeps the original size. Smaller = faster.
        fps: Frame rate of the output video. A still image needs very few
            frames, so 1 fps keeps encoding extremely fast.
        overwrite: Replace the output file if it already exists.
    """

    output_format: str = "mp4"
    max_width: Optional[int] = 1280
    fps: int = 1
    overwrite: bool = False


def get_ffmpeg_exe() -> str:
    """Return the path to the ffmpeg executable."""
    override = os.environ.get("AUDIO_TO_VIDEO_FFMPEG")
    if override:
        return override
    try:
        import imageio_ffmpeg
    except ImportError as exc:  # pragma: no cover - dependency is required
        raise ConversionError(
            "The imageio-ffmpeg package is missing. Install it: pip install imageio-ffmpeg"
        ) from exc
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except RuntimeError as exc:
        raise ConversionError(f"ffmpeg not found: {exc}") from exc


def _subprocess_flags() -> int:
    # Hide the black console window when running from the windowed .exe.
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return 0


def validate_inputs(audio: Path, image: Path) -> None:
    """Check that both input files exist and have a supported extension."""
    if not audio.is_file():
        raise ConversionError(f"Audio file not found: {audio}")
    if audio.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ConversionError(
            f"Unsupported audio format '{audio.suffix}'. "
            f"Supported: {', '.join(AUDIO_EXTENSIONS)}"
        )
    if not image.is_file():
        raise ConversionError(f"Image not found: {image}")
    if image.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ConversionError(
            f"Unsupported image format '{image.suffix}'. "
            f"Supported: {', '.join(IMAGE_EXTENSIONS)}"
        )


def default_output_path(audio: Path, output_format: str = "mp4") -> Path:
    """Suggest an output path next to the audio file, e.g. ``song.mp4``."""
    return audio.with_suffix("." + output_format)


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


def parse_duration(ffmpeg_output: str) -> Optional[float]:
    """Extract the duration in seconds from ``ffmpeg -i`` output."""
    match = _DURATION_RE.search(ffmpeg_output)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def probe_duration(audio: Path, ffmpeg: Optional[str] = None) -> float:
    """Return the duration of an audio file in seconds."""
    ffmpeg = ffmpeg or get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(audio)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_subprocess_flags(),
    )
    duration = parse_duration(result.stderr)
    if duration is None or duration <= 0:
        raise ConversionError(f"Could not determine the audio duration: {audio}")
    return duration


def scale_filter(max_width: Optional[int]) -> str:
    """Build the ffmpeg scale filter.

    H.264 with yuv420p requires even width and height, so dimensions are
    always rounded down to an even number. Images are never upscaled.
    """
    if max_width is None:
        return "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    if max_width < 2:
        raise ConversionError("Maximum width must be at least 2")
    return f"scale='trunc(min(iw,{int(max_width)})/2)*2':-2"


def build_prepare_command(
    image: Path, prepared: Path, max_width: Optional[int], ffmpeg: str = "ffmpeg"
) -> list[str]:
    """Command that resizes the image once and saves it as a small PNG.

    Looping a pre-scaled PNG is much faster than decoding and scaling a
    large JPEG for every frame. Converting to RGB also normalises unusual
    inputs (CMYK JPEG, full-range "yuvj" JPEG, animated GIF/WebP -> first
    frame) so the final video uses the standard TV colour range.
    """
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(image),
        "-frames:v", "1",
        "-vf", scale_filter(max_width) + ",setsar=1,format=rgb24",
        str(prepared),
    ]


def prepare_image(image: Path, prepared: Path, max_width: Optional[int], ffmpeg: str) -> Path:
    """Resize ``image`` into ``prepared`` (a PNG path) and return it."""
    result = subprocess.run(
        build_prepare_command(image, prepared, max_width, ffmpeg),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        creationflags=_subprocess_flags(),
    )
    if result.returncode != 0 or not prepared.is_file():
        raise ConversionError(f"Could not read the image {image}:\n{result.stderr.strip()}")
    return prepared


def audio_codec_args(audio: Path, output_format: str) -> list[str]:
    """Choose how to store the audio so quality is preserved.

    * MKV: always copy the original stream (bit-exact, any codec).
    * MP4 + MP3 input: copy the MP3 stream (no re-encoding, no loss).
    * MP4 + WAV/FLAC input: encode to AAC 320 kbit/s (MP4 players do not
      reliably support FLAC/PCM). The "fast" AAC coder is about twice as
      quick as the default and at 320 kbit/s the difference is inaudible.
    """
    if output_format == "mkv":
        return ["-c:a", "copy"]
    if audio.suffix.lower() == ".mp3":
        return ["-c:a", "copy"]
    return ["-c:a", "aac", "-aac_coder", "fast", "-b:a", AAC_BITRATE]


def build_command(
    audio: Path,
    image: Path,
    output: Path,
    duration: float,
    options: ConversionOptions,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """Build the ffmpeg command that writes the video.

    ``image`` should already be prepared with :func:`prepare_image` (even
    dimensions, final size); it is not scaled again here.
    """
    if options.output_format not in OUTPUT_FORMATS:
        raise ConversionError(
            f"Unknown format '{options.output_format}'. "
            f"Available: {', '.join(OUTPUT_FORMATS)}"
        )
    if options.fps < 1:
        raise ConversionError("FPS must be at least 1")

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-nostats",
        "-progress", "pipe:1",
        "-y" if options.overwrite else "-n",
        # Input 0: the image, looped at a very low frame rate for as long as
        # the audio lasts. The limit is set on this input (not the output)
        # so a copied audio stream is never cut short.
        "-loop", "1",
        "-framerate", str(options.fps),
        "-t", f"{duration:.3f}",
        "-i", str(image),
        # Input 1: the audio.
        "-i", str(audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-r", str(options.fps),
        *audio_codec_args(audio, options.output_format),
    ]
    if options.output_format == "mp4":
        cmd += ["-movflags", "+faststart"]
    cmd.append(str(output))
    return cmd


def parse_progress_line(line: str) -> Optional[float]:
    """Parse one ``-progress`` line and return elapsed output seconds."""
    key, _, value = line.strip().partition("=")
    # Despite the name, out_time_ms is in microseconds as well.
    if key in ("out_time_us", "out_time_ms"):
        try:
            return int(value) / 1_000_000
        except ValueError:
            return None
    return None


def convert(
    audio: Path | str,
    image: Path | str,
    output: Path | str | None = None,
    options: Optional[ConversionOptions] = None,
    progress: Optional[ProgressCallback] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Path:
    """Create a video from ``audio`` and ``image``.

    Args:
        audio: Path to an MP3/WAV/FLAC file.
        image: Path to the picture shown for the whole video.
        output: Output file. Defaults to the audio path with a new extension.
        options: Conversion settings, see :class:`ConversionOptions`.
        progress: Called with a value from 0.0 to 1.0 while encoding.
        cancel_event: Set this event from another thread to stop the
            conversion; :class:`ConversionCancelled` is raised.

    Returns:
        Path of the created video file.
    """
    options = options or ConversionOptions()
    audio, image = Path(audio), Path(image)
    validate_inputs(audio, image)
    output = Path(output) if output else default_output_path(audio, options.output_format)

    if output.resolve() in (audio.resolve(), image.resolve()):
        raise ConversionError("The output file cannot be one of the input files")
    if output.exists() and not options.overwrite:
        raise ConversionError(f"File already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = get_ffmpeg_exe()
    duration = probe_duration(audio, ffmpeg)
    with tempfile.TemporaryDirectory(prefix="audio_to_video_") as tmp:
        prepared = prepare_image(image, Path(tmp) / "cover.png", options.max_width, ffmpeg)
        if cancel_event is not None and cancel_event.is_set():
            raise ConversionCancelled("Conversion cancelled")
        cmd = build_command(audio, prepared, output, duration, options, ffmpeg)
        _run_ffmpeg(cmd, output, duration, progress, cancel_event)

    if progress is not None:
        progress(1.0)
    return output


def _run_ffmpeg(
    cmd: list[str],
    output: Path,
    duration: float,
    progress: Optional[ProgressCallback],
    cancel_event: Optional[threading.Event],
) -> None:
    """Run the encoding command, reporting progress and honouring cancel."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_subprocess_flags(),
    )

    # Read stderr in the background so the pipe never fills up and blocks.
    stderr_chunks: list[str] = []
    stderr_thread = threading.Thread(
        target=lambda: stderr_chunks.append(process.stderr.read()), daemon=True
    )
    stderr_thread.start()

    cancelled = False
    assert process.stdout is not None
    for line in process.stdout:
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            process.kill()
            break
        seconds = parse_progress_line(line)
        if seconds is not None and progress is not None:
            progress(min(max(seconds / duration, 0.0), 1.0))

    process.wait()
    stderr_thread.join(timeout=5)

    if cancelled:
        output.unlink(missing_ok=True)
        raise ConversionCancelled("Conversion cancelled")
    if process.returncode != 0:
        output.unlink(missing_ok=True)
        details = "".join(stderr_chunks).strip()
        raise ConversionError(f"ffmpeg failed (exit code {process.returncode}):\n{details}")
