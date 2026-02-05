"""Media handling module for Navidisc.

Provides track resolution, downloading, and conversion functionality.
"""

from navidisc.media.converter import (
    AudioConverter,
    ConversionError,
    ConversionProgress,
    check_ffmpeg_available,
    get_quality_description,
)
from navidisc.media.downloader import Downloader
from navidisc.media.resolver import MediaResolver, ResolvedTrack

__all__ = [
    "AudioConverter",
    "ConversionError",
    "ConversionProgress",
    "check_ffmpeg_available",
    "get_quality_description",
    "Downloader",
    "MediaResolver",
    "ResolvedTrack",
]
