"""Track resolution for determining how to obtain track files.

This module determines the best way to obtain each track:
1. Local filesystem path (if Navidrome library is accessible)
2. Remote download via Subsonic API
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from navidisc.models import DownloadMode, Track

logger = logging.getLogger(__name__)


class ResolveMethod(StrEnum):
    """How a track file was/will be obtained."""
    LOCAL = "local"
    DOWNLOAD = "download"
    NOT_FOUND = "not_found"


@dataclass
class ResolvedTrack:
    """A track with its resolved file location.

    This is a pure data class representing the resolution result
    for a single track, designed to be deterministic and serializable.
    """
    track: Track
    method: ResolveMethod
    local_path: Path | None = None
    download_url: str | None = None
    size_bytes: int | None = None
    verified: bool = False
    error: str | None = None

    @property
    def is_available(self) -> bool:
        """Whether the track file is available (local or downloadable)."""
        return self.method in (ResolveMethod.LOCAL, ResolveMethod.DOWNLOAD)


class MediaResolver:
    """Resolves tracks to their file locations.

    This class is responsible for determining how to obtain each track
    based on the configured download mode and available sources.

    The resolver is designed to be:
    - Deterministic: same inputs produce same outputs
    - Pure: no side effects during resolution
    - Serializable: results can be saved and restored

    Example:
        resolver = MediaResolver(
            library_paths=[Path("/music")],
            download_mode=DownloadMode.DOWNLOAD_IF_MISSING
        )
        resolved = resolver.resolve(track, download_url)
    """

    def __init__(
        self,
        library_paths: list[Path] | None = None,
        download_mode: DownloadMode = DownloadMode.DOWNLOAD_IF_MISSING,
    ):
        """Initialize the media resolver.

        Args:
            library_paths: Paths to local music library directories.
                          If provided, local files will be preferred.
            download_mode: How to handle track file acquisition.
        """
        self.library_paths = library_paths or []
        self.download_mode = download_mode

    def resolve(self, track: Track, download_url: str) -> ResolvedTrack:
        """Resolve a track to its file location.

        This is a pure function - it only examines the filesystem
        and returns a result without modifying anything.

        Args:
            track: Track to resolve.
            download_url: URL for downloading the track if needed.

        Returns:
            ResolvedTrack with resolution details.
        """
        logger.debug(f"Resolving track: '{track.title}' | download_mode={self.download_mode.value} | library_paths={[str(p) for p in self.library_paths]} | track.path={track.path}")

        # Download-always mode: always use download
        if self.download_mode == DownloadMode.DOWNLOAD_ALWAYS:
            logger.debug(f"  -> DOWNLOAD (mode=always)")
            return ResolvedTrack(
                track=track,
                method=ResolveMethod.DOWNLOAD,
                download_url=download_url,
                size_bytes=track.size_bytes,
            )

        # Try to find local file
        local_path = self._find_local_file(track)

        if local_path is not None:
            logger.debug(f"  -> LOCAL: {local_path}")
            return ResolvedTrack(
                track=track,
                method=ResolveMethod.LOCAL,
                local_path=local_path,
                size_bytes=local_path.stat().st_size,
                verified=True,
            )

        # Local-only mode: fail if not found locally
        if self.download_mode == DownloadMode.LOCAL_ONLY:
            logger.warning(f"  -> NOT_FOUND (local-only mode, track.path={track.path})")
            return ResolvedTrack(
                track=track,
                method=ResolveMethod.NOT_FOUND,
                error=f"Track not found locally and download_mode is local-only: {track.path}",
            )

        # Download-if-missing mode: use download
        logger.debug(f"  -> DOWNLOAD (not found locally)")
        return ResolvedTrack(
            track=track,
            method=ResolveMethod.DOWNLOAD,
            download_url=download_url,
            size_bytes=track.size_bytes,
        )

    def resolve_many(
        self,
        tracks: list[Track],
        download_url_builder: callable,
    ) -> list[ResolvedTrack]:
        """Resolve multiple tracks.

        Args:
            tracks: List of tracks to resolve.
            download_url_builder: Function that takes a track ID and returns download URL.

        Returns:
            List of ResolvedTrack objects in the same order.
        """
        return [
            self.resolve(track, download_url_builder(track.id))
            for track in tracks
        ]

    def _find_local_file(self, track: Track) -> Path | None:
        """Find a track's local file.

        Searches library paths for the track file. Handles Docker path mapping
        where Navidrome may report paths like /music/Artist/Album/Track.flac
        but the actual files are at a different host path.

        Args:
            track: Track to find.

        Returns:
            Path to local file if found, None otherwise.
        """
        if not self.library_paths:
            logger.debug(f"No library paths configured, cannot find local file for: {track.title}")
            return None

        if not track.path:
            logger.debug(f"Track has no path metadata: {track.title}")
            return None

        logger.debug(f"Looking for local file: track.path={track.path}")

        # Common Navidrome Docker music folder prefixes to strip
        docker_prefixes = ['/music/', '/music', 'music/']

        for lib_path in self.library_paths:
            logger.debug(f"Checking library path: {lib_path}")

            # Build list of candidate paths to check
            candidates = []
            track_path = track.path

            # Try stripping common Docker prefixes (e.g., /music/Artist/Album/file.flac -> Artist/Album/file.flac)
            relative_path = track_path
            for prefix in docker_prefixes:
                if track_path.startswith(prefix):
                    relative_path = track_path[len(prefix):]
                    logger.debug(f"  Stripped Docker prefix '{prefix}' -> {relative_path}")
                    break
            
            # Also try stripping leading slashes
            relative_path = relative_path.lstrip('/')
            
            # Primary candidate: library path + relative path (after stripping Docker prefix)
            candidates.append(lib_path / relative_path)
            
            # Also try the original path variations
            if track_path.startswith('/'):
                candidates.append(lib_path / track_path.lstrip('/'))
            candidates.append(lib_path / track_path)

            # Try absolute path directly if it exists
            if Path(track_path).is_absolute():
                candidates.append(Path(track_path))

            for candidate in candidates:
                logger.debug(f"  Trying candidate: {candidate}")
                try:
                    if candidate.exists() and candidate.is_file():
                        logger.info(f"Found local file: {candidate}")
                        return candidate.resolve()
                except (OSError, PermissionError) as e:
                    logger.debug(f"  Error checking {candidate}: {e}")
                    continue

        logger.debug(f"Could not find local file for: {track.title} (path: {track.path})")
        return None

    def get_resolution_summary(
        self,
        resolved_tracks: list[ResolvedTrack],
    ) -> dict:
        """Get a summary of resolution results.

        Args:
            resolved_tracks: List of resolved tracks.

        Returns:
            Dictionary with summary statistics.
        """
        summary = {
            "total": len(resolved_tracks),
            "local": 0,
            "download": 0,
            "not_found": 0,
            "total_size_bytes": 0,
            "download_size_bytes": 0,
        }

        for rt in resolved_tracks:
            if rt.method == ResolveMethod.LOCAL:
                summary["local"] += 1
            elif rt.method == ResolveMethod.DOWNLOAD:
                summary["download"] += 1
            elif rt.method == ResolveMethod.NOT_FOUND:
                summary["not_found"] += 1

            if rt.size_bytes:
                summary["total_size_bytes"] += rt.size_bytes
                if rt.method == ResolveMethod.DOWNLOAD:
                    summary["download_size_bytes"] += rt.size_bytes

        return summary
