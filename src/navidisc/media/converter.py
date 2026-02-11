"""Audio converter for converting tracks to MP3.

This module handles audio conversion using ffmpeg with:
- Quality presets (best, high, medium, small)
- Progress reporting
- Metadata preservation
- Accurate duration probing via ffprobe
"""

import asyncio
import json
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from navidisc.models import ConversionQuality

logger = logging.getLogger(__name__)


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


def check_ffprobe_available() -> bool:
    """Check if ffprobe is available on the system."""
    return shutil.which("ffprobe") is not None


async def ffprobe_duration(file_path: Path) -> float | None:
    """Get the actual audio duration of a file using ffprobe.
    
    This is more accurate than relying on API metadata, which can be wrong.
    
    Args:
        file_path: Path to the audio file.
        
    Returns:
        Duration in seconds (as float for precision), or None if probe fails.
    """
    if not file_path.exists():
        logger.warning(f"ffprobe: File does not exist: {file_path}")
        return None
    
    if not check_ffprobe_available():
        logger.warning("ffprobe not available, cannot get accurate duration")
        return None
    
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(file_path),
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.warning(f"ffprobe failed for {file_path.name}: {stderr.decode()}")
            return None
        
        data = json.loads(stdout.decode())
        duration_str = data.get("format", {}).get("duration")
        
        if duration_str:
            duration = float(duration_str)
            logger.debug(f"ffprobe: {file_path.name} duration = {duration:.2f}s")
            return duration
        else:
            logger.warning(f"ffprobe: No duration found for {file_path.name}")
            return None
            
    except json.JSONDecodeError as e:
        logger.warning(f"ffprobe: Invalid JSON response for {file_path.name}: {e}")
        return None
    except Exception as e:
        logger.warning(f"ffprobe failed for {file_path.name}: {e}")
        return None


def ffprobe_duration_sync(file_path: Path) -> float | None:
    """Synchronous wrapper for ffprobe_duration.
    
    Uses subprocess.run instead of asyncio for use in sync contexts.
    """
    import subprocess
    
    if not file_path.exists():
        return None
    
    if not check_ffprobe_available():
        return None
    
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(file_path),
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        
        data = json.loads(result.stdout)
        duration_str = data.get("format", {}).get("duration")
        return float(duration_str) if duration_str else None
    except Exception:
        return None


async def estimate_mp3_size_from_file(
    file_path: Path,
    quality: ConversionQuality,
    fallback_duration_seconds: int | None = None,
) -> int:
    """Estimate MP3 size by probing the actual file duration.
    
    This is more accurate than estimate_mp3_size() because it uses
    ffprobe to get the real duration instead of trusting API metadata.
    
    Args:
        file_path: Path to the source audio file.
        quality: Quality preset for conversion.
        fallback_duration_seconds: Duration to use if ffprobe fails.
        
    Returns:
        Estimated file size in bytes.
    """
    if quality == ConversionQuality.DISABLED:
        # Return actual file size if no conversion
        if file_path.exists():
            return file_path.stat().st_size
        return 0
    
    # Try to get actual duration via ffprobe
    duration = await ffprobe_duration(file_path)
    
    if duration is None and fallback_duration_seconds:
        logger.debug(f"Using fallback duration {fallback_duration_seconds}s for {file_path.name}")
        duration = float(fallback_duration_seconds)
    
    if duration is None:
        logger.warning(f"Cannot estimate size for {file_path.name}: no duration available")
        # Return original file size as very rough fallback
        if file_path.exists():
            return file_path.stat().st_size
        return 0
    
    return _calculate_mp3_size(duration, quality)


def _calculate_mp3_size(duration_seconds: float, quality: ConversionQuality) -> int:
    """Calculate MP3 file size from duration and quality.
    
    Args:
        duration_seconds: Track duration in seconds.
        quality: Quality preset.
        
    Returns:
        Estimated file size in bytes.
    """
    if quality == ConversionQuality.DISABLED:
        return 0

    preset = QUALITY_PRESETS.get(quality)
    if not preset:
        return 0

    # Parse bitrate string like "320k" -> 320000 bits per second
    bitrate_str = preset["bitrate"]
    bitrate_bps = int(bitrate_str.replace("k", "")) * 1000

    # Size = (bitrate in bits/sec * duration in sec) / 8 bits per byte
    raw_size = (bitrate_bps * duration_seconds) / 8

    # Add ~5% overhead for MP3 framing, ID3 tags, and padding
    # (2% was too conservative based on real-world testing)
    estimated = int(raw_size * 1.05)
    
    logger.debug(
        f"MP3 size estimate: {duration_seconds:.1f}s @ {bitrate_str} = "
        f"{estimated} bytes ({estimated / 1024 / 1024:.2f} MB)"
    )
    
    return estimated


