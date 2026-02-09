"""Staging manager for preparing disc directories.

This module handles:
- Creating temporary disc directories
- Copying or hard-linking files
- Filename normalization for disc compatibility
- Track renumbering
"""

import os
import shutil
from pathlib import Path
from typing import Optional

from navidisc.models import BurnPlan, DiscPlan, StagedDisc, StagedFile, Track


class StagingError(Exception):
    """Error during file staging."""
    pass


class StagingManager:
    """Manages file staging for disc burning.
    
    This class is responsible for preparing the files for each disc,
    creating properly structured directories that can be burned.
    
    The staging process:
    1. Creates a disc directory (e.g., staging/disc_01/)
    2. Copies or hard-links track files
    3. Applies filename normalization
    4. Optionally adds track numbers
    
    Example:
        manager = StagingManager(
            staging_dir=Path("/tmp/navidisc"),
            use_hardlinks=True
        )
        staged = manager.stage_disc(disc_plan, track_paths)
    """
    
    def __init__(
        self,
        staging_dir: Path,
        use_hardlinks: bool = True,
        normalize_filenames: bool = True,
        include_track_numbers: bool = True,
    ):
        """Initialize the staging manager.
        
        Args:
            staging_dir: Base directory for staging files.
            use_hardlinks: Use hard links instead of copying when possible.
            normalize_filenames: Sanitize filenames for disc compatibility.
            include_track_numbers: Prefix filenames with track numbers.
        """
        self.staging_dir = staging_dir
        self.use_hardlinks = use_hardlinks
        self.normalize_filenames = normalize_filenames
        self.include_track_numbers = include_track_numbers
    
    def prepare(self) -> None:
        """Prepare the staging directory.
        
        Creates the staging directory if it doesn't exist.
        """
        self.staging_dir.mkdir(parents=True, exist_ok=True)
    
    def stage_disc(
        self,
        disc_plan: DiscPlan,
        track_paths: dict[str, Path],
        tracks: dict[str, Track],
    ) -> StagedDisc:
        """Stage files for a single disc.
        
        Args:
            disc_plan: Plan for this disc.
            track_paths: Mapping of track IDs to source file paths.
            tracks: Mapping of track IDs to Track objects for metadata.
            
        Returns:
            StagedDisc with staged file information.
            
        Raises:
            StagingError: If staging fails.
        """
        # Create disc directory
        disc_dir = self.staging_dir / f"disc_{disc_plan.disc_number:02d}"
        
        try:
            # Remove existing disc directory if present
            if disc_dir.exists():
                shutil.rmtree(disc_dir)
            disc_dir.mkdir(parents=True)
        except OSError as e:
            raise StagingError(f"Failed to create disc directory: {e}")
        
        staged_files: list[StagedFile] = []
        total_size = 0
        
        for position, track_id in enumerate(disc_plan.track_ids, start=1):
            source_path = track_paths.get(track_id)
            if source_path is None:
                raise StagingError(f"No file path for track {track_id}")
            
            if not source_path.exists():
                raise StagingError(f"Source file does not exist: {source_path}")
            
            track = tracks.get(track_id)
            if track is None:
                raise StagingError(f"No track metadata for {track_id}")
            
            # Generate filename
            filename = self._generate_filename(track, position, source_path.suffix)
            staged_path = disc_dir / filename
            
            # Copy or link file
            is_hardlink = self._stage_file(source_path, staged_path)
            
            file_size = staged_path.stat().st_size
            total_size += file_size
            
            staged_files.append(StagedFile(
                track_id=track_id,
                source_path=source_path,
                staged_path=staged_path,
                filename=filename,
                size_bytes=file_size,
                is_hardlink=is_hardlink,
            ))
        
        return StagedDisc(
            disc_number=disc_plan.disc_number,
            directory=disc_dir,
            files=staged_files,
            total_size_bytes=total_size,
        )
    
    def stage_all_discs(
        self,
        burn_plan: BurnPlan,
        track_paths: dict[str, Path],
        tracks: dict[str, Track],
    ) -> list[StagedDisc]:
        """Stage files for all discs in a burn plan.
        
        Args:
            burn_plan: Complete burn plan.
            track_paths: Mapping of track IDs to source file paths.
            tracks: Mapping of track IDs to Track objects.
            
        Returns:
            List of StagedDisc objects.
        """
        self.prepare()
        
        staged_discs = []
        for disc_plan in burn_plan.discs:
            staged = self.stage_disc(disc_plan, track_paths, tracks)
            staged_discs.append(staged)
        
        return staged_discs
    
    def _stage_file(self, source: Path, dest: Path) -> bool:
        """Stage a single file by copying or hard-linking.
        
        Args:
            source: Source file path.
            dest: Destination file path.
            
        Returns:
            True if hard-linked, False if copied.
            
        Raises:
            StagingError: If staging fails.
        """
        is_hardlink = False
        
        try:
            if self.use_hardlinks:
                try:
                    os.link(source, dest)
                    is_hardlink = True
                except OSError:
                    # Hard link failed (cross-device or not supported)
                    shutil.copy2(source, dest)
            else:
                shutil.copy2(source, dest)
        except (OSError, shutil.Error) as e:
            raise StagingError(f"Failed to stage file {source}: {e}")
        
        return is_hardlink
    
    def _generate_filename(
        self,
        track: Track,
        position: int,
        extension: str,
    ) -> str:
        """Generate a filename for a staged track.
        
        Args:
            track: Track metadata.
            position: Track position on disc (1-based).
            extension: File extension (including dot).
            
        Returns:
            Generated filename.
        """
        # Build base filename
        if self.normalize_filenames:
            artist = self._sanitize_component(track.artist)
            title = self._sanitize_component(track.title)
            base = f"{artist} - {title}"
        else:
            base = f"{track.artist} - {track.title}"
        
        # Add track number prefix (format: "01. Artist - Title")
        if self.include_track_numbers:
            filename = f"{position:02d}. {base}{extension}"
        else:
            filename = f"{base}{extension}"
        
        # Ensure filename isn't too long (max 255 chars for most filesystems)
        if len(filename) > 250:
            name_part = filename[:-len(extension)]
            filename = name_part[:250 - len(extension)] + extension
        
        return filename
    
    def _sanitize_component(self, name: str) -> str:
        """Sanitize a filename component.
        
        Makes the string safe for use in filenames across
        different filesystems (including ISO 9660).
        
        Args:
            name: Original string.
            
        Returns:
            Sanitized string.
        """
        # Characters not allowed in filenames
        invalid_chars = '<>:"/\\|?*'
        
        # Replace invalid characters with underscores
        result = name
        for char in invalid_chars:
            result = result.replace(char, "_")
        
        # Remove control characters
        result = "".join(c for c in result if ord(c) >= 32)
        
        # Collapse multiple spaces/underscores
        while "__" in result:
            result = result.replace("__", "_")
        while "  " in result:
            result = result.replace("  ", " ")
        
        # Trim whitespace and underscores
        result = result.strip(" _")
        
        return result or "Unknown"
    
    def cleanup_disc(self, disc_number: int) -> None:
        """Clean up staged files for a disc.
        
        Args:
            disc_number: Disc number to clean up.
        """
        disc_dir = self.staging_dir / f"disc_{disc_number:02d}"
        if disc_dir.exists():
            shutil.rmtree(disc_dir)
    
    def cleanup_all(self) -> None:
        """Clean up all staged files."""
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir)
    
    def get_staging_summary(self, staged_discs: list[StagedDisc]) -> dict:
        """Get a summary of staged files.
        
        Args:
            staged_discs: List of staged discs.
            
        Returns:
            Summary dictionary.
        """
        total_files = sum(len(d.files) for d in staged_discs)
        total_size = sum(d.total_size_bytes for d in staged_discs)
        hardlink_count = sum(
            sum(1 for f in d.files if f.is_hardlink)
            for d in staged_discs
        )
        
        return {
            "total_discs": len(staged_discs),
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "hardlink_count": hardlink_count,
            "copy_count": total_files - hardlink_count,
            "staging_dir": str(self.staging_dir),
        }
