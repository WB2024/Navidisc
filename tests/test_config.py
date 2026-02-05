"""Tests for the configuration system."""

import tempfile
from pathlib import Path

import pytest

from navidisc.config import (
    BurningConfig,
    MediaConfig,
    NavidiscConfig,
    NavidromeConfig,
    create_example_config,
    load_config,
    save_config,
)
from navidisc.models import DiscType, DownloadMode


class TestNavidromeConfig:
    """Tests for NavidromeConfig."""
    
    def test_url_trailing_slash_removed(self):
        """Test that trailing slashes are removed from URL."""
        config = NavidromeConfig(
            url="http://localhost:4533/",
            username="user",
            password="pass",
        )
        assert config.url == "http://localhost:4533"
    
    def test_default_api_version(self):
        """Test default API version."""
        config = NavidromeConfig(
            url="http://localhost:4533",
            username="user",
            password="pass",
        )
        assert config.api_version == "1.16.1"


class TestBurningConfig:
    """Tests for BurningConfig."""
    
    def test_disc_size_bytes_property(self):
        """Test disc size bytes calculation."""
        config = BurningConfig(disc_size_mb=700)
        assert config.disc_size_bytes == 700 * 1024 * 1024
    
    def test_audio_disc_seconds_property(self):
        """Test audio disc seconds calculation."""
        config = BurningConfig(audio_disc_minutes=80)
        assert config.audio_disc_seconds == 80 * 60
    
    def test_default_values(self):
        """Test default configuration values."""
        config = BurningConfig()
        assert config.device == "/dev/sr0"
        assert config.disc_type == DiscType.DATA
        assert config.disc_size_mb == 700
        assert config.verify_after_burn is True
        assert config.eject_after_burn is True


class TestMediaConfig:
    """Tests for MediaConfig."""
    
    def test_default_values(self):
        """Test default media configuration."""
        config = MediaConfig()
        assert config.download_mode == DownloadMode.DOWNLOAD_IF_MISSING
        assert config.use_hardlinks is True
        assert config.normalize_filenames is True


class TestConfigIO:
    """Tests for configuration file I/O."""
    
    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        config = NavidiscConfig(
            navidrome=NavidromeConfig(
                url="http://localhost:4533",
                username="testuser",
                password="testpass",
            ),
            burning=BurningConfig(
                disc_type=DiscType.AUDIO,
                disc_size_mb=650,
            ),
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            
            save_config(config, config_path)
            assert config_path.exists()
            
            loaded = load_config(config_path)
            assert loaded.navidrome.url == config.navidrome.url
            assert loaded.navidrome.username == config.navidrome.username
            assert loaded.burning.disc_type == DiscType.AUDIO
            assert loaded.burning.disc_size_mb == 650
    
    def test_load_nonexistent_file_raises(self):
        """Test that loading nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/config.yaml"))
    
    def test_create_example_config(self):
        """Test that example config is valid YAML."""
        import yaml
        
        example = create_example_config()
        data = yaml.safe_load(example)
        
        assert "navidrome" in data
        assert "burning" in data
        assert "media" in data
        assert data["navidrome"]["url"] == "http://localhost:4533"