def estimate_mp3_size(duration_seconds: int, quality: ConversionQuality) -> int:
    """Estimate the MP3 file size after conversion based on duration.
    
    WARNING: This uses the provided duration which may come from API metadata
    that can be inaccurate. For local files, use estimate_mp3_size_from_file()
    which probes the actual file duration via ffprobe.

    Args:
        duration_seconds: Track duration in seconds (from API metadata).
        quality: Quality preset to estimate for.

    Returns:
        Estimated file size in bytes.
    """
    if quality == ConversionQuality.DISABLED:
        return 0
    
    # Log a warning about potential inaccuracy
    logger.debug(
        f"estimate_mp3_size: Using API duration {duration_seconds}s - "
        "this may be inaccurate. Consider using estimate_mp3_size_from_file() for local files."
    )
    
    return _calculate_mp3_size(float(duration_seconds), quality)


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


# =============================================================================
# WAV Conversion for Audio CDs (Red Book)
# =============================================================================

# Audio CD requirements: 16-bit, 44.1kHz, stereo PCM
AUDIO_CD_SAMPLE_RATE = 44100
AUDIO_CD_BIT_DEPTH = 16
AUDIO_CD_CHANNELS = 2
AUDIO_CD_BYTES_PER_SECOND = AUDIO_CD_SAMPLE_RATE * (AUDIO_CD_BIT_DEPTH // 8) * AUDIO_CD_CHANNELS  # 176400


def estimate_wav_size(duration_seconds: float) -> int:
    """Estimate WAV file size for audio CD format.
    
    Audio CDs use 16-bit, 44.1kHz, stereo PCM which is exactly
    176,400 bytes per second of audio.
    
    Args:
        duration_seconds: Track duration in seconds.
        
    Returns:
        Estimated WAV file size in bytes.
    """
    # WAV header is typically 44 bytes
    header_size = 44
    audio_size = int(duration_seconds * AUDIO_CD_BYTES_PER_SECOND)
    return header_size + audio_size


async def estimate_wav_size_from_file(
    file_path: Path,
    fallback_duration_seconds: float | None = None,
) -> int:
    """Estimate WAV size by probing the actual file duration.
    
    Args:
        file_path: Path to the source audio file.
        fallback_duration_seconds: Duration to use if ffprobe fails.
        
    Returns:
        Estimated WAV file size in bytes.
    """
    # Try to get actual duration via ffprobe
    duration = await ffprobe_duration(file_path)
    
    if duration is None and fallback_duration_seconds:
        logger.debug(f"Using fallback duration {fallback_duration_seconds}s for {file_path.name}")
        duration = fallback_duration_seconds
    
    if duration is None:
        logger.warning(f"Cannot estimate WAV size for {file_path.name}: no duration available")
        # Rough fallback: assume original file is comparable
        if file_path.exists():
            # WAV is typically 10x larger than MP3
            return file_path.stat().st_size * 10
        return 0
    
    return estimate_wav_size(duration)


class WavConverter:
    """Converts audio files to WAV format for audio CD burning.
    
    Audio CDs require 16-bit, 44.1kHz, stereo PCM audio. This converter
    ensures all audio is in the correct format for Red Book audio CDs.
    
    Example:
        converter = WavConverter(output_dir=Path("/tmp/navidisc/wav"))
        
        converted_paths = await converter.convert_many(
            source_paths,
            progress_callback=lambda p: print(f"Converting: {p.filename}")
        )
    """
    
    def __init__(self, output_dir: Path):
        """Initialize the WAV converter.
        
        Args:
            output_dir: Directory to write converted WAV files.
        """
        self.output_dir = output_dir
    
    def prepare(self) -> None:
        """Prepare the output directory."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def convert(self, source_path: Path) -> Path:
        """Convert a single audio file to CD-quality WAV.
        
        Args:
            source_path: Path to the source audio file.
            
        Returns:
            Path to the converted WAV file.
            
        Raises:
            ConversionError: If conversion fails.
        """
        if not source_path.exists():
            raise ConversionError(f"Source file not found: {source_path}", source_path)
        
        # Output path
        output_path = self.output_dir / f"{source_path.stem}.wav"
        
        # Build ffmpeg command for CD-quality WAV
        # -ar 44100: sample rate 44.1kHz
        # -ac 2: stereo
        # -sample_fmt s16: 16-bit signed PCM
        # -f wav: output format
        cmd = [
            "ffmpeg",
            "-i", str(source_path),
            "-ar", str(AUDIO_CD_SAMPLE_RATE),
            "-ac", str(AUDIO_CD_CHANNELS),
            "-sample_fmt", "s16",
            "-f", "wav",
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
                    f"ffmpeg WAV conversion failed for {source_path.name}: {error_msg}",
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
            raise ConversionError(f"WAV conversion failed: {e}", source_path)
    
    async def convert_many(
        self,
        track_paths: dict[str, Path],
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Path]:
        """Convert multiple audio files to CD-quality WAV.
        
        Args:
            track_paths: Mapping of track IDs to source file paths.
            progress_callback: Optional callback for progress updates.
            
        Returns:
            Mapping of track IDs to converted WAV file paths.
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
