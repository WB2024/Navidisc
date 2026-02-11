"""CUE sheet and TOC file generation for audio CD burning.

This module provides:
- CUE sheet generation for wodim/cdrecord
- TOC file generation for cdrdao
- CD-TEXT embedding support
- Gap/pregap control

Audio CD Format Reference:
- 44.1kHz, 16-bit, stereo PCM
- 75 frames per second (1 frame = 1/75 second = 2352 bytes)
- Standard 2-second pregap before each track (except track 1)
- DAO mode allows gapless or custom gaps
"""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Audio CD constants
FRAMES_PER_SECOND = 75
BYTES_PER_FRAME = 2352  # 44100 * 2 * 2 / 75


@dataclass
class AudioTrack:
    """Represents a track for audio CD burning."""
    
    track_number: int
    file_path: Path
    title: str
    artist: str
    duration_seconds: float
    album: str = ""
    
    @property
    def duration_frames(self) -> int:
        """Duration in CD frames (75 per second)."""
        return int(self.duration_seconds * FRAMES_PER_SECOND)
    
    @property
    def duration_msf(self) -> str:
        """Duration in MM:SS:FF format (minutes:seconds:frames)."""
        total_frames = self.duration_frames
        minutes = total_frames // (60 * FRAMES_PER_SECOND)
        remaining = total_frames % (60 * FRAMES_PER_SECOND)
        seconds = remaining // FRAMES_PER_SECOND
        frames = remaining % FRAMES_PER_SECOND
        return f"{minutes:02d}:{seconds:02d}:{frames:02d}"


def generate_cue_sheet(
    tracks: list[AudioTrack],
    album_title: str,
    album_artist: str = "",
    gap_seconds: int = 2,
    include_cd_text: bool = True,
) -> str:
    """Generate a CUE sheet for audio CD burning with wodim/cdrecord.
    
    CUE sheets define the track layout and metadata for audio CDs.
    
    Args:
        tracks: List of AudioTrack objects to burn.
        album_title: Album/disc title for CD-TEXT.
        album_artist: Album artist for CD-TEXT.
        gap_seconds: Gap between tracks in seconds (0-8).
        include_cd_text: Whether to include CD-TEXT metadata.
        
    Returns:
        CUE sheet content as a string.
    """
    lines = []
    
    # CD-TEXT header
    if include_cd_text:
        lines.append(f'TITLE "{_escape_cue_string(album_title)}"')
        if album_artist:
            lines.append(f'PERFORMER "{_escape_cue_string(album_artist)}"')
    
    # Each track
    for track in tracks:
        # FILE directive - each track is in its own WAV file
        lines.append(f'FILE "{track.file_path.name}" WAVE')
        
        # TRACK directive
        lines.append(f"  TRACK {track.track_number:02d} AUDIO")
        
        # CD-TEXT for track
        if include_cd_text:
            lines.append(f'    TITLE "{_escape_cue_string(track.title)}"')
            lines.append(f'    PERFORMER "{_escape_cue_string(track.artist)}"')
        
        # Pregap (gap before track)
        # Track 1 doesn't have a pregap in standard CUE format
        if track.track_number > 1 and gap_seconds > 0:
            lines.append(f"    PREGAP {_seconds_to_msf(gap_seconds)}")
        
        # INDEX 01 is the start of audio (always at 00:00:00 for separate files)
        lines.append("    INDEX 01 00:00:00")
    
    return "\n".join(lines) + "\n"


