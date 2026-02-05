"""Subsonic API client for Navidisc.

Provides authentication and data retrieval from Navidrome
and other Subsonic-compatible servers.
"""

from navidisc.api.client import SubsonicClient
from navidisc.api.exceptions import (
    SubsonicError,
    AuthenticationError,
    PlaylistNotFoundError,
    ConnectionError,
)

__all__ = [
    "SubsonicClient",
    "SubsonicError",
    "AuthenticationError",
    "PlaylistNotFoundError",
    "ConnectionError",
]
