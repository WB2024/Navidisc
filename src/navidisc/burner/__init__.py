"""Burner module for Navidisc.

Provides disc burning abstraction and backend implementations.
"""

from navidisc.burner.adapter import (
    AudioCDBackend,
    BurnerAdapter,
    DryRunBackend,
    GrowIsofsBackend,
    WodimBackend,
    detect_backend,
)
from navidisc.burner.cuesheet import (
    AudioTrack,
    generate_cue_sheet,
    generate_toc_file,
    write_cue_sheet,
    write_toc_file,
)
from navidisc.burner.drive import (
    DriveInfo,
    SpeedRecommendation,
    calculate_write_speed,
    detect_blank_media,
    detect_drive_info,
    format_speed_for_display,
    get_media_capacity,
    get_media_max_speed,
    MEDIA_SPECS,
)

__all__ = [
    "AudioCDBackend",
    "BurnerAdapter",
    "GrowIsofsBackend",
    "WodimBackend",
    "DryRunBackend",
    "detect_backend",
    "AudioTrack",
    "generate_cue_sheet",
    "generate_toc_file",
    "write_cue_sheet",
    "write_toc_file",
    "DriveInfo",
    "SpeedRecommendation",
    "calculate_write_speed",
    "detect_blank_media",
    "detect_drive_info",
    "format_speed_for_display",
    "get_media_capacity",
    "get_media_max_speed",
    "MEDIA_SPECS",
]
