"""Tests for the audio converter module."""

import pytest

from navidisc.media.converter import (
    AudioConverter,
    ConversionError,
    QUALITY_PRESETS,
)
from navidisc.models import ConversionQuality


class TestQualityPresets:
    """Tests for quality preset configuration."""
    
    def test_all_quality_levels_defined(self):
        """Test that all quality levels have presets defined."""
        for quality in ConversionQuality:
            if quality != ConversionQuality.DISABLED:
                assert quality in QUALITY_PRESETS
    
    def test_best_quality_highest_bitrate(self):
        """Test that best quality has highest bitrate."""
        best = QUALITY_PRESETS[ConversionQuality.BEST]
        high = QUALITY_PRESETS[ConversionQuality.HIGH]
        medium = QUALITY_PRESETS[ConversionQuality.MEDIUM]
        small = QUALITY_PRESETS[ConversionQuality.SMALL]
        
        assert int(best["bitrate"].rstrip("k")) >= int(high["bitrate"].rstrip("k"))
        assert int(high["bitrate"].rstrip("k")) >= int(medium["bitrate"].rstrip("k"))
        assert int(medium["bitrate"].rstrip("k")) >= int(small["bitrate"].rstrip("k"))
    
    def test_preset_has_required_fields(self):
        """Test that all presets have required fields."""
        for quality, preset in QUALITY_PRESETS.items():
            assert "bitrate" in preset
            assert "description" in preset


class TestAudioConverter:
    """Tests for AudioConverter class."""
    
    def test_disabled_quality_raises_error(self):
        """Test that disabled quality raises ValueError."""
        with pytest.raises(ValueError, match="DISABLED"):
            AudioConverter(
                quality=ConversionQuality.DISABLED,
                output_dir=None,
            )
    
    def test_needs_conversion_flac(self, tmp_path):
        """Test that FLAC files need conversion."""
        converter = AudioConverter(
            quality=ConversionQuality.HIGH,
            output_dir=tmp_path,
        )
        flac_file = tmp_path / "test.flac"
        flac_file.touch()
        
        assert converter.needs_conversion(flac_file) is True
    
    def test_needs_conversion_mp3(self, tmp_path):
        """Test that MP3 files don't need conversion."""
        converter = AudioConverter(
            quality=ConversionQuality.HIGH,
            output_dir=tmp_path,
        )
        mp3_file = tmp_path / "test.mp3"
        mp3_file.touch()
        
        assert converter.needs_conversion(mp3_file) is False
    
    def test_needs_conversion_wav(self, tmp_path):
        """Test that WAV files need conversion."""
        converter = AudioConverter(
            quality=ConversionQuality.HIGH,
            output_dir=tmp_path,
        )
        wav_file = tmp_path / "test.wav"
        wav_file.touch()
        
        assert converter.needs_conversion(wav_file) is True
    
    def test_converter_has_quality_setting(self, tmp_path):
        """Test that converter stores quality setting."""
        converter = AudioConverter(
            quality=ConversionQuality.HIGH,
            output_dir=tmp_path,
        )
        assert converter.quality == ConversionQuality.HIGH
    
    def test_converter_has_output_dir(self, tmp_path):
        """Test that converter stores output directory."""
        converter = AudioConverter(
            quality=ConversionQuality.HIGH,
            output_dir=tmp_path,
        )
        assert converter.output_dir == tmp_path
