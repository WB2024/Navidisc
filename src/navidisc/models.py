"""Core data models for Navidisc.

These models are designed to be:
- Serializable (JSON/YAML compatible via Pydantic)
- Immutable where possible
- AI-friendly with clear, explicit fields
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class DiscType(str, Enum):
    """Type of disc to burn."""
    DATA = "data"
    AUDIO = "audio"


class DownloadMode(str, Enum):
    """How to obtain track files."""
    LOCAL_ONLY = "local-only"
    DOWNLOAD_IF_MISSING = "download-if-missing"
    DOWNLOAD_ALWAYS = "download-always"


class OrchestratorState(str, Enum):
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


class BurnStatus(str, Enum):
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
    artist: Optional[str] = None
    artist_id: Optional[str] = None
    year: Optional[int] = None
    genre: Optional[str] = None


class Track(BaseModel):
    """A single track with all metadata needed for planning and staging."""
    id: str
    title: str
    artist: str
    album: Optional[str] = None
    track_number: Optional[int] = None
    duration_seconds: int = Field(ge=0)
    bitrate: Optional[int] = None  # kbps
    size_bytes: Optional[int] = None
    format: Optional[str] = None  # flac, mp3, etc.
    path: Optional[str] = None  # Original path in library
    stream_url: Optional[str] = None

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
    created: Optional[datetime] = None
    changed: Optional[datetime] = None
    owner: Optional[str] = None
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
    disc_capacity_bytes: Optional[int] = None  # For data discs
    disc_capacity_seconds: Optional[int] = None  # For audio discs
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
    disc_number: int
    directory: Path
    files: list[StagedFile] = Field(default_factory=list)
    total_size_bytes: int = 0

    class Config:
        arbitrary_types_allowed = True


# =============================================================================
# Burn Result Models
# =============================================================================

class BurnResult(BaseModel):
    """Result of a burn operation."""
    disc_number: int
    status: BurnStatus
    device: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    command_output: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
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
    suggested_action: Optional[str] = None
    recoverable: bool = False
    context: dict = Field(default_factory=dict)


# =============================================================================
# Session State
# =============================================================================

class SessionState(BaseModel):
    """Complete state of a burn session for persistence/recovery."""
    session_id: str
    state: OrchestratorState
    playlist_id: Optional[str] = None
    burn_plan: Optional[BurnPlan] = None
    current_disc: int = 0
    burn_results: list[BurnResult] = Field(default_factory=list)
    errors: list[NavidiscError] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
