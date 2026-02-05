"""Tests for the media resolver."""

import tempfile
from pathlib import Path

import pytest

from navidisc.media.resolver import MediaResolver, ResolveMethod
from navidisc.models import DownloadMode, Track


def make_track(track_id: str = "test-track", path: str | None = None) -> Track:
    """Create a test track."""
    return Track(
        id=track_id,
        title="Test Track",
        artist="Test Artist",
        duration_seconds=180,
        size_bytes=5 * 1024 * 1024,
        path=path,
    )


class TestMediaResolver:
    """Tests for MediaResolver."""
    
    def test_download_always_mode(self):
        """Test that download-always mode always returns DOWNLOAD."""
        resolver = MediaResolver(
            library_paths=[],
            download_mode=DownloadMode.DOWNLOAD_ALWAYS,
        )
        
        track = make_track()
        result = resolver.resolve(track, "http://example.com/download")
        
        assert result.method == ResolveMethod.DOWNLOAD
        assert result.download_url == "http://example.com/download"
        assert result.is_available is True
    
    def test_local_only_mode_not_found(self):
        """Test that local-only mode fails when file not found."""
        resolver = MediaResolver(
            library_paths=[],
            download_mode=DownloadMode.LOCAL_ONLY,
        )
        
        track = make_track()
        result = resolver.resolve(track, "http://example.com/download")
        
        assert result.method == ResolveMethod.NOT_FOUND
        assert result.is_available is False
        assert result.error is not None
    
    def test_local_only_mode_found(self):
        """Test that local-only mode succeeds when file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lib_path = Path(tmpdir)
            track_file = lib_path / "Artist" / "Album" / "track.flac"
            track_file.parent.mkdir(parents=True)
            track_file.write_bytes(b"fake audio data")
            
            resolver = MediaResolver(
                library_paths=[lib_path],
                download_mode=DownloadMode.LOCAL_ONLY,
            )
            
            track = make_track(path="Artist/Album/track.flac")
            result = resolver.resolve(track, "http://example.com/download")
            
            assert result.method == ResolveMethod.LOCAL
            assert result.is_available is True
            assert result.local_path is not None
            assert result.verified is True
    
    def test_download_if_missing_local_exists(self):
        """Test that download-if-missing uses local file when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lib_path = Path(tmpdir)
            track_file = lib_path / "track.flac"
            track_file.write_bytes(b"fake audio data")
            
            resolver = MediaResolver(
                library_paths=[lib_path],
                download_mode=DownloadMode.DOWNLOAD_IF_MISSING,
            )
            
            track = make_track(path="track.flac")
            result = resolver.resolve(track, "http://example.com/download")
            
            assert result.method == ResolveMethod.LOCAL
    
    def test_download_if_missing_local_missing(self):
        """Test that download-if-missing falls back to download."""
        resolver = MediaResolver(
            library_paths=[],
            download_mode=DownloadMode.DOWNLOAD_IF_MISSING,
        )
        
        track = make_track()
        result = resolver.resolve(track, "http://example.com/download")
        
        assert result.method == ResolveMethod.DOWNLOAD
        assert result.download_url == "http://example.com/download"
    
    def test_resolve_many(self):
        """Test resolving multiple tracks at once."""
        resolver = MediaResolver(
            library_paths=[],
            download_mode=DownloadMode.DOWNLOAD_ALWAYS,
        )
        
        tracks = [make_track(f"track-{i}") for i in range(5)]
        results = resolver.resolve_many(
            tracks,
            lambda track_id: f"http://example.com/{track_id}",
        )
        
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result.method == ResolveMethod.DOWNLOAD
            assert result.download_url == f"http://example.com/track-{i}"
    
    def test_resolution_summary(self):
        """Test getting a resolution summary."""
        resolver = MediaResolver(download_mode=DownloadMode.DOWNLOAD_ALWAYS)
        
        tracks = [make_track(f"track-{i}") for i in range(3)]
        results = resolver.resolve_many(
            tracks,
            lambda track_id: f"http://example.com/{track_id}",
        )
        
        summary = resolver.get_resolution_summary(results)
        
        assert summary["total"] == 3
        assert summary["download"] == 3
        assert summary["local"] == 0
        assert summary["not_found"] == 0
        assert summary["total_size_bytes"] == 3 * 5 * 1024 * 1024
