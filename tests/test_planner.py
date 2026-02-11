"""Tests for the disc planning engine."""

import pytest

from navidisc.models import DiscType, Playlist, Track
from navidisc.planner import DiscPlanningEngine, PlanningStrategy


def make_track(track_id: str, size_mb: float = 5.0, duration_seconds: int = 180) -> Track:
    """Create a test track."""
    return Track(
        id=track_id,
        title=f"Track {track_id}",
        artist="Test Artist",
        duration_seconds=duration_seconds,
        size_bytes=int(size_mb * 1024 * 1024),
    )


def make_playlist(tracks: list[Track]) -> Playlist:
    """Create a test playlist."""
    total_duration = sum(t.duration_seconds for t in tracks)
    return Playlist(
        id="test-playlist",
        name="Test Playlist",
        track_count=len(tracks),
        duration_seconds=total_duration,
        tracks=tracks,
    )


# Calculate effective capacity for tests
# Raw 700 MB - 15% ISO overhead - 10 MB safety = ~585 MB effective
RAW_CAPACITY_MB = 700
ISO_OVERHEAD_PERCENT = 0.15
SAFETY_MARGIN_MB = 10
EFFECTIVE_CAPACITY_MB = int(RAW_CAPACITY_MB * (1 - ISO_OVERHEAD_PERCENT) - SAFETY_MARGIN_MB)  # ~585 MB


class TestDiscPlanningEngine:
    """Tests for DiscPlanningEngine."""
    
    def test_single_disc_fits(self):
        """Test that tracks fitting on one disc create a single-disc plan."""
        # Create 10 tracks of 50MB each = 500MB (fits on ~585MB effective capacity)
        tracks = [make_track(f"track-{i}", size_mb=50) for i in range(10)]
        playlist = make_playlist(tracks)
        
        engine = DiscPlanningEngine(
            disc_type=DiscType.DATA,
            disc_capacity_bytes=RAW_CAPACITY_MB * 1024 * 1024,
        )
        
        plan = engine.plan(playlist)
        
        assert plan.total_discs == 1
        assert plan.discs[0].track_count == 10
        assert len(plan.discs[0].track_ids) == 10
    
    def test_multiple_discs_required(self):
        """Test that large playlists are split across multiple discs."""
        # Create 20 tracks of 50MB each = 1000MB
        # With ~585MB effective capacity: ~11 tracks per disc
        tracks = [make_track(f"track-{i}", size_mb=50) for i in range(20)]
        playlist = make_playlist(tracks)
        
        engine = DiscPlanningEngine(
            disc_type=DiscType.DATA,
            disc_capacity_bytes=RAW_CAPACITY_MB * 1024 * 1024,
        )
        
        plan = engine.plan(playlist)
        
        assert plan.total_discs == 2
        # First disc should have 11 tracks (585MB / 50MB = 11.7 -> 11)
        assert plan.discs[0].track_count == 11
        # Second disc should have remaining 9 tracks
        assert plan.discs[1].track_count == 9
    
    def test_audio_disc_planning(self):
        """Test planning for audio CDs based on duration."""
        # Create 30 tracks of 4 minutes each = 120 minutes (needs 2 CDs)
        tracks = [make_track(f"track-{i}", duration_seconds=240) for i in range(30)]
        playlist = make_playlist(tracks)
        
        engine = DiscPlanningEngine(
            disc_type=DiscType.AUDIO,
            disc_capacity_seconds=80 * 60,  # 80 minutes
        )
        
        plan = engine.plan(playlist)
        
        assert plan.total_discs == 2
        # First disc: 80 min / 4 min = 20 tracks
        assert plan.discs[0].track_count == 20
        # Second disc: remaining 10 tracks
        assert plan.discs[1].track_count == 10
    
    def test_track_order_preserved(self):
        """Test that track order is preserved across discs."""
        # Use 100MB tracks, ~5 fit per disc with 585MB effective capacity
        tracks = [make_track(f"track-{i:03d}", size_mb=100) for i in range(10)]
        playlist = make_playlist(tracks)
        
        engine = DiscPlanningEngine(
            disc_type=DiscType.DATA,
            disc_capacity_bytes=RAW_CAPACITY_MB * 1024 * 1024,
        )
        
        plan = engine.plan(playlist)
        
        # Collect all track IDs in order
        all_track_ids = []
        for disc in plan.discs:
            all_track_ids.extend(disc.track_ids)
        
        # Verify order matches original
        original_ids = [t.id for t in tracks]
        assert all_track_ids == original_ids
    
    def test_empty_playlist_raises_error(self):
        """Test that empty playlist raises an error."""
        playlist = make_playlist([])
        
        engine = DiscPlanningEngine(disc_type=DiscType.DATA)
        
        with pytest.raises(Exception) as exc_info:
            engine.plan(playlist)
        
        assert "no tracks" in str(exc_info.value).lower()
    
    def test_oversized_track_raises_error(self):
        """Test that a track larger than disc capacity raises an error."""
        # 600MB track exceeds ~585MB effective capacity
        tracks = [make_track("huge-track", size_mb=600)]
        playlist = make_playlist(tracks)
        
        engine = DiscPlanningEngine(
            disc_type=DiscType.DATA,
            disc_capacity_bytes=RAW_CAPACITY_MB * 1024 * 1024,
        )
        
        with pytest.raises(Exception) as exc_info:
            engine.plan(playlist)
        
        assert "exceeds disc capacity" in str(exc_info.value).lower()
    
    def test_plan_summary(self):
        """Test that plan summary contains expected information."""
        tracks = [make_track(f"track-{i}", size_mb=50, duration_seconds=200) for i in range(10)]
        playlist = make_playlist(tracks)
        
        engine = DiscPlanningEngine(
            disc_type=DiscType.DATA,
            disc_capacity_bytes=RAW_CAPACITY_MB * 1024 * 1024,
        )
        
        plan = engine.plan(playlist)
        summary = engine.get_plan_summary(plan)
        
        assert summary["playlist_name"] == "Test Playlist"
        assert summary["disc_type"] == "data"
        assert summary["total_discs"] == 1
        assert summary["total_tracks"] == 10
        assert "discs" in summary
        assert len(summary["discs"]) == 1


class TestEstimateDiscs:
    """Tests for disc count estimation."""
    
    def test_estimate_data_discs(self):
        """Test estimation for data discs."""
        engine = DiscPlanningEngine(
            disc_type=DiscType.DATA,
            disc_capacity_bytes=RAW_CAPACITY_MB * 1024 * 1024,
        )
        
        # With ~585MB effective capacity:
        # 1.5 GB (1536 MB) should need 3 discs (1536 / 585 = 2.6 -> 3)
        assert engine.estimate_discs(total_size_bytes=int(1.5 * 1024**3)) == 3
        
        # 500 MB should need 1 disc (fits in 585MB)
        assert engine.estimate_discs(total_size_bytes=500 * 1024**2) == 1
    
    def test_estimate_audio_discs(self):
        """Test estimation for audio discs."""
        engine = DiscPlanningEngine(
            disc_type=DiscType.AUDIO,
            disc_capacity_seconds=80 * 60,  # 80 minutes
        )
        
        # 120 minutes should need 2 discs
        assert engine.estimate_discs(total_duration_seconds=120 * 60) == 2
        
        # 60 minutes should need 1 disc
        assert engine.estimate_discs(total_duration_seconds=60 * 60) == 1
