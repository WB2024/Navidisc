"""Track downloader for fetching files from Subsonic API.

This module handles downloading track files with:
- Progress reporting
- Integrity verification
- Resume support (future)
"""

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

import httpx

from navidisc.media.resolver import ResolvedTrack, ResolveMethod

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Error during file download."""

    def __init__(self, message: str, track_id: str | None = None):
        super().__init__(message)
        self.track_id = track_id


class DownloadProgress:
    """Progress information for a download."""

    def __init__(
        self,
        track_id: str,
        filename: str,
        total_bytes: int | None,
        downloaded_bytes: int = 0,
    ):
        self.track_id = track_id
        self.filename = filename
        self.total_bytes = total_bytes
        self.downloaded_bytes = downloaded_bytes

    @property
    def percent(self) -> float | None:
        """Download progress as percentage, or None if size unknown."""
        if self.total_bytes and self.total_bytes > 0:
            return (self.downloaded_bytes / self.total_bytes) * 100
        return None

    @property
    def is_complete(self) -> bool:
        """Whether download is complete."""
        if self.total_bytes:
            return self.downloaded_bytes >= self.total_bytes
        return False


ProgressCallback = Callable[[DownloadProgress], None]


class Downloader:
    """Downloads track files from Subsonic-compatible servers.

    This class handles the actual file downloads, separate from resolution.
    Side effects are isolated here.

    Example:
        downloader = Downloader(download_dir=Path("/tmp/navidisc/downloads"))

        async for progress in downloader.download(resolved_track):
            print(f"Downloaded: {progress.percent:.1f}%")
    """

    def __init__(
        self,
        download_dir: Path,
        chunk_size: int = 8192,
        timeout: float = 60.0,
    ):
        """Initialize the downloader.

        Args:
            download_dir: Directory to save downloaded files.
            chunk_size: Size of download chunks in bytes.
            timeout: HTTP timeout in seconds.
        """
        self.download_dir = download_dir
        self.chunk_size = chunk_size
        self.timeout = timeout
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                follow_redirects=True,
            )
        return self._http_client

    async def download(
        self,
        resolved_track: ResolvedTrack,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        """Download a track file.

        Args:
            resolved_track: Resolved track with download URL.
            progress_callback: Optional callback for progress updates.

        Returns:
            Path to the downloaded file.

        Raises:
            DownloadError: If download fails.
            ValueError: If track doesn't need downloading.
        """
        if resolved_track.method != ResolveMethod.DOWNLOAD:
            raise ValueError(
                f"Track does not need downloading: {resolved_track.track.id}"
            )

        if not resolved_track.download_url:
            raise DownloadError(
                "No download URL available",
                resolved_track.track.id,
            )

        # Ensure download directory exists
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename: "Artist - Album - Title.ext"
        track = resolved_track.track
        extension = track.format or "mp3"
        safe_title = self._sanitize_filename(track.title)
        safe_artist = self._sanitize_filename(track.artist)
        safe_album = self._sanitize_filename(track.album or "Unknown Album")
        filename = f"{safe_artist} - {safe_album} - {safe_title}.{extension}"
        output_path = self.download_dir / filename

        # Skip if file already exists (same track already downloaded)
        if output_path.exists():
            logger.debug(f"Skipping download, file exists: {output_path}")
            return output_path

        # Download the file
        client = await self._get_client()
        logger.debug(f"Starting download: {track.title} -> {output_path}")

        try:
            async with client.stream("GET", resolved_track.download_url) as response:
                response.raise_for_status()

                # Get total size from headers if available
                total_size = response.headers.get("content-length")
                total_bytes = int(total_size) if total_size else resolved_track.size_bytes

                progress = DownloadProgress(
                    track_id=track.id,
                    filename=filename,
                    total_bytes=total_bytes,
                )

                # Write to file
                with open(output_path, "wb") as f:
                    async for chunk in response.aiter_bytes(self.chunk_size):
                        f.write(chunk)
                        progress.downloaded_bytes += len(chunk)

                        if progress_callback:
                            try:
                                progress_callback(progress)
                            except Exception:
                                # Don't let progress callback errors kill the download
                                pass

        except httpx.HTTPStatusError as e:
            raise DownloadError(
                f"HTTP error {e.response.status_code}: {e.response.reason_phrase}",
                track.id,
            )
        except httpx.RequestError as e:
            raise DownloadError(f"Request failed: {e}", track.id)
        except httpx.StreamError as e:
            # Streaming errors (e.g., connection closed mid-download)
            raise DownloadError(f"Stream error during download: {e}", track.id)
        except OSError as e:
            raise DownloadError(f"Failed to write file: {e}", track.id)
        except GeneratorExit:
            # HTTP client was closed during streaming - this typically means
            # an error occurred elsewhere and cleanup is in progress
            logger.warning(f"Download interrupted by client closure: {track.id}")
            raise DownloadError(
                "Download interrupted: connection was closed",
                track.id,
            )
        except Exception as e:
            # Log unexpected errors for debugging before converting to DownloadError
            logger.exception(f"Unexpected error downloading track {track.id}: {e}")
            raise DownloadError(f"Unexpected download error: {e}", track.id)

        logger.debug(f"Download complete: {track.title} ({output_path.stat().st_size} bytes)")
        return output_path

    async def download_many(
        self,
        resolved_tracks: list[ResolvedTrack],
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Path]:
        """Download multiple track files.

        Args:
            resolved_tracks: List of resolved tracks to download.
            progress_callback: Optional callback for progress updates.

        Returns:
            Dictionary mapping track IDs to downloaded file paths.
        """
        results = {}

        for rt in resolved_tracks:
            if rt.method == ResolveMethod.DOWNLOAD:
                path = await self.download(rt, progress_callback)
                results[rt.track.id] = path
            elif rt.method == ResolveMethod.LOCAL and rt.local_path:
                results[rt.track.id] = rt.local_path

        return results

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use in filenames.

        Args:
            name: Original name string.

        Returns:
            Sanitized filename-safe string.
        """
        # Remove or replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        result = name
        for char in invalid_chars:
            result = result.replace(char, "_")

        # Collapse multiple underscores/spaces
        while "__" in result:
            result = result.replace("__", "_")
        while "  " in result:
            result = result.replace("  ", " ")

        # Trim whitespace and underscores from ends
        result = result.strip(" _")

        # Limit length
        if len(result) > 200:
            result = result[:200]

        return result or "unknown"

    async def verify_file(
        self,
        path: Path,
        expected_size: int | None = None,
        expected_hash: str | None = None,
    ) -> bool:
        """Verify a downloaded file's integrity.

        Args:
            path: Path to the file.
            expected_size: Expected file size in bytes.
            expected_hash: Expected MD5 hash (optional).

        Returns:
            True if verification passes.
        """
        if not path.exists():
            return False

        actual_size = path.stat().st_size

        if expected_size is not None and actual_size != expected_size:
            return False

        if expected_hash is not None:
            md5 = hashlib.md5()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    md5.update(chunk)
            if md5.hexdigest() != expected_hash.lower():
                return False

        return True

    async def close(self) -> None:
        """Close the HTTP client and clean up resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
