"""Core data models for Navidisc.

These models are designed to be:
- Serializable (JSON/YAML compatible via Pydantic)
- Immutable where possible
- AI-friendly with clear, explicit fields
"""

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DiscType(StrEnum):
    """Type of disc to burn."""
    DATA = "data"
    AUDIO = "audio"


class DownloadMode(StrEnum):
    """How to obtain track files."""
    LOCAL_ONLY = "local-only"
    DOWNLOAD_IF_MISSING = "download-if-missing"
    DOWNLOAD_ALWAYS = "download-always"


class ConversionQuality(StrEnum):
    """Audio conversion quality presets."""
    DISABLED = "disabled"  # No conversion
    BEST = "best"  # 320kbps CBR, highest quality
    HIGH = "high"  # 256kbps CBR
    MEDIUM = "medium"  # 192kbps CBR, good balance
    SMALL = "small"  # 128kbps CBR, smallest size


class MediaType(StrEnum):
    """Physical disc media type with max speed rating."""
    # CD-R Standard (12 cm) - various speed ratings
    CD_R_1X = "cd-r-1x"
    CD_R_2X = "cd-r-2x"
    CD_R_4X = "cd-r-4x"
    CD_R_8X = "cd-r-8x"
    CD_R_12X = "cd-r-12x"
    CD_R_16X = "cd-r-16x"
    CD_R_20X = "cd-r-20x"
    CD_R_24X = "cd-r-24x"
    CD_R_32X = "cd-r-32x"
    CD_R_40X = "cd-r-40x"
    CD_R_48X = "cd-r-48x"
    CD_R_52X = "cd-r-52x"
    # CD-R Mini (8 cm)
    CD_R_MINI_4X = "cd-r-mini-4x"
    CD_R_MINI_8X = "cd-r-mini-8x"
    CD_R_MINI_12X = "cd-r-mini-12x"
    CD_R_MINI_16X = "cd-r-mini-16x"
    CD_R_MINI_24X = "cd-r-mini-24x"
    # CD-RW Standard - various speed ratings
    CD_RW_1X = "cd-rw-1x"
    CD_RW_2X = "cd-rw-2x"
    CD_RW_4X = "cd-rw-4x"
    CD_RW_8X = "cd-rw-8x"
    CD_RW_10X = "cd-rw-10x"
    CD_RW_12X = "cd-rw-12x"
    CD_RW_16X = "cd-rw-16x"
    CD_RW_20X = "cd-rw-20x"
    CD_RW_24X = "cd-rw-24x"
    CD_RW_32X = "cd-rw-32x"
    # CD-RW Mini (8 cm)
    CD_RW_MINI_4X = "cd-rw-mini-4x"
    CD_RW_MINI_8X = "cd-rw-mini-8x"
    CD_RW_MINI_10X = "cd-rw-mini-10x"
    # DVD-R
    DVD_R_1X = "dvd-r-1x"
    DVD_R_2X = "dvd-r-2x"
    DVD_R_4X = "dvd-r-4x"
    DVD_R_8X = "dvd-r-8x"
    DVD_R_16X = "dvd-r-16x"
    # DVD+R
    DVD_PLUS_R_2_4X = "dvd+r-2.4x"
    DVD_PLUS_R_4X = "dvd+r-4x"
    DVD_PLUS_R_8X = "dvd+r-8x"
    DVD_PLUS_R_16X = "dvd+r-16x"
    # DVD-RW
    DVD_RW_1X = "dvd-rw-1x"
    DVD_RW_2X = "dvd-rw-2x"
    DVD_RW_4X = "dvd-rw-4x"
    DVD_RW_6X = "dvd-rw-6x"
    # DVD+RW
    DVD_PLUS_RW_2_4X = "dvd+rw-2.4x"
    DVD_PLUS_RW_4X = "dvd+rw-4x"
    DVD_PLUS_RW_8X = "dvd+rw-8x"
    # DVD Dual Layer
    DVD_R_DL_2X = "dvd-r-dl-2x"
    DVD_R_DL_4X = "dvd-r-dl-4x"
    DVD_R_DL_8X = "dvd-r-dl-8x"
    DVD_PLUS_R_DL_2_4X = "dvd+r-dl-2.4x"
    DVD_PLUS_R_DL_4X = "dvd+r-dl-4x"
    DVD_PLUS_R_DL_8X = "dvd+r-dl-8x"
    # DVD-RAM
    DVD_RAM_2X = "dvd-ram-2x"
    DVD_RAM_3X = "dvd-ram-3x"
    DVD_RAM_5X = "dvd-ram-5x"
    # DVD Mini (8 cm)
    DVD_R_MINI_2X = "dvd-r-mini-2x"
    DVD_R_MINI_4X = "dvd-r-mini-4x"
    DVD_RW_MINI_2X = "dvd-rw-mini-2x"
    # Blu-ray BD-R
    BD_R_1X = "bd-r-1x"
    BD_R_2X = "bd-r-2x"
    BD_R_4X = "bd-r-4x"
    BD_R_6X = "bd-r-6x"
    BD_R_8X = "bd-r-8x"
    BD_R_10X = "bd-r-10x"
    BD_R_12X = "bd-r-12x"
    BD_R_16X = "bd-r-16x"
    # Blu-ray BD-RE (rewritable)
    BD_RE_1X = "bd-re-1x"
    BD_RE_2X = "bd-re-2x"
    # BDXL (high capacity)
    BD_R_XL_4X = "bd-r-xl-4x"
    BD_R_XL_6X = "bd-r-xl-6x"
    BD_RE_XL_2X = "bd-re-xl-2x"
    # Auto-detect
    AUTO = "auto"  # Detect from inserted media


