"""Tests for the drive detection and speed calculation module."""

import pytest

from navidisc.burner.drive import (
    MEDIA_SPECS,
    calculate_write_speed,
    format_speed_for_display,
    get_media_family,
    get_media_max_speed,
    get_media_capacity,
    DriveInfo,
    SpeedRecommendation,
)
from navidisc.models import MediaType, WriteSpeed


class TestMediaSpecs:
    """Tests for media specifications."""
    
    def test_all_media_types_have_specs(self):
        """Test that all media types except AUTO have specs defined."""
        for media_type in MediaType:
            if media_type != MediaType.AUTO:
                assert media_type in MEDIA_SPECS, f"Missing spec for {media_type}"
    
    def test_cd_base_speed_is_correct(self):
        """Test that CD base speed is 150 KB/s."""
        for media_type, spec in MEDIA_SPECS.items():
            if spec["family"] == "cd":
                assert spec["base"] == 150
    
    def test_dvd_base_speed_is_correct(self):
        """Test that DVD base speed is 1350 KB/s."""
        for media_type, spec in MEDIA_SPECS.items():
            if spec["family"] == "dvd":
                assert spec["base"] == 1350
    
    def test_bd_base_speed_is_correct(self):
        """Test that Blu-ray base speed is 4500 KB/s."""
        for media_type, spec in MEDIA_SPECS.items():
            if spec["family"] == "bd":
                assert spec["base"] == 4500


class TestCalculateWriteSpeed:
    """Tests for speed calculation logic."""
    
    def test_auto_preset_uses_seventy_percent(self):
        """Test that AUTO preset uses ~70% of max speed."""
        result = calculate_write_speed(
            write_speed_preset=WriteSpeed.AUTO,
            media_type=MediaType.CD_R_52X,
            drive_info=None,
            custom_speed=None,
        )
        # 70% of 52x = 36.4, rounded
        assert 35 <= result.speed_x <= 40
    
    def test_safe_preset_uses_fifty_percent(self):
        """Test that SAFE preset uses ~50% of max speed."""
        result = calculate_write_speed(
            write_speed_preset=WriteSpeed.SAFE,
            media_type=MediaType.CD_R_52X,
            drive_info=None,
            custom_speed=None,
        )
        # 50% of 52x = 26
        assert 24 <= result.speed_x <= 28
    
    def test_max_preset_uses_full_speed(self):
        """Test that MAX preset uses full speed."""
        result = calculate_write_speed(
            write_speed_preset=WriteSpeed.MAX,
            media_type=MediaType.CD_R_52X,
            drive_info=None,
            custom_speed=None,
        )
        assert result.speed_x == 52
    
    def test_custom_speed_is_used(self):
        """Test that custom speed overrides preset."""
        result = calculate_write_speed(
            write_speed_preset=WriteSpeed.CUSTOM,
            media_type=MediaType.CD_R_52X,
            drive_info=None,
            custom_speed=16,
        )
        assert result.speed_x == 16
    
    def test_custom_without_value_falls_back_to_auto(self):
        """Test that CUSTOM without a value falls back to AUTO."""
        result = calculate_write_speed(
            write_speed_preset=WriteSpeed.CUSTOM,
            media_type=MediaType.CD_R_52X,
            drive_info=None,
            custom_speed=None,
        )
        # Should use AUTO logic
        assert 35 <= result.speed_x <= 40
    
    def test_drive_limits_respected(self):
        """Test that drive max speed limits the result."""
        drive = DriveInfo(
            device="/dev/sr0",
            vendor="Test",
            model="Slow Drive",
            can_write_cd=True,
            can_write_dvd=True,
            can_write_bd=False,
            max_cd_write_speed=24,
            max_dvd_write_speed=8,
            max_bd_write_speed=None,
            current_media=None,
            media_writable=False,
        )
        result = calculate_write_speed(
            write_speed_preset=WriteSpeed.MAX,
            media_type=MediaType.CD_R_52X,
            drive_info=drive,
            custom_speed=None,
        )
        # Drive only supports 24x, so max should be 24
        assert result.speed_x == 24
    
    def test_auto_media_uses_drive_decision(self):
        """Test that AUTO media type lets drive decide."""
        result = calculate_write_speed(
            write_speed_preset=WriteSpeed.AUTO,
            media_type=MediaType.AUTO,
            drive_info=None,
            custom_speed=None,
        )
        # AUTO media should return 0 (let drive decide)
        assert result.speed_x == 0


class TestFormatSpeedForDisplay:
    """Tests for speed display formatting."""
    
    def test_cd_speed_formatting(self):
        """Test CD speed display format."""
        result = format_speed_for_display(16, MediaType.CD_R_52X)
        assert "16x" in result
        assert "MB/s" in result
    
    def test_dvd_speed_formatting(self):
        """Test DVD speed display format."""
        result = format_speed_for_display(8, MediaType.DVD_R_16X)
        assert "8x" in result
    
    def test_bd_speed_formatting(self):
        """Test Blu-ray speed display format."""
        result = format_speed_for_display(6, MediaType.BD_R_6X)
        assert "6x" in result
    
    def test_auto_speed_formatting(self):
        """Test auto speed display format."""
        result = format_speed_for_display(0, MediaType.AUTO)
        assert "Auto" in result


class TestSpeedRecommendation:
    """Tests for SpeedRecommendation dataclass."""
    
    def test_recommendation_fields(self):
        """Test that SpeedRecommendation has expected fields."""
        rec = SpeedRecommendation(
            speed_x=16,
            speed_kbps=2400,
            reason="Test reason",
            media_type=MediaType.CD_R_52X,
            is_estimated=False,
        )
        assert rec.speed_x == 16
        assert rec.speed_kbps == 2400
        assert rec.reason == "Test reason"
        assert rec.media_type == MediaType.CD_R_52X
        assert rec.is_estimated is False


class TestHelperFunctions:
    """Tests for helper functions."""
    
    def test_get_media_family_cd(self):
        """Test CD family detection."""
        assert get_media_family(MediaType.CD_R_52X) == "cd"
        assert get_media_family(MediaType.CD_RW_24X) == "cd"
    
    def test_get_media_family_dvd(self):
        """Test DVD family detection."""
        assert get_media_family(MediaType.DVD_R_16X) == "dvd"
        assert get_media_family(MediaType.DVD_PLUS_R_8X) == "dvd"
    
    def test_get_media_family_bd(self):
        """Test Blu-ray family detection."""
        assert get_media_family(MediaType.BD_R_16X) == "bd"
        assert get_media_family(MediaType.BD_RE_2X) == "bd"
    
    def test_get_media_max_speed(self):
        """Test max speed retrieval."""
        multiplier, kbps = get_media_max_speed(MediaType.CD_R_52X)
        assert multiplier == 52
        assert kbps == 52 * 150
    
    def test_get_media_capacity(self):
        """Test capacity retrieval."""
        assert get_media_capacity(MediaType.CD_R_52X) == 700
        assert get_media_capacity(MediaType.DVD_R_16X) == 4700
        assert get_media_capacity(MediaType.BD_R_16X) == 25000
