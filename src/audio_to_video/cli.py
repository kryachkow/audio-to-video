"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import __version__
from .core import OUTPUT_FORMATS, ConversionError, ConversionOptions, convert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audio-to-video",
        description="Make a video from an audio file (mp3/wav/flac) and an image.",
    )
    parser.add_argument("audio", help="audio file: .mp3, .wav or .flac")
    parser.add_argument("image", help="image shown for the whole video")
    parser.add_argument(
        "-o", "--output",
        help="output file (default: next to the audio, same name)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=OUTPUT_FORMATS,
        default="mp4",
        help="mp4 plays everywhere; mkv keeps the audio unchanged (default: mp4)",
    )
    parser.add_argument(
        "-w", "--max-width",
        type=int,
        default=1280,
        help="downscale the image to this width; 0 = original size (default: 1280)",
    )
    parser.add_argument("--fps", type=int, default=1, help="frames per second (default: 1)")
    parser.add_argument("-y", "--overwrite", action="store_true", help="overwrite the output file")
    parser.add_argument("-q", "--quiet", action="store_true", help="do not show progress")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _print_progress(fraction: float) -> None:
    filled = int(fraction * 30)
    bar = "#" * filled + "-" * (30 - filled)
    print(f"\r[{bar}] {fraction * 100:5.1f}%", end="", flush=True)


def _ensure_utf8_output() -> None:
    """Avoid UnicodeEncodeError when output is redirected on Windows.

    Interactive consoles handle Unicode already; pipes and files default to
    the legacy code page (e.g. cp1252), which cannot encode most non-ASCII text.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _ensure_utf8_output()
    args = build_parser().parse_args(argv)
    options = ConversionOptions(
        output_format=args.format,
        max_width=args.max_width or None,
        fps=args.fps,
        overwrite=args.overwrite,
    )
    try:
        result = convert(
            args.audio,
            args.image,
            args.output,
            options,
            progress=None if args.quiet else _print_progress,
        )
    except ConversionError as exc:
        if not args.quiet:
            print()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    if not args.quiet:
        print()
    print(f"Done: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
