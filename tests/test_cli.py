import os
import subprocess
import sys
from pathlib import Path

import pytest

from audio_to_video.cli import build_parser, main


def test_parser_defaults():
    args = build_parser().parse_args(["a.mp3", "b.png"])
    assert args.format == "mp4"
    assert args.max_width == 1280
    assert args.fps == 1
    assert not args.overwrite


def test_cli_error_for_missing_file(tmp_path, capsys):
    code = main([str(tmp_path / "missing.mp3"), str(tmp_path / "x.png"), "-q"])
    assert code == 1
    assert "Audio file not found" in capsys.readouterr().err


@pytest.mark.integration
def test_cli_converts(media, tmp_path, capsys):
    out = tmp_path / "cli.mkv"
    code = main([str(media["flac"]), str(media["png"]), "-o", str(out), "-f", "mkv", "-w", "0"])
    assert code == 0
    assert out.is_file()
    assert "Done" in capsys.readouterr().out


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "1.0.0" in capsys.readouterr().out


def test_cli_does_not_crash_on_legacy_console_encoding(tmp_path):
    # Simulate output redirected to a cp1252 pipe (default on many Windows PCs).
    src = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONPATH=src)
    result = subprocess.run(
        [sys.executable, "-m", "audio_to_video", str(tmp_path / "音楽.mp3"), str(tmp_path / "x.png")],
        capture_output=True,
        env=env,
    )
    assert result.returncode == 1
    assert b"Traceback" not in result.stderr
    assert "音楽.mp3" in result.stderr.decode("utf-8")
