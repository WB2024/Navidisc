"""Disc planning engine for splitting playlists across discs.

This module provides:
- Intelligent playlist splitting based on disc capacity
- Support for data CDs (size-based) and audio CDs (duration-based)
- Multiple planning strategies
- Serializable, deterministic output
"""

import logging
from datetime import datetime
from enum import StrEnum

from navidisc.models import BurnPlan, DiscPlan, DiscType, Playlist, Track

logger = logging.getLogger(__name__)


class PlanningStrategy(StrEnum):
    """Strategy for splitting playlists across discs."""
    GREEDY_SEQUENTIAL = "greedy_sequential"  # Fill each disc in order
    # Future strategies:
    # MINIMIZE_DISCS = "minimize_discs"  # Bin-packing optimization
    # FIXED_TRACKS = "fixed_tracks"  # Fixed number of tracks per disc


class PlanningError(Exception):
    """Error during disc planning."""
    pass


class DiscPlanningEngine:
    """Engine for planning how to split playlists across discs.

    This engine is:
    - Deterministic: same inputs always produce same outputs
    - Pure: no side effects
    - Serializable: plans can be saved/loaded as JSON

    Example:
        engine = DiscPlanningEngine(
            disc_type=DiscType.DATA,
            disc_capacity_bytes=700 * 1024 * 1024
        )
        plan = engine.plan(playlist, tracks_with_sizes)
    """

    # Default capacities
    DEFAULT_DATA_CD_BYTES = 700 * 1024 * 1024  # 700 MB
    DEFAULT_AUDIO_CD_SECONDS = 80 * 60  # 80 minutes
    
    # ISO9660 filesystem overhead settings
    # ISO overhead includes: volume descriptors, path tables, directory records,
    # Rock Ridge extensions (~200 bytes/file), Joliet extensions, sector padding
    # Real-world testing shows 10-20% overhead depending on file count/names
    ISO_OVERHEAD_PERCENT = 0.15  # 15% overhead for ISO9660 + Rock Ridge + Joliet
    SAFETY_MARGIN_BYTES = 10 * 1024 * 1024  # 10 MB safety margin

    def __init__(
        self,
        disc_type: DiscType = DiscType.DATA,
        disc_capacity_bytes: int | None = None,
        disc_capacity_seconds: int | None = None,
        strategy: PlanningStrategy = PlanningStrategy.GREEDY_SEQUENTIAL,
    ):
        """Initialize the planning engine.

        Args:
            disc_type: Type of disc to plan for.
            disc_capacity_bytes: Capacity for data discs (bytes).
            disc_capacity_seconds: Capacity for audio discs (seconds).
            strategy: Planning strategy to use.
        """
        self.disc_type = disc_type
        self.strategy = strategy

        # Set capacities based on disc type
        if disc_type == DiscType.DATA:
            raw_capacity = disc_capacity_bytes or self.DEFAULT_DATA_CD_BYTES
            # Calculate effective capacity accounting for ISO overhead and safety margin
            self._raw_capacity_bytes = raw_capacity
            self.disc_capacity_bytes = self._calculate_effective_capacity(raw_capacity)
            self.disc_capacity_seconds = None
        else:
            self._raw_capacity_bytes = None
            self.disc_capacity_bytes = None
            self.disc_capacity_seconds = disc_capacity_seconds or self.DEFAULT_AUDIO_CD_SECONDS
    
    def _calculate_effective_capacity(self, raw_capacity: int) -> int:
        """Calculate effective usable capacity after accounting for filesystem overhead.
        
        ISO9660 filesystems with Rock Ridge and Joliet extensions add significant
        overhead that must be accounted for in planning. This includes:
        - Volume descriptors and path tables
        - Directory records for each file
        - Rock Ridge POSIX extensions (~200 bytes per file)
        - Joliet Unicode filename support
        - 2048-byte sector alignment padding
        
        Args:
            raw_capacity: Raw disc capacity in bytes.
            
        Returns:
            Effective capacity available for file data.
        """
        # Subtract ISO overhead percentage
        after_overhead = int(raw_capacity * (1 - self.ISO_OVERHEAD_PERCENT))
        # Subtract safety margin
        effective = after_overhead - self.SAFETY_MARGIN_BYTES
        
        logger.info(
            f"Disc capacity calculation: {raw_capacity / 1024 / 1024:.0f} MB raw "
            f"- {self.ISO_OVERHEAD_PERCENT * 100:.0f}% ISO overhead "
            f"- {self.SAFETY_MARGIN_BYTES / 1024 / 1024:.0f} MB safety margin "
            f"= {effective / 1024 / 1024:.0f} MB effective"
        )
        
        return effective

    def plan(
        self,
        playlist: Playlist,
        track_sizes: dict[str, int] | None = None,
    ) -> BurnPlan:
        """Create a burn plan for a playlist.

        Args:
            playlist: Playlist to plan.
            track_sizes: Dictionary mapping track IDs to file sizes in bytes.
                        Required for data discs if tracks don't have size info.

        Returns:
            BurnPlan with disc allocations.

        Raises:
            PlanningError: If planning fails.
        """
        if not playlist.tracks:
            raise PlanningError("Playlist has no tracks")

        # Build size/duration lookup
        size_lookup = track_sizes or {}

        # Verify we have required info
        for track in playlist.tracks:
            if self.disc_type == DiscType.DATA:
                size = size_lookup.get(track.id) or track.size_bytes
                if not size:
                    raise PlanningError(
                        f"Track '{track.title}' has no size information"
                    )
            else:
                if not track.duration_seconds:
                    raise PlanningError(
                        f"Track '{track.title}' has no duration information"
                    )

        # Plan using selected strategy
        if self.strategy == PlanningStrategy.GREEDY_SEQUENTIAL:
            discs = self._plan_greedy_sequential(playlist.tracks, size_lookup)
        else:
            raise PlanningError(f"Unknown planning strategy: {self.strategy}")

        return BurnPlan(
            playlist_id=playlist.id,
            playlist_name=playlist.name,
            disc_type=self.disc_type,
            disc_capacity_bytes=self.disc_capacity_bytes,
            disc_capacity_seconds=self.disc_capacity_seconds,
            discs=discs,
            created_at=datetime.now(),
        )

    def _plan_greedy_sequential(
        self,
        tracks: list[Track],
        size_lookup: dict[str, int],
    ) -> list[DiscPlan]:
        """Plan using greedy sequential strategy.

        This fills each disc in order until it's full,
        then moves to the next disc.

        Args:
            tracks: Ordered list of tracks.
            size_lookup: Track ID to size mapping.

        Returns:
            List of DiscPlan objects.
        """
        logger.debug("=" * 60)
        logger.debug("PLANNER: GREEDY SEQUENTIAL PLANNING")
        logger.debug("=" * 60)
        logger.debug(f"Total tracks: {len(tracks)}")
        logger.debug(f"Disc type: {self.disc_type}")
        if self.disc_capacity_bytes:
            if self._raw_capacity_bytes:
                logger.info(
                    f"Disc capacity: {self._raw_capacity_bytes / 1024 / 1024:.0f} MB raw -> "
                    f"{self.disc_capacity_bytes / 1024 / 1024:.0f} MB effective "
                    f"(after {self.ISO_OVERHEAD_PERCENT * 100:.0f}% ISO overhead + "
                    f"{self.SAFETY_MARGIN_BYTES / 1024 / 1024:.0f} MB safety margin)"
                )
            else:
                logger.debug(f"Disc capacity: {self.disc_capacity_bytes / 1024 / 1024:.0f} MB")
        if self.disc_capacity_seconds:
            logger.debug(f"Disc capacity: {self.disc_capacity_seconds} seconds ({self.disc_capacity_seconds // 60} min)")
        logger.debug("=" * 60)
        
        discs: list[DiscPlan] = []
        current_disc_tracks: list[str] = []
        current_size = 0
        current_duration = 0
        current_disc_num = 1

        for idx, track in enumerate(tracks, 1):
            track_size = size_lookup.get(track.id) or track.size_bytes or 0
            track_duration = track.duration_seconds
            
            # Detailed logging for each track
            logger.debug(
                f"Track {idx}: '{track.title}' - "
                f"size={track_size} bytes ({track_size / 1024 / 1024:.2f} MB), "
                f"duration={track_duration}s"
            )

            # Check if track fits on current disc
            fits = self._track_fits(
                current_size=current_size,
                current_duration=current_duration,
                track_size=track_size,
                track_duration=track_duration,
            )

            if not fits and current_disc_tracks:
                # Start a new disc
                if self.disc_capacity_bytes:
                    pct_used = (current_size / self.disc_capacity_bytes) * 100
                    remaining_mb = (self.disc_capacity_bytes - current_size) / 1024 / 1024
                    logger.info(
                        f"Disc {current_disc_num} full: {len(current_disc_tracks)} tracks, "
                        f"{current_size / 1024 / 1024:.1f} MB ({pct_used:.1f}% capacity, "
                        f"{remaining_mb:.1f} MB unused)"
                    )
                else:
                    logger.info(
                        f"Disc {current_disc_num} full: {len(current_disc_tracks)} tracks, "
                        f"{current_size / 1024 / 1024:.2f} MB, {current_duration}s"
                    )
                discs.append(DiscPlan(
                    disc_number=len(discs) + 1,
                    track_ids=current_disc_tracks,
                    total_size_bytes=current_size,
                    total_duration_seconds=current_duration,
                ))
                current_disc_tracks = []
                current_size = 0
                current_duration = 0
                current_disc_num += 1

            # Check if single track exceeds disc capacity
            if not self._track_fits(0, 0, track_size, track_duration):
                effective_mb = self.disc_capacity_bytes / 1024 / 1024 if self.disc_capacity_bytes else 0
                raw_mb = self._raw_capacity_bytes / 1024 / 1024 if self._raw_capacity_bytes else effective_mb
                logger.error(
                    f"Track '{track.title}' exceeds disc capacity! "
                    f"Track: {track_size / 1024 / 1024:.2f} MB, "
                    f"Effective capacity: {effective_mb:.0f} MB (raw: {raw_mb:.0f} MB)"
                )
                raise PlanningError(
                    f"Track '{track.title}' exceeds disc capacity "
                    f"({self._format_capacity(track_size, track_duration)})"
                )

            # Add track to current disc
            current_disc_tracks.append(track.id)
            current_size += track_size
            current_duration += track_duration
            
            if self.disc_capacity_bytes:
                pct_used = (current_size / self.disc_capacity_bytes) * 100
                remaining_mb = (self.disc_capacity_bytes - current_size) / 1024 / 1024
                logger.debug(
                    f"  -> Added to disc {current_disc_num}, now at {pct_used:.1f}% "
                    f"({current_size / 1024 / 1024:.1f} MB, {remaining_mb:.1f} MB remaining)"
                )

        # Add final disc
        if current_disc_tracks:
            if self.disc_capacity_bytes:
                pct_used = (current_size / self.disc_capacity_bytes) * 100
                remaining_mb = (self.disc_capacity_bytes - current_size) / 1024 / 1024
                logger.info(
                    f"Disc {current_disc_num} (final): {len(current_disc_tracks)} tracks, "
                    f"{current_size / 1024 / 1024:.1f} MB ({pct_used:.1f}% of effective capacity, "
                    f"{remaining_mb:.1f} MB headroom)"
                )
            else:
                logger.info(
                    f"Disc {current_disc_num} (final): {len(current_disc_tracks)} tracks, "
                    f"{current_size / 1024 / 1024:.2f} MB, {current_duration}s"
                )
            discs.append(DiscPlan(
                disc_number=len(discs) + 1,
                track_ids=current_disc_tracks,
                total_size_bytes=current_size,
                total_duration_seconds=current_duration,
            ))

        logger.debug("=" * 60)
        logger.info(f"Planning complete: {len(discs)} disc(s) required")
        logger.debug("=" * 60)
        
        return discs

    def _track_fits(
        self,
        current_size: int,
        current_duration: int,
        track_size: int,
        track_duration: int,
    ) -> bool:
        """Check if a track fits on the current disc.

        Args:
            current_size: Current disc size usage in bytes.
            current_duration: Current disc duration usage in seconds.
            track_size: Track file size in bytes.
            track_duration: Track duration in seconds.

        Returns:
            True if track fits, False otherwise.
        """
        if self.disc_type == DiscType.DATA:
            return (current_size + track_size) <= self.disc_capacity_bytes
        else:
            return (current_duration + track_duration) <= self.disc_capacity_seconds

    def _format_capacity(self, size_bytes: int, duration_seconds: int) -> str:
        """Format capacity for error messages."""
        if self.disc_type == DiscType.DATA:
            mb = size_bytes / (1024 * 1024)
            return f"{mb:.1f} MB"
        else:
            minutes = duration_seconds // 60
            seconds = duration_seconds % 60
            return f"{minutes}:{seconds:02d}"

    def estimate_discs(
        self,
        total_size_bytes: int | None = None,
        total_duration_seconds: int | None = None,
    ) -> int:
        """Estimate number of discs needed.

        This is a rough estimate, not accounting for track boundaries.

        Args:
            total_size_bytes: Total size for data discs.
            total_duration_seconds: Total duration for audio discs.

        Returns:
            Estimated number of discs.
        """
        if self.disc_type == DiscType.DATA and total_size_bytes:
            return max(1, (total_size_bytes + self.disc_capacity_bytes - 1) // self.disc_capacity_bytes)
        elif self.disc_type == DiscType.AUDIO and total_duration_seconds:
            return max(1, (total_duration_seconds + self.disc_capacity_seconds - 1) // self.disc_capacity_seconds)
        return 1

    def get_plan_summary(self, plan: BurnPlan) -> dict:
        """Get a summary of a burn plan.

        Args:
            plan: Burn plan to summarize.

        Returns:
            Dictionary with plan summary.
        """
        total_tracks = sum(d.track_count for d in plan.discs)
        total_size = sum(d.total_size_bytes for d in plan.discs)
        total_duration = sum(d.total_duration_seconds for d in plan.discs)

        # Calculate average utilization
        total_utilizations = []
        for disc in plan.discs:
            if plan.disc_type == DiscType.DATA and plan.disc_capacity_bytes:
                total_utilizations.append(disc.total_size_bytes / plan.disc_capacity_bytes)
            elif plan.disc_type == DiscType.AUDIO and plan.disc_capacity_seconds:
                total_utilizations.append(disc.total_duration_seconds / plan.disc_capacity_seconds)
        
        avg_utilization = sum(total_utilizations) / len(total_utilizations) if total_utilizations else 0

        summary = {
            "playlist_name": plan.playlist_name,
            "disc_type": plan.disc_type.value,
            "total_discs": plan.total_discs,
            "total_tracks": total_tracks,
            "total_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "total_duration_minutes": total_duration / 60,
            "average_utilization": avg_utilization,
            "discs": [],
        }

        for disc in plan.discs:
            disc_info = {
                "disc_number": disc.disc_number,
                "tracks": disc.track_count,
                "size_mb": disc.total_size_bytes / (1024 * 1024),
                "duration_minutes": disc.total_duration_seconds / 60,
            }

            # Add capacity usage percentage
            if plan.disc_type == DiscType.DATA and plan.disc_capacity_bytes:
                disc_info["capacity_percent"] = (
                    disc.total_size_bytes / plan.disc_capacity_bytes * 100
                )
            elif plan.disc_type == DiscType.AUDIO and plan.disc_capacity_seconds:
                disc_info["capacity_percent"] = (
                    disc.total_duration_seconds / plan.disc_capacity_seconds * 100
                )

            summary["discs"].append(disc_info)

        return summary


def plan_to_json(plan: BurnPlan) -> str:
    """Serialize a burn plan to JSON.

    Args:
        plan: Burn plan to serialize.

    Returns:
        JSON string representation.
    """
    return plan.model_dump_json(indent=2)


def plan_from_json(json_str: str) -> BurnPlan:
    """Deserialize a burn plan from JSON.

    Args:
        json_str: JSON string representation.

    Returns:
        BurnPlan instance.
    """
    return BurnPlan.model_validate_json(json_str)
