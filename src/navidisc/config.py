"""Configuration system for Navidisc.

Provides schema-validated, YAML-based configuration that is:
- Fully declarative
- Machine-readable and editable
- AI-friendly with clear defaults
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from navidisc.models import DiscType, DownloadMode


class NavidromeConfig(BaseModel):
    """Navidrome/Subsonic server connection settings."""
    url: str = Field(description="Navidrome server URL")
    username: str = Field(description="Subsonic API username")
    password: str = Field(description="Subsonic API password or token")
    api_version: str = Field(default="1.16.1", description="Subsonic API version")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL doesn't have trailing slash."""
        return v.rstrip("/")


class BurningConfig(BaseModel):
    """Disc burning settings."""
    device: str = Field(default="/dev/sr0", description="Optical drive device path")
    disc_type: DiscType = Field(default=DiscType.DATA, description="Type of disc to create")
    disc_size_mb: int = Field(default=700, ge=100, le=9000, description="Disc capacity in MB")
    audio_disc_minutes: int = Field(default=80, ge=20, le=100, description="Audio CD capacity in minutes")
    write_speed: int | None = Field(default=None, description="Write speed (None for auto)")
    verify_after_burn: bool = Field(default=True, description="Verify disc after burning")
    eject_after_burn: bool = Field(default=True, description="Eject disc after burning")

    @property
    def disc_size_bytes(self) -> int:
        """Disc capacity in bytes."""
        return self.disc_size_mb * 1024 * 1024

    @property
    def audio_disc_seconds(self) -> int:
        """Audio disc capacity in seconds."""
        return self.audio_disc_minutes * 60


class MediaConfig(BaseModel):
    """Media handling settings."""
    staging_dir: Path = Field(
        default=Path("/tmp/navidisc"),
        description="Directory for staging files before burning"
    )
    download_mode: DownloadMode = Field(
        default=DownloadMode.DOWNLOAD_IF_MISSING,
        description="How to obtain track files"
    )
    use_hardlinks: bool = Field(
        default=True,
        description="Use hardlinks instead of copying when possible"
    )
    normalize_filenames: bool = Field(
        default=True,
        description="Normalize filenames for disc compatibility"
    )
    include_track_numbers: bool = Field(
        default=True,
        description="Prefix filenames with track numbers"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class LoggingConfig(BaseModel):
    """Logging settings."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="text", description="Log format: text or json")
    file: Path | None = Field(default=None, description="Log file path")


class NavidiscConfig(BaseModel):
    """Root configuration for Navidisc."""
    navidrome: NavidromeConfig
    burning: BurningConfig = Field(default_factory=BurningConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(path: Path) -> NavidiscConfig:
    """Load configuration from a YAML file.
    
    Args:
        path: Path to the configuration file.
        
    Returns:
        Validated NavidiscConfig instance.
        
    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValidationError: If config is invalid.
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return NavidiscConfig.model_validate(data)


def save_config(config: NavidiscConfig, path: Path) -> None:
    """Save configuration to a YAML file.
    
    Args:
        config: Configuration to save.
        path: Path to write the configuration file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict, handling Path objects
    data = config.model_dump(mode="json")

    with open(path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def get_default_config_path() -> Path:
    """Get the default configuration file path.
    
    Returns:
        Path to ~/.config/navidisc/config.yaml
    """
    return Path.home() / ".config" / "navidisc" / "config.yaml"


def create_example_config() -> str:
    """Generate an example configuration file.
    
    Returns:
        YAML string with example configuration.
    """
    example = """# Navidisc Configuration
# See documentation for all available options

navidrome:
  url: http://localhost:4533
  username: your_username
  password: your_password

burning:
  device: /dev/sr0
  disc_type: data  # data or audio
  disc_size_mb: 700
  verify_after_burn: true
  eject_after_burn: true

media:
  staging_dir: /tmp/navidisc
  download_mode: download-if-missing  # local-only, download-if-missing, download-always
  use_hardlinks: true
  normalize_filenames: true
  include_track_numbers: true

logging:
  level: INFO
  format: text  # text or json
"""
    return example
