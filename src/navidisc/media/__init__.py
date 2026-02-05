"""Media handling module for Navidisc.

Provides track resolution and downloading functionality.
"""

from navidisc.media.downloader import Downloader
from navidisc.media.resolver import MediaResolver, ResolvedTrack

__all__ = [
    "MediaResolver",
    "ResolvedTrack",
    "Downloader",
]
