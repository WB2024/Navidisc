"""Media handling module for Navidisc.

Provides track resolution and downloading functionality.
"""

from navidisc.media.resolver import MediaResolver, ResolvedTrack
from navidisc.media.downloader import Downloader

__all__ = [
    "MediaResolver",
    "ResolvedTrack",
    "Downloader",
]
