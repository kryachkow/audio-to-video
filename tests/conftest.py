import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audio_to_video.core import get_ffmpeg_exe  # noqa: E402

AUDIO_SECONDS = 3


@pytest.fixture(scope="session")
def ffmpeg() -> str:
    return get_ffmpeg_exe()


def _run(ffmpeg: str, *args: str) -> None:
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def media(tmp_path_factory, ffmpeg) -> dict:
    """Generate small test files with ffmpeg: a sine tone and images."""
    d = tmp_path_factory.mktemp("media")
    tone = ["-f", "lavfi", "-i", f"sine=frequency=440:duration={AUDIO_SECONDS}:sample_rate=44100"]
    files = {
        "wav": d / "tone.wav",
        "flac": d / "tone.flac",
        "mp3": d / "tone.mp3",
        "png": d / "cover.png",
        "jpg_odd": d / "odd size.jpg",  # odd dimensions + space in name
        "big_png": d / "big.png",
    }
    _run(ffmpeg, *tone, str(files["wav"]))
    _run(ffmpeg, *tone, str(files["flac"]))
    _run(ffmpeg, *tone, "-c:a", "libmp3lame", "-b:a", "192k", str(files["mp3"]))
    _run(ffmpeg, "-f", "lavfi", "-i", "testsrc=size=640x480", "-frames:v", "1", str(files["png"]))
    _run(ffmpeg, "-f", "lavfi", "-i", "color=c=red:size=333x211", "-frames:v", "1", str(files["jpg_odd"]))
    _run(ffmpeg, "-f", "lavfi", "-i", "testsrc=size=3000x2000", "-frames:v", "1", str(files["big_png"]))
    return files
