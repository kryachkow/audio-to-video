"""Launcher used by PyInstaller to build the standalone .exe."""

import sys

from audio_to_video.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