def generate_toc_file(
    tracks: list[AudioTrack],
    album_title: str,
    album_artist: str = "",
    gap_seconds: int = 2,
    include_cd_text: bool = True,
) -> str:
    """Generate a TOC file for audio CD burning with cdrdao.
    
    TOC (Table of Contents) is cdrdao's native format and offers
    more control over the disc layout than CUE sheets.
    
    Args:
        tracks: List of AudioTrack objects to burn.
        album_title: Album/disc title for CD-TEXT.
        album_artist: Album artist for CD-TEXT.
        gap_seconds: Gap between tracks in seconds (0-8).
        include_cd_text: Whether to include CD-TEXT metadata.
        
    Returns:
        TOC file content as a string.
    """
    lines = []
    
    # Disc type
    lines.append("CD_DA")
    lines.append("")
    
    # CD-TEXT block
    if include_cd_text:
        lines.append("CD_TEXT {")
        lines.append("  LANGUAGE_MAP {")
        lines.append("    0 : EN")
        lines.append("  }")
        lines.append("  LANGUAGE 0 {")
        lines.append(f'    TITLE "{_escape_toc_string(album_title)}"')
        if album_artist:
            lines.append(f'    PERFORMER "{_escape_toc_string(album_artist)}"')
        lines.append("  }")
        lines.append("}")
        lines.append("")
    
    # Each track
    for track in tracks:
        lines.append("// " + "-" * 60)
        lines.append(f"// Track {track.track_number}: {track.title}")
        lines.append("// " + "-" * 60)
        lines.append("")
        lines.append("TRACK AUDIO")
        
        # CD-TEXT for this track
        if include_cd_text:
            lines.append("CD_TEXT {")
            lines.append("  LANGUAGE 0 {")
            lines.append(f'    TITLE "{_escape_toc_string(track.title)}"')
            lines.append(f'    PERFORMER "{_escape_toc_string(track.artist)}"')
            lines.append("  }")
            lines.append("}")
        
        # Pregap (silence before track)
        if track.track_number > 1 and gap_seconds > 0:
            lines.append(f"PREGAP {_seconds_to_msf(gap_seconds)}")
        
        # Audio file
        lines.append(f'FILE "{track.file_path}" 0')
        lines.append("")
    
    return "\n".join(lines)


def _escape_cue_string(s: str) -> str:
    """Escape a string for use in a CUE sheet."""
    # Replace double quotes with single quotes
    return s.replace('"', "'").replace("\\", "")


def _escape_toc_string(s: str) -> str:
    """Escape a string for use in a TOC file."""
    # Replace double quotes and backslashes
    return s.replace('"', "'").replace("\\", "\\\\")


def _seconds_to_msf(seconds: int) -> str:
    """Convert seconds to MM:SS:00 format for CUE/TOC files."""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}:00"


def write_cue_sheet(
    output_path: Path,
    tracks: list[AudioTrack],
    album_title: str,
    album_artist: str = "",
    gap_seconds: int = 2,
    include_cd_text: bool = True,
) -> Path:
    """Write a CUE sheet file.
    
    Args:
        output_path: Path for the output .cue file.
        tracks: List of AudioTrack objects.
        album_title: Album/disc title.
        album_artist: Album artist.
        gap_seconds: Gap between tracks.
        include_cd_text: Include CD-TEXT metadata.
        
    Returns:
        Path to the written CUE file.
    """
    content = generate_cue_sheet(
        tracks=tracks,
        album_title=album_title,
        album_artist=album_artist,
        gap_seconds=gap_seconds,
        include_cd_text=include_cd_text,
    )
    
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Wrote CUE sheet: {output_path}")
    return output_path


def write_toc_file(
    output_path: Path,
    tracks: list[AudioTrack],
    album_title: str,
    album_artist: str = "",
    gap_seconds: int = 2,
    include_cd_text: bool = True,
) -> Path:
    """Write a TOC file for cdrdao.
    
    Args:
        output_path: Path for the output .toc file.
        tracks: List of AudioTrack objects.
        album_title: Album/disc title.
        album_artist: Album artist.
        gap_seconds: Gap between tracks.
        include_cd_text: Include CD-TEXT metadata.
        
    Returns:
        Path to the written TOC file.
    """
    content = generate_toc_file(
        tracks=tracks,
        album_title=album_title,
        album_artist=album_artist,
        gap_seconds=gap_seconds,
        include_cd_text=include_cd_text,
    )
    
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Wrote TOC file: {output_path}")
    return output_path
