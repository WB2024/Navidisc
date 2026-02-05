"""Subsonic API client implementation.

This client handles:
- Authentication (password and token-based)
- Playlist retrieval
- Track metadata resolution
- Stream URL generation
"""

import hashlib
import secrets
from typing import Any
from urllib.parse import urljoin

import httpx

from navidisc.api.exceptions import (
    APIError,
    AuthenticationError,
    ConnectionError,
    PlaylistNotFoundError,
    SubsonicError,
)
from navidisc.models import Album, Artist, Playlist, Track


class SubsonicClient:
    """Client for interacting with Subsonic-compatible APIs (including Navidrome).
    
    This client uses token-based authentication (salt + token) which is the
    recommended method for Subsonic API 1.13.0+.
    
    Example:
        client = SubsonicClient(
            base_url="http://localhost:4533",
            username="admin",
            password="password"
        )
        await client.authenticate()
        playlists = await client.get_playlists()
    """
    
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        api_version: str = "1.16.1",
        client_name: str = "navidisc",
    ):
        """Initialize the Subsonic client.
        
        Args:
            base_url: Base URL of the Subsonic server (e.g., http://localhost:4533)
            username: Username for authentication
            password: Password for authentication
            api_version: Subsonic API version to use
            client_name: Client identifier sent with requests
        """
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.api_version = api_version
        self.client_name = client_name
        self._authenticated = False
        self._http_client: httpx.AsyncClient | None = None
    
    @property
    def is_authenticated(self) -> bool:
        """Whether the client has successfully authenticated."""
        return self._authenticated
    
    def _generate_auth_params(self) -> dict[str, str]:
        """Generate authentication parameters using token method.
        
        Returns:
            Dictionary with authentication parameters.
        """
        salt = secrets.token_hex(8)
        token = hashlib.md5((self.password + salt).encode()).hexdigest()
        
        return {
            "u": self.username,
            "t": token,
            "s": salt,
            "v": self.api_version,
            "c": self.client_name,
            "f": "json",
        }
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client
    
    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the Subsonic API.
        
        Args:
            endpoint: API endpoint (e.g., "getPlaylists")
            params: Additional query parameters
            
        Returns:
            Response data from the API.
            
        Raises:
            ConnectionError: If unable to connect to server
            AuthenticationError: If authentication fails
            APIError: If the API returns an error
        """
        url = f"{self.base_url}/rest/{endpoint}"
        
        request_params = self._generate_auth_params()
        if params:
            request_params.update(params)
        
        try:
            client = await self._get_client()
            response = await client.get(url, params=request_params)
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(f"Could not connect to {self.base_url}: {e}")
        except httpx.HTTPStatusError as e:
            raise SubsonicError(f"HTTP error: {e.response.status_code}")
        
        try:
            data = response.json()
        except ValueError:
            raise SubsonicError("Invalid JSON response from server")
        
        # Subsonic wraps responses in "subsonic-response"
        subsonic_response = data.get("subsonic-response", {})
        
        if subsonic_response.get("status") == "failed":
            error = subsonic_response.get("error", {})
            code = error.get("code", 0)
            message = error.get("message", "Unknown error")
            
            if code == 40:
                raise AuthenticationError(message, code)
            raise APIError(message, code)
        
        return subsonic_response
    
    async def authenticate(self) -> bool:
        """Test authentication with the server.
        
        Returns:
            True if authentication successful.
            
        Raises:
            AuthenticationError: If authentication fails.
            ConnectionError: If unable to connect.
        """
        # ping endpoint is the simplest way to test auth
        await self._request("ping")
        self._authenticated = True
        return True
    
    async def get_playlists(self) -> list[Playlist]:
        """Get all playlists accessible to the user.
        
        Returns:
            List of Playlist objects (without full track details).
        """
        response = await self._request("getPlaylists")
        playlists_data = response.get("playlists", {}).get("playlist", [])
        
        # Handle single playlist (not returned as list)
        if isinstance(playlists_data, dict):
            playlists_data = [playlists_data]
        
        playlists = []
        for p in playlists_data:
            playlists.append(Playlist(
                id=str(p.get("id")),
                name=p.get("name", ""),
                track_count=p.get("songCount", 0),
                duration_seconds=p.get("duration", 0),
                owner=p.get("owner"),
                public=p.get("public", False),
            ))
        
        return playlists
    
    async def get_playlist(self, playlist_id: str) -> Playlist:
        """Get a playlist with full track details.
        
        Args:
            playlist_id: ID of the playlist to retrieve.
            
        Returns:
            Playlist with tracks populated.
            
        Raises:
            PlaylistNotFoundError: If playlist doesn't exist.
        """
        try:
            response = await self._request("getPlaylist", {"id": playlist_id})
        except APIError as e:
            if e.code == 70:  # Data not found
                raise PlaylistNotFoundError(playlist_id)
            raise
        
        playlist_data = response.get("playlist", {})
        tracks_data = playlist_data.get("entry", [])
        
        # Handle single track (not returned as list)
        if isinstance(tracks_data, dict):
            tracks_data = [tracks_data]
        
        tracks = [self._parse_track(t) for t in tracks_data]
        
        return Playlist(
            id=str(playlist_data.get("id")),
            name=playlist_data.get("name", ""),
            track_count=playlist_data.get("songCount", 0),
            duration_seconds=playlist_data.get("duration", 0),
            owner=playlist_data.get("owner"),
            public=playlist_data.get("public", False),
            tracks=tracks,
        )
    
    async def get_playlist_by_name(self, name: str) -> Playlist:
        """Get a playlist by name with full track details.
        
        Args:
            name: Name of the playlist (case-insensitive).
            
        Returns:
            Playlist with tracks populated.
            
        Raises:
            PlaylistNotFoundError: If no playlist with that name exists.
        """
        playlists = await self.get_playlists()
        
        # Find playlist by name (case-insensitive)
        for playlist in playlists:
            if playlist.name.lower() == name.lower():
                return await self.get_playlist(playlist.id)
        
        raise PlaylistNotFoundError(name)
    
    def _parse_track(self, data: dict[str, Any]) -> Track:
        """Parse track data from API response.
        
        Args:
            data: Track data from Subsonic API.
            
        Returns:
            Track model instance.
        """
        return Track(
            id=str(data.get("id")),
            title=data.get("title", "Unknown"),
            artist=data.get("artist", "Unknown Artist"),
            album=data.get("album"),
            track_number=data.get("track"),
            duration_seconds=data.get("duration", 0),
            bitrate=data.get("bitRate"),
            size_bytes=data.get("size"),
            format=data.get("suffix"),
            path=data.get("path"),
            stream_url=self._build_stream_url(str(data.get("id"))),
        )
    
    def _build_stream_url(self, track_id: str) -> str:
        """Build a stream/download URL for a track.
        
        Args:
            track_id: ID of the track.
            
        Returns:
            Full URL that can be used to download the track.
        """
        params = self._generate_auth_params()
        params["id"] = track_id
        
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.base_url}/rest/download?{query}"
    
    def get_download_url(self, track_id: str) -> str:
        """Get a download URL for a track.
        
        Public method for getting track download URLs.
        
        Args:
            track_id: ID of the track.
            
        Returns:
            Full URL for downloading the track.
        """
        return self._build_stream_url(track_id)
    
    async def close(self) -> None:
        """Close the HTTP client and clean up resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._authenticated = False
    
    async def __aenter__(self) -> "SubsonicClient":
        """Async context manager entry."""
        await self.authenticate()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
