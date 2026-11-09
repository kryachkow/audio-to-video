"""Build a standalone AudioToVideo executable with PyInstaller.

Usage:
    pip install -r requirements-dev.txt
    python build_exe.py

The result is ``dist/AudioToVideo.exe`` (Windows) or ``dist/AudioToVideo``
(macOS/Linux). ffmpeg is bundled inside, so the file runs on a PC without
Python or ffmpeg installed.
"""

from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent


def main() -> None:
    PyInstaller.__main__.run(
        [
            str(ROOT / "run_app.py"),
            "--name", "AudioToVideo",
            "--onefile",
            "--windowed",
            "--noconfirm",
            "--clean",
            "--paths", str(ROOT / "src"),
            # Bundle the ffmpeg binary shipped with imageio-ffmpeg.
            "--collect-all", "imageio_ffmpeg",
            "--distpath", str(ROOT / "dist"),
            "--workpath", str(ROOT / "build"),
            "--specpath", str(ROOT / "build"),
        ]
    )


if __name__ == "__main__":
    main()
