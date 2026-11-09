"""Unit tests that do not run ffmpeg."""

from pathlib import Path

import pytest

from audio_to_video.core import (
    ConversionError,
    ConversionOptions,
    audio_codec_args,
    build_command,
    build_prepare_command,
    default_output_path,
    parse_duration,
    parse_progress_line,
    scale_filter,
    validate_inputs,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("  Duration: 00:03:21.45, start: 0.000000, bitrate: 320 kb/s", 201.45),
        ("Duration: 01:00:00.00, start", 3600.0),
        ("Duration: 00:00:03.000, start", 3.0),
    ],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == pytest.approx(expected)


def test_parse_duration_missing():
    assert parse_duration("Duration: N/A, bitrate: N/A") is None
    assert parse_duration("") is None


@pytest.mark.parametrize(
    "line, expected",
    [
        ("out_time_us=1500000\n", 1.5),
        ("out_time_ms=2000000", 2.0),
        ("out_time_us=N/A", None),
        ("frame=10", None),
        ("progress=continue", None),
    ],
)
def test_parse_progress_line(line, expected):
    assert parse_progress_line(line) == expected


def test_scale_filter_limits_width_and_keeps_even_size():
    assert scale_filter(1280) == "scale='trunc(min(iw,1280)/2)*2':-2"


def test_scale_filter_original_size():
    assert scale_filter(None) == "scale=trunc(iw/2)*2:trunc(ih/2)*2"


def test_scale_filter_rejects_tiny_width():
    with pytest.raises(ConversionError):
        scale_filter(1)


@pytest.mark.parametrize(
    "audio, fmt, expected",
    [
        ("a.mp3", "mp4", ["-c:a", "copy"]),
        ("a.MP3", "mp4", ["-c:a", "copy"]),
        ("a.wav", "mp4", ["-c:a", "aac", "-aac_coder", "fast", "-b:a", "320k"]),
        ("a.flac", "mp4", ["-c:a", "aac", "-aac_coder", "fast", "-b:a", "320k"]),
        ("a.wav", "mkv", ["-c:a", "copy"]),
        ("a.flac", "mkv", ["-c:a", "copy"]),
        ("a.mp3", "mkv", ["-c:a", "copy"]),
    ],
)
def test_audio_codec_args(audio, fmt, expected):
    assert audio_codec_args(Path(audio), fmt) == expected


def _cmd(**kw):
    opts = ConversionOptions(**kw)
    return build_command(Path("in.flac"), Path("cover.jpg"), Path("out.mp4"), 12.5, opts, "ffmpeg")


def test_build_command_structure():
    cmd = _cmd()
    assert cmd[0] == "ffmpeg"
    assert cmd[-1] == "out.mp4"
    # Duration limits the image input only, so the audio is never truncated.
    assert cmd.count("-t") == 1
    assert cmd[cmd.index("-t") + 1] == "12.500"
    assert cmd.index("-t") < cmd.index("cover.jpg")
    assert cmd[cmd.index("-loop") + 1] == "1"
    # Image is input 0, audio input 1, mapped explicitly.
    inputs = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-i"]
    assert inputs == ["cover.jpg", "in.flac"]
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert "+faststart" in cmd
    # Scaling happens once in the prepare step, not for every frame.
    assert "-vf" not in cmd


def test_build_prepare_command():
    cmd = build_prepare_command(Path("big.jpg"), Path("tmp/cover.png"), 854, "ffmpeg")
    assert cmd[cmd.index("-i") + 1] == "big.jpg"
    assert cmd[-1] == str(Path("tmp/cover.png"))
    assert cmd[cmd.index("-frames:v") + 1] == "1"
    assert cmd[cmd.index("-vf") + 1] == scale_filter(854) + ",setsar=1,format=rgb24"


def test_build_command_overwrite_flag():
    assert "-n" in _cmd() and "-y" not in _cmd()
    assert "-y" in _cmd(overwrite=True)


def test_build_command_mkv_has_no_faststart():
    cmd = build_command(
        Path("in.flac"), Path("c.png"), Path("o.mkv"), 1.0, ConversionOptions(output_format="mkv")
    )
    assert "-movflags" not in cmd
    assert cmd[cmd.index("-c:a") + 1] == "copy"


def test_build_command_rejects_bad_format():
    with pytest.raises(ConversionError):
        _cmd(output_format="avi")


def test_build_command_rejects_bad_fps():
    with pytest.raises(ConversionError):
        _cmd(fps=0)


def test_default_output_path():
    assert default_output_path(Path("music/song.flac")) == Path("music/song.mp4")
    assert default_output_path(Path("song.wav"), "mkv") == Path("song.mkv")


def test_validate_inputs_ok(tmp_path):
    audio, image = tmp_path / "a.mp3", tmp_path / "b.PNG"
    audio.write_bytes(b"x")
    image.write_bytes(b"x")
    validate_inputs(audio, image)


def test_validate_inputs_missing_audio(tmp_path):
    image = tmp_path / "b.png"
    image.write_bytes(b"x")
    with pytest.raises(ConversionError, match="Audio file not found"):
        validate_inputs(tmp_path / "nope.mp3", image)


def test_validate_inputs_bad_audio_extension(tmp_path):
    audio, image = tmp_path / "a.ogg", tmp_path / "b.png"
    audio.write_bytes(b"x")
    image.write_bytes(b"x")
    with pytest.raises(ConversionError, match="audio format"):
        validate_inputs(audio, image)


def test_validate_inputs_bad_image(tmp_path):
    audio, image = tmp_path / "a.wav", tmp_path / "b.txt"
    audio.write_bytes(b"x")
    image.write_bytes(b"x")
    with pytest.raises(ConversionError, match="image format"):
        validate_inputs(audio, image)
    with pytest.raises(ConversionError, match="Image not found"):
        validate_inputs(audio, tmp_path / "missing.png")
