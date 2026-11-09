"""Audio to Video: make a video from a music file and a single image."""

from .core import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    OUTPUT_FORMATS,
    ConversionCancelled,
    ConversionError,
    ConversionOptions,
    convert,
)

__version__ = "1.0.0"

__all__ = [
    "AUDIO_EXTENSIONS",
    "IMAGE_EXTENSIONS",
    "OUTPUT_FORMATS",
    "ConversionCancelled",
    "ConversionError",
    "ConversionOptions",
    "convert",
    "__version__",
]
