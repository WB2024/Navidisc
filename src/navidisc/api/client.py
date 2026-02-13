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

import httpx

from navidisc.api.exceptions import (
    AlbumNotFoundError,
    APIError,
    AuthenticationError,
    ConnectionError,
    PlaylistNotFoundError,
    SubsonicError,
)
from navidisc.models import Album, Playlist, Track


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
        self._navidrome_token: str | None = None  # Cached JWT token for native API

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

    async def _get_navidrome_token(self) -> str | None:
        """Get a JWT token from Navidrome's native API.
        
        Navidrome's native API uses JWT tokens for authentication,
        obtained by POSTing to /auth/login. Token is cached for reuse.
        
        Returns:
            JWT token string, or None if auth fails.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Return cached token if available
        if self._navidrome_token:
            return self._navidrome_token
        
        try:
            client = await self._get_client()
            
            url = f"{self.base_url}/auth/login"
            payload = {
                "username": self.username,
                "password": self.password,
            }
            
            logger.info(f"Getting Navidrome JWT token from {url}")
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                token = data.get("token")
                if token:
                    logger.info("Successfully obtained Navidrome JWT token")
                    self._navidrome_token = token  # Cache for reuse
                    return token
                else:
                    logger.warning(f"No token in response: {data}")
            else:
                logger.warning(f"Navidrome auth failed: {response.status_code} - {response.text[:200]}")
                
        except Exception as e:
            logger.error(f"Failed to get Navidrome token: {e}")
            
        return None

    async def _fetch_navidrome_song_path(self, song_id: str) -> str | None:
        """Fetch the real file path from Navidrome's native API.
        
        Navidrome has a native REST API at /api/inspect that returns the actual
        filesystem path, unlike the Subsonic API which returns a simulated path
        based on metadata (Artist/Album/Track format).
        
        Args:
            song_id: The song/track ID.
            
        Returns:
            The actual file path, or None if not available.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            client = await self._get_client()
            
            # Get JWT token for Navidrome's native API
            token = await self._get_navidrome_token()
            if not token:
                logger.warning("Could not get Navidrome token, cannot fetch real file path")
                return None
            
            # Use the /api/inspect endpoint with id as query param
            url = f"{self.base_url}/api/inspect"
            headers = {"x-nd-authorization": f"Bearer {token}"}
            params = {"id": song_id}
            
            logger.info(f"Calling Navidrome API: {url}?id={song_id}")
            response = await client.get(url, headers=headers, params=params)
            logger.info(f"Navidrome API response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                # The file path is in the "file" field
                real_path = data.get("file")
                logger.info(f"Navidrome API returned file: {real_path}")
                if real_path:
                    return real_path
            else:
                logger.warning(f"Navidrome API returned {response.status_code} for song {song_id}: {response.text[:200]}")
                
        except Exception as e:
            logger.error(f"Failed to fetch path from Navidrome API: {e}")
            
        return None

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
        import logging
        logger = logging.getLogger(__name__)
        
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
        
        # Try to fetch real file paths from Navidrome's native API
        # This is necessary because the Subsonic API returns a logical path, not the real filesystem path
        logger.info(f"=== Fetching real file paths for {len(tracks)} tracks from Navidrome API ===")
        
        for track in tracks:
            real_path = await self._fetch_navidrome_song_path(track.id)
            if real_path:
                logger.info(f"Track '{track.title}': path updated '{track.path}' -> '{real_path}'")
                track.path = real_path
            else:
                logger.warning(f"Track '{track.title}': NO PATH from Navidrome API, keeping '{track.path}'")
        
        logger.info(f"=== Finished fetching paths ===")

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

    async def get_albums(
        self,
        type: str = "alphabeticalByName",
        size: int = 500,
        offset: int = 0,
    ) -> list[Album]:
        """Get albums from the server.

        Args:
            type: Sort order. Options: 'alphabeticalByName', 'alphabeticalByArtist',
                  'recent', 'newest', 'frequent', 'random', 'starred', 'byYear', 'byGenre'.
            size: Maximum number of albums to return.
            offset: Offset for paging.

        Returns:
            List of Album objects (without full track details).
        """
        response = await self._request("getAlbumList2", {
            "type": type,
            "size": size,
            "offset": offset,
        })
        albums_data = response.get("albumList2", {}).get("album", [])

        # Handle single album (not returned as list)
        if isinstance(albums_data, dict):
            albums_data = [albums_data]

        albums = []
        for a in albums_data:
            albums.append(Album(
                id=str(a.get("id")),
                name=a.get("name", a.get("title", "")),
                artist=a.get("artist"),
                artist_id=a.get("artistId"),
                year=a.get("year"),
                genre=a.get("genre"),
                track_count=a.get("songCount", 0),
                duration_seconds=a.get("duration", 0),
                cover_art=a.get("coverArt"),
            ))

        return albums

    async def get_album(self, album_id: str) -> Album:
        """Get an album with full track details.

        Args:
            album_id: ID of the album to retrieve.

        Returns:
            Album with tracks populated.

        Raises:
            AlbumNotFoundError: If album doesn't exist.
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            response = await self._request("getAlbum", {"id": album_id})
        except APIError as e:
            if e.code == 70:  # Data not found
                raise AlbumNotFoundError(album_id)
            raise

        album_data = response.get("album", {})
        tracks_data = album_data.get("song", [])

        # Handle single track (not returned as list)
        if isinstance(tracks_data, dict):
            tracks_data = [tracks_data]

        tracks = [self._parse_track(t) for t in tracks_data]

        # Try to fetch real file paths from Navidrome's native API
        logger.info(f"=== Fetching real file paths for {len(tracks)} tracks from Navidrome API ===")

        for track in tracks:
            real_path = await self._fetch_navidrome_song_path(track.id)
            if real_path:
                logger.info(f"Track '{track.title}': path updated '{track.path}' -> '{real_path}'")
                track.path = real_path
            else:
                logger.warning(f"Track '{track.title}': NO PATH from Navidrome API, keeping '{track.path}'")

        logger.info(f"=== Finished fetching paths ===")

        return Album(
            id=str(album_data.get("id")),
            name=album_data.get("name", album_data.get("title", "")),
            artist=album_data.get("artist"),
            artist_id=album_data.get("artistId"),
            year=album_data.get("year"),
            genre=album_data.get("genre"),
            track_count=album_data.get("songCount", 0),
            duration_seconds=album_data.get("duration", 0),
            cover_art=album_data.get("coverArt"),
            tracks=tracks,
        )

    def _parse_track(self, data: dict[str, Any]) -> Track:
        """Parse track data from API response.

        Args:
            data: Track data from Subsonic API.

        Returns:
            Track model instance.
        """
        # Log full track data for debugging path issues
        track_id = str(data.get("id"))
        title = data.get("title", "Unknown")
        path = data.get("path")
        
        # Log all keys and path-related fields for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Track '{title}' raw data keys: {list(data.keys())}")
        logger.debug(f"Track '{title}' path field: {path}")
        
        # Log any field that might contain path info
        for key in ['path', 'file', 'filePath', 'mediaFile', 'fullPath']:
            if key in data:
                logger.info(f"Track '{title}' {key}: {data[key]}")
        
        # Log duration specifically for debugging size estimation issues
        raw_duration = data.get("duration", 0)
        raw_size = data.get("size", 0)
        logger.debug(
            f"Track '{title}': API duration={raw_duration}s ({raw_duration // 60}m {raw_duration % 60}s), "
            f"size={raw_size} bytes, bitrate={data.get('bitRate')}kbps, format={data.get('suffix')}"
        )
        
        # Sanity check: if duration seems unreasonable (> 1 hour), log a warning
        if raw_duration > 3600:
            logger.warning(
                f"Track '{title}' has unusually long duration: {raw_duration}s ({raw_duration / 60:.1f} min). "
                "This may indicate corrupted metadata."
            )
        
        return Track(
            id=track_id,
            title=title,
            artist=data.get("artist", "Unknown Artist"),
            album=data.get("album"),
            track_number=data.get("track"),
            duration_seconds=raw_duration,
            bitrate=data.get("bitRate"),
            size_bytes=raw_size,
            format=data.get("suffix"),
            path=path,
            stream_url=self._build_stream_url(track_id),
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
