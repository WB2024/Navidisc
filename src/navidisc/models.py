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
