"""Entry point: ``python -m audio_to_video``.

Without arguments the graphical interface opens; with arguments the
command-line interface is used.
"""

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from .cli import main as cli_main

        return cli_main()
    from .gui import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
