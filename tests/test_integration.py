"""End-to-end tests that run the real (bundled) ffmpeg."""

import subprocess
import threading

import pytest

from audio_to_video.core import (
    ConversionCancelled,
    ConversionError,
    ConversionOptions,
    convert,
    probe_duration,
)

from .conftest import AUDIO_SECONDS

pytestmark = pytest.mark.integration


def streams(ffmpeg, path) -> str:
    """Return the stream description printed by ``ffmpeg -i``."""
    out = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True, errors="replace"
    )
    return out.stderr


def decoded_audio(ffmpeg, path) -> bytes:
    """Decode the audio track to raw PCM for bit-exact comparison."""
    out = subprocess.run(
        [ffmpeg, "-loglevel", "error", "-i", str(path), "-map", "0:a:0", "-f", "s16le", "-"],
        capture_output=True,
        check=True,
    )
    return out.stdout


def test_probe_duration(media, ffmpeg):
    for key in ("wav", "flac", "mp3"):
        assert probe_duration(media[key], ffmpeg) == pytest.approx(AUDIO_SECONDS, abs=0.1)


@pytest.mark.parametrize("audio_key", ["wav", "flac", "mp3"])
def test_convert_mp4(media, ffmpeg, tmp_path, audio_key):
    progress = []
    out = convert(media[audio_key], media["png"], tmp_path / "out.mp4", progress=progress.append)

    assert out.is_file() and out.stat().st_size > 0
    info = streams(ffmpeg, out)
    assert "Video: h264" in info
    assert "Audio:" in info
    assert probe_duration(out, ffmpeg) == pytest.approx(AUDIO_SECONDS, abs=0.5)
    assert progress and progress[-1] == 1.0
    assert all(0.0 <= p <= 1.0 for p in progress)


def test_mp4_from_mp3_keeps_audio_bit_exact(media, ffmpeg, tmp_path):
    out = convert(media["mp3"], media["png"], tmp_path / "out.mp4")
    assert "Audio: mp3" in streams(ffmpeg, out)
    assert decoded_audio(ffmpeg, out) == decoded_audio(ffmpeg, media["mp3"])


def test_mp4_from_wav_uses_aac(media, ffmpeg, tmp_path):
    out = convert(media["wav"], media["png"], tmp_path / "out.mp4")
    assert "Audio: aac" in streams(ffmpeg, out)


@pytest.mark.parametrize("audio_key", ["wav", "flac"])
def test_mkv_keeps_lossless_audio_bit_exact(media, ffmpeg, tmp_path, audio_key):
    out = convert(
        media[audio_key], media["png"], tmp_path / "out.mkv", ConversionOptions(output_format="mkv")
    )
    assert decoded_audio(ffmpeg, out) == decoded_audio(ffmpeg, media[audio_key])


def test_odd_image_size_and_spaces_in_path(media, ffmpeg, tmp_path):
    out = convert(media["wav"], media["jpg_odd"], tmp_path / "my video.mp4")
    assert "332x210" in streams(ffmpeg, out)


def test_unicode_paths(media, ffmpeg, tmp_path):
    audio = tmp_path / "café ünïcode 音楽.wav"
    audio.write_bytes(media["wav"].read_bytes())
    out = convert(audio, media["png"], tmp_path / "vidéo 動画.mp4")
    assert out.is_file()


def test_jpeg_cover_uses_standard_color_range(media, ffmpeg, tmp_path):
    out = convert(media["wav"], media["jpg_odd"], tmp_path / "o.mp4")
    info = streams(ffmpeg, out)
    assert "yuv420p" in info
    assert "(pc" not in info
    assert "SAR 1:1" in info
    assert "yuvj420p" not in info


def test_broken_image_file(media, tmp_path):
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(ConversionError, match="Could not read the image"):
        convert(media["wav"], bad, tmp_path / "o.mp4")
    assert not (tmp_path / "o.mp4").exists()


def test_big_image_is_downscaled(media, ffmpeg, tmp_path):
    out = convert(media["wav"], media["big_png"], tmp_path / "o.mp4", ConversionOptions(max_width=854))
    assert "854x570" in streams(ffmpeg, out)


def test_original_size_kept(media, ffmpeg, tmp_path):
    out = convert(media["wav"], media["png"], tmp_path / "o.mp4", ConversionOptions(max_width=None))
    assert "640x480" in streams(ffmpeg, out)


def test_small_image_is_not_upscaled(media, ffmpeg, tmp_path):
    out = convert(media["wav"], media["png"], tmp_path / "o.mp4", ConversionOptions(max_width=1920))
    assert "640x480" in streams(ffmpeg, out)


def test_default_output_next_to_audio(media, tmp_path):
    audio = tmp_path / "song.flac"
    audio.write_bytes(media["flac"].read_bytes())
    out = convert(audio, media["png"])
    assert out == tmp_path / "song.mp4"
    assert out.is_file()


def test_refuses_to_overwrite(media, tmp_path):
    target = tmp_path / "exists.mp4"
    target.write_bytes(b"keep me")
    with pytest.raises(ConversionError, match="already exists"):
        convert(media["wav"], media["png"], target)
    assert target.read_bytes() == b"keep me"


def test_overwrite(media, tmp_path):
    target = tmp_path / "exists.mp4"
    target.write_bytes(b"old")
    convert(media["wav"], media["png"], target, ConversionOptions(overwrite=True))
    assert target.stat().st_size > 100


def test_output_equal_to_input_rejected(media):
    with pytest.raises(ConversionError, match="cannot be one of the input"):
        convert(media["wav"], media["png"], media["wav"], ConversionOptions(overwrite=True))


def test_broken_audio_file(media, tmp_path):
    bad = tmp_path / "broken.mp3"
    bad.write_bytes(b"this is not audio")
    with pytest.raises(ConversionError):
        convert(bad, media["png"], tmp_path / "o.mp4")
    assert not (tmp_path / "o.mp4").exists()


def test_cancel_removes_partial_file(media, tmp_path):
    cancel = threading.Event()
    cancel.set()
    out = tmp_path / "cancelled.mp4"
    with pytest.raises(ConversionCancelled):
        convert(media["wav"], media["png"], out, cancel_event=cancel)
    assert not out.exists()