class WriteSpeed(StrEnum):
    """Write speed presets."""
    AUTO = "auto"  # Let drive determine optimal speed
    MAX = "max"  # Use maximum speed for media type
    SAFE = "safe"  # Use conservative speed for reliability
    CUSTOM = "custom"  # Use custom speed value


class AudioCDBurnMode(StrEnum):
    """Burn mode for audio CDs."""
    TAO = "tao"  # Track-at-once: allows pausing between tracks (gaps enforced)
    DAO = "dao"  # Disc-at-once: writes entire disc in one pass (gapless possible)


class OrchestratorState(StrEnum):
    """States for the main workflow state machine."""
    INIT = "init"
    AUTHENTICATED = "authenticated"
    PLAYLIST_RESOLVED = "playlist_resolved"
    PLANNED = "planned"
    STAGING_DISC = "staging_disc"
    WAIT_FOR_DISC = "wait_for_disc"
    BURNING_DISC = "burning_disc"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    ERROR = "error"


class BurnStatus(StrEnum):
    """Result status of a burn operation."""
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


# =============================================================================
# API Models (Subsonic/Navidrome)
# =============================================================================

class Artist(BaseModel):
    """Artist information from Subsonic API."""
    id: str
    name: str


class Album(BaseModel):
    """Album information from Subsonic API."""
    id: str
    name: str
    artist: str | None = None
    artist_id: str | None = None
    year: int | None = None
    genre: str | None = None


class Track(BaseModel):
    """A single track with all metadata needed for planning and staging."""
    id: str
    title: str
    artist: str
    album: str | None = None
    track_number: int | None = None
    duration_seconds: int = Field(ge=0)
    bitrate: int | None = None  # kbps
    size_bytes: int | None = None
    format: str | None = None  # flac, mp3, etc.
    path: str | None = None  # Original path in library
    stream_url: str | None = None

    @property
    def display_name(self) -> str:
        """Human-readable name for the track."""
        return f"{self.artist} - {self.title}"


class Playlist(BaseModel):
    """A playlist containing ordered tracks."""
    id: str
    name: str
    track_count: int
    duration_seconds: int
    created: datetime | None = None
    changed: datetime | None = None
    owner: str | None = None
    public: bool = False
    tracks: list[Track] = Field(default_factory=list)


# =============================================================================
# Planning Models
# =============================================================================

class DiscPlan(BaseModel):
    """Plan for a single disc."""
    disc_number: int
    track_ids: list[str]
    total_size_bytes: int = 0
    total_duration_seconds: int = 0

    @property
    def track_count(self) -> int:
        return len(self.track_ids)


class BurnPlan(BaseModel):
    """Complete plan for burning a playlist to one or more discs."""
    playlist_id: str
    playlist_name: str
    disc_type: DiscType
    disc_capacity_bytes: int | None = None  # For data discs
    disc_capacity_seconds: int | None = None  # For audio discs
    discs: list[DiscPlan] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def total_discs(self) -> int:
        return len(self.discs)


# =============================================================================
# Staging Models
# =============================================================================

class StagedFile(BaseModel):
    """A file that has been staged for burning."""
    track_id: str
    source_path: Path
    staged_path: Path
    filename: str
    size_bytes: int
    is_hardlink: bool = False


class StagedDisc(BaseModel):
    """A disc directory ready for burning."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    disc_number: int
    directory: Path
    files: list[StagedFile] = Field(default_factory=list)
    total_size_bytes: int = 0


# =============================================================================
# Burn Result Models
# =============================================================================

class BurnResult(BaseModel):
    """Result of a burn operation."""
    disc_number: int
    status: BurnStatus
    device: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    command_output: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


# =============================================================================
# Error Models
# =============================================================================

class NavidiscError(BaseModel):
    """Structured error for debugging and recovery."""
    stage: OrchestratorState
    error_type: str
    message: str
    suggested_action: str | None = None
    recoverable: bool = False
    context: dict = Field(default_factory=dict)


# =============================================================================
# Session State
# =============================================================================

class SessionState(BaseModel):
    """Complete state of a burn session for persistence/recovery."""
    session_id: str
    state: OrchestratorState
    playlist_id: str | None = None
    burn_plan: BurnPlan | None = None
    current_disc: int = 0
    burn_results: list[BurnResult] = Field(default_factory=list)
    errors: list[NavidiscError] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
