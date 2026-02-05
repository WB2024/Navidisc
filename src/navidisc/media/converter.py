"""Audio converter for converting tracks to MP3.

This module handles audio conversion using ffmpeg with:
- Quality presets (best, high, medium, small)
- Progress reporting
- Metadata preservation
"""

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path

from navidisc.models import ConversionQuality


class ConversionError(Exception):
    """Error during audio conversion."""

    def __init__(self, message: str, source_path: Path | None = None):
        super().__init__(message)
        self.source_path = source_path


class ConversionProgress:
    """Progress information for a conversion."""

    def __init__(
        self,
        source_path: Path,
        total_files: int,
        completed_files: int,
    ):
        self.source_path = source_path
        self.total_files = total_files
        self.completed_files = completed_files

    @property
    def percent(self) -> float:
        """Conversion progress as percentage."""
        if self.total_files > 0:
            return (self.completed_files / self.total_files) * 100
        return 0

    @property
    def filename(self) -> str:
        """Current filename being converted."""
        return self.source_path.name


ProgressCallback = Callable[[ConversionProgress], None]


# Quality presets: (bitrate, description)
QUALITY_PRESETS: dict[ConversionQuality, dict] = {
    ConversionQuality.BEST: {
        "bitrate": "320k",
        "description": "320kbps CBR - Highest quality",
    },
    ConversionQuality.HIGH: {
        "bitrate": "256k",
        "description": "256kbps CBR - High quality",
    },
    ConversionQuality.MEDIUM: {
        "bitrate": "192k",
        "description": "192kbps CBR - Good balance",
    },
    ConversionQuality.SMALL: {
        "bitrate": "128k",
        "description": "128kbps CBR - Smallest size",
    },
}


def get_quality_description(quality: ConversionQuality) -> str:
    """Get human-readable description of quality preset."""
    if quality == ConversionQuality.DISABLED:
        return "No conversion"
    preset = QUALITY_PRESETS.get(quality)
    return preset["description"] if preset else "Unknown"


def check_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system."""
    return shutil.which("ffmpeg") is not None


class AudioConverter:
    """Converts audio files to MP3 using ffmpeg.

    This class handles audio conversion with configurable quality presets.
    Metadata from the source file is preserved in the output.

    Example:
        converter = AudioConverter(
            output_dir=Path("/tmp/navidisc/converted"),
            quality=ConversionQuality.BEST
        )

        converted_paths = await converter.convert_many(
            source_paths,
            progress_callback=lambda p: print(f"Converting: {p.filename}")
        )
    """

    def __init__(
        self,
        output_dir: Path,
        quality: ConversionQuality = ConversionQuality.BEST,
    ):
        """Initialize the converter.

        Args:
            output_dir: Directory to write converted files.
            quality: Quality preset for conversion.
        """
        self.output_dir = output_dir
        self.quality = quality
        
        if quality == ConversionQuality.DISABLED:
            raise ValueError("Cannot create converter with DISABLED quality")
        
        self._preset = QUALITY_PRESETS[quality]

    def prepare(self) -> None:
        """Prepare the output directory."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def convert(self, source_path: Path) -> Path:
        """Convert a single audio file to MP3.

        Args:
            source_path: Path to the source audio file.

        Returns:
            Path to the converted MP3 file.

        Raises:
            ConversionError: If conversion fails.
        """
        if not source_path.exists():
            raise ConversionError(f"Source file not found: {source_path}", source_path)

        # Skip if already MP3
        if source_path.suffix.lower() == ".mp3":
            return source_path

        # Determine output path
        output_path = self.output_dir / f"{source_path.stem}.mp3"

        # Build ffmpeg command
        # -i: input file
        # -b:a: audio bitrate
        # -map_metadata 0: preserve metadata from input
        # -id3v2_version 3: use ID3v2.3 for best compatibility
        # -y: overwrite output without asking
        cmd = [
            "ffmpeg",
            "-i", str(source_path),
            "-b:a", self._preset["bitrate"],
            "-map_metadata", "0",
            "-id3v2_version", "3",
            "-y",
            str(output_path),
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise ConversionError(
                    f"ffmpeg failed for {source_path.name}: {error_msg}",
                    source_path,
                )

            return output_path

        except FileNotFoundError:
            raise ConversionError(
                "ffmpeg not found. Please install ffmpeg to enable audio conversion.",
                source_path,
            )
        except Exception as e:
            if isinstance(e, ConversionError):
                raise
            raise ConversionError(f"Conversion failed: {e}", source_path)

    async def convert_many(
        self,
        track_paths: dict[str, Path],
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Path]:
        """Convert multiple audio files to MP3.

        Args:
            track_paths: Mapping of track IDs to source file paths.
            progress_callback: Optional callback for progress updates.

        Returns:
            Mapping of track IDs to converted file paths.
            Files that were already MP3 are returned unchanged.
        """
        self.prepare()

        converted: dict[str, Path] = {}
        total = len(track_paths)
        completed = 0

        for track_id, source_path in track_paths.items():
            if progress_callback:
                progress_callback(ConversionProgress(
                    source_path=source_path,
                    total_files=total,
                    completed_files=completed,
                ))

            # Convert the file
            output_path = await self.convert(source_path)
            converted[track_id] = output_path
            completed += 1

        # Final progress update
        if progress_callback and track_paths:
            last_path = list(track_paths.values())[-1]
            progress_callback(ConversionProgress(
                source_path=last_path,
                total_files=total,
                completed_files=completed,
            ))

        return converted

    def needs_conversion(self, source_path: Path) -> bool:
        """Check if a file needs conversion.

        Args:
            source_path: Path to check.

        Returns:
            True if the file should be converted (not already MP3).
        """
        return source_path.suffix.lower() != ".mp3"
