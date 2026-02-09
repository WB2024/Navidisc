"""Burner module for Navidisc.

Provides disc burning abstraction and backend implementations.
"""

from navidisc.burner.adapter import (
    BurnerAdapter,
    DryRunBackend,
    GrowIsofsBackend,
    WodimBackend,
    detect_backend,
)
from navidisc.burner.drive import (
    DriveInfo,
    SpeedRecommendation,
    calculate_write_speed,
    detect_drive_info,
    format_speed_for_display,
    get_media_capacity,
    get_media_max_speed,
    MEDIA_SPECS,
)

__all__ = [
    "BurnerAdapter",
    "GrowIsofsBackend",
    "WodimBackend",
    "DryRunBackend",
    "detect_backend",
    "DriveInfo",
    "SpeedRecommendation",
    "calculate_write_speed",
    "detect_drive_info",
    "format_speed_for_display",
    "get_media_capacity",
    "get_media_max_speed",
    "MEDIA_SPECS",
]
