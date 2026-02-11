"""Drive detection and speed calculation for disc burning.

This module provides:
- Optical drive capability detection
- Media type detection from inserted disc
- Optimal write speed calculation
- Drive/media compatibility checking
"""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from navidisc.models import MediaType, WriteSpeed


# Media type specifications: (base_speed_kbps, max_multiplier, capacity_mb)
# Base speeds: CD=150KB/s, DVD=1350KB/s, BD=4500KB/s
MEDIA_SPECS: dict[MediaType, dict] = {
    # CD-R Standard (1x = 150 KB/s)
    MediaType.CD_R_1X: {"base": 150, "max_x": 1, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_2X: {"base": 150, "max_x": 2, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_4X: {"base": 150, "max_x": 4, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_8X: {"base": 150, "max_x": 8, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_12X: {"base": 150, "max_x": 12, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_16X: {"base": 150, "max_x": 16, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_20X: {"base": 150, "max_x": 20, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_24X: {"base": 150, "max_x": 24, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_32X: {"base": 150, "max_x": 32, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_40X: {"base": 150, "max_x": 40, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_48X: {"base": 150, "max_x": 48, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_R_52X: {"base": 150, "max_x": 52, "capacity_mb": 700, "family": "cd"},
    # CD-R Mini (8 cm)
    MediaType.CD_R_MINI_4X: {"base": 150, "max_x": 4, "capacity_mb": 185, "family": "cd"},
    MediaType.CD_R_MINI_8X: {"base": 150, "max_x": 8, "capacity_mb": 185, "family": "cd"},
    MediaType.CD_R_MINI_12X: {"base": 150, "max_x": 12, "capacity_mb": 185, "family": "cd"},
    MediaType.CD_R_MINI_16X: {"base": 150, "max_x": 16, "capacity_mb": 185, "family": "cd"},
    MediaType.CD_R_MINI_24X: {"base": 150, "max_x": 24, "capacity_mb": 185, "family": "cd"},
    # CD-RW Standard
    MediaType.CD_RW_1X: {"base": 150, "max_x": 1, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_RW_2X: {"base": 150, "max_x": 2, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_RW_4X: {"base": 150, "max_x": 4, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_RW_8X: {"base": 150, "max_x": 8, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_RW_10X: {"base": 150, "max_x": 10, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_RW_12X: {"base": 150, "max_x": 12, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_RW_16X: {"base": 150, "max_x": 16, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_RW_20X: {"base": 150, "max_x": 20, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_RW_24X: {"base": 150, "max_x": 24, "capacity_mb": 700, "family": "cd"},
    MediaType.CD_RW_32X: {"base": 150, "max_x": 32, "capacity_mb": 700, "family": "cd"},
    # CD-RW Mini (8 cm)
    MediaType.CD_RW_MINI_4X: {"base": 150, "max_x": 4, "capacity_mb": 185, "family": "cd"},
    MediaType.CD_RW_MINI_8X: {"base": 150, "max_x": 8, "capacity_mb": 185, "family": "cd"},
    MediaType.CD_RW_MINI_10X: {"base": 150, "max_x": 10, "capacity_mb": 185, "family": "cd"},
    # DVD-R (1x = 1350 KB/s)
    MediaType.DVD_R_1X: {"base": 1350, "max_x": 1, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_R_2X: {"base": 1350, "max_x": 2, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_R_4X: {"base": 1350, "max_x": 4, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_R_8X: {"base": 1350, "max_x": 8, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_R_16X: {"base": 1350, "max_x": 16, "capacity_mb": 4700, "family": "dvd"},
    # DVD+R
    MediaType.DVD_PLUS_R_2_4X: {"base": 1350, "max_x": 2, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_PLUS_R_4X: {"base": 1350, "max_x": 4, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_PLUS_R_8X: {"base": 1350, "max_x": 8, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_PLUS_R_16X: {"base": 1350, "max_x": 16, "capacity_mb": 4700, "family": "dvd"},
    # DVD-RW
    MediaType.DVD_RW_1X: {"base": 1350, "max_x": 1, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_RW_2X: {"base": 1350, "max_x": 2, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_RW_4X: {"base": 1350, "max_x": 4, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_RW_6X: {"base": 1350, "max_x": 6, "capacity_mb": 4700, "family": "dvd"},
    # DVD+RW
    MediaType.DVD_PLUS_RW_2_4X: {"base": 1350, "max_x": 2, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_PLUS_RW_4X: {"base": 1350, "max_x": 4, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_PLUS_RW_8X: {"base": 1350, "max_x": 8, "capacity_mb": 4700, "family": "dvd"},
    # DVD Dual Layer
    MediaType.DVD_R_DL_2X: {"base": 1350, "max_x": 2, "capacity_mb": 8500, "family": "dvd"},
    MediaType.DVD_R_DL_4X: {"base": 1350, "max_x": 4, "capacity_mb": 8500, "family": "dvd"},
    MediaType.DVD_R_DL_8X: {"base": 1350, "max_x": 8, "capacity_mb": 8500, "family": "dvd"},
    MediaType.DVD_PLUS_R_DL_2_4X: {"base": 1350, "max_x": 2, "capacity_mb": 8500, "family": "dvd"},
    MediaType.DVD_PLUS_R_DL_4X: {"base": 1350, "max_x": 4, "capacity_mb": 8500, "family": "dvd"},
    MediaType.DVD_PLUS_R_DL_8X: {"base": 1350, "max_x": 8, "capacity_mb": 8500, "family": "dvd"},
    # DVD-RAM
    MediaType.DVD_RAM_2X: {"base": 1350, "max_x": 2, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_RAM_3X: {"base": 1350, "max_x": 3, "capacity_mb": 4700, "family": "dvd"},
    MediaType.DVD_RAM_5X: {"base": 1350, "max_x": 5, "capacity_mb": 4700, "family": "dvd"},
    # DVD Mini (8 cm)
    MediaType.DVD_R_MINI_2X: {"base": 1350, "max_x": 2, "capacity_mb": 1400, "family": "dvd"},
    MediaType.DVD_R_MINI_4X: {"base": 1350, "max_x": 4, "capacity_mb": 1400, "family": "dvd"},
    MediaType.DVD_RW_MINI_2X: {"base": 1350, "max_x": 2, "capacity_mb": 1400, "family": "dvd"},
    # Blu-ray BD-R (1x = 4500 KB/s)
    MediaType.BD_R_1X: {"base": 4500, "max_x": 1, "capacity_mb": 25000, "family": "bd"},
    MediaType.BD_R_2X: {"base": 4500, "max_x": 2, "capacity_mb": 25000, "family": "bd"},
    MediaType.BD_R_4X: {"base": 4500, "max_x": 4, "capacity_mb": 25000, "family": "bd"},
    MediaType.BD_R_6X: {"base": 4500, "max_x": 6, "capacity_mb": 25000, "family": "bd"},
    MediaType.BD_R_8X: {"base": 4500, "max_x": 8, "capacity_mb": 25000, "family": "bd"},
    MediaType.BD_R_10X: {"base": 4500, "max_x": 10, "capacity_mb": 25000, "family": "bd"},
    MediaType.BD_R_12X: {"base": 4500, "max_x": 12, "capacity_mb": 25000, "family": "bd"},
    MediaType.BD_R_16X: {"base": 4500, "max_x": 16, "capacity_mb": 25000, "family": "bd"},
    # Blu-ray BD-RE (rewritable)
    MediaType.BD_RE_1X: {"base": 4500, "max_x": 1, "capacity_mb": 25000, "family": "bd"},
    MediaType.BD_RE_2X: {"base": 4500, "max_x": 2, "capacity_mb": 25000, "family": "bd"},
    # BDXL (high capacity)
    MediaType.BD_R_XL_4X: {"base": 4500, "max_x": 4, "capacity_mb": 100000, "family": "bd"},
    MediaType.BD_R_XL_6X: {"base": 4500, "max_x": 6, "capacity_mb": 100000, "family": "bd"},
    MediaType.BD_RE_XL_2X: {"base": 4500, "max_x": 2, "capacity_mb": 100000, "family": "bd"},
}

# Safe speed multipliers (more conservative for reliability)
SAFE_SPEED_RATIO = 0.5  # Use 50% of max speed for safe mode


@dataclass
class DriveInfo:
    """Information about an optical drive."""
    device: str
    vendor: str
    model: str
    can_write_cd: bool
    can_write_dvd: bool
    can_write_bd: bool
    max_cd_write_speed: int | None  # In x multiplier
    max_dvd_write_speed: int | None
    max_bd_write_speed: int | None
    current_media: str | None  # Type of inserted media
    media_writable: bool


@dataclass
class SpeedRecommendation:
    """Recommended write speed calculation result."""
    speed_x: int  # Speed multiplier (e.g., 16 for 16x)
    speed_kbps: int  # Actual speed in KB/s
    reason: str  # Explanation of how speed was determined
    media_type: MediaType | None
    is_estimated: bool  # True if we couldn't detect actual capabilities


def get_media_max_speed(media_type: MediaType) -> tuple[int, int]:
    """Get maximum speed for a media type.
    
    Returns:
        Tuple of (multiplier, speed_in_kbps)
    """
    if media_type == MediaType.AUTO or media_type not in MEDIA_SPECS:
        return (0, 0)
    
    spec = MEDIA_SPECS[media_type]
    speed_kbps = spec["base"] * spec["max_x"]
    return (spec["max_x"], speed_kbps)


def get_media_family(media_type: MediaType) -> str:
    """Get the media family (cd, dvd, bd) for a media type."""
    if media_type == MediaType.AUTO:
        return "unknown"
    spec = MEDIA_SPECS.get(media_type)
    return spec["family"] if spec else "unknown"


def get_media_capacity(media_type: MediaType) -> int:
    """Get capacity in MB for a media type."""
    if media_type == MediaType.AUTO:
        return 700  # Default to CD
    spec = MEDIA_SPECS.get(media_type)
    return spec["capacity_mb"] if spec else 700


async def detect_drive_info(device: str) -> DriveInfo | None:
    """Detect optical drive capabilities.
    
    Uses cdrecord/wodim -prcap or udevadm to get drive info.
    
    Args:
        device: Device path (e.g., /dev/sr0)
        
    Returns:
        DriveInfo or None if detection fails.
    """
    if not Path(device).exists():
        return None
    
    # Try wodim/cdrecord first for detailed capabilities
    drive_info = await _detect_with_wodim(device)
    if drive_info:
        return drive_info
    
    # Fall back to udevadm
    drive_info = await _detect_with_udevadm(device)
    if drive_info:
        return drive_info
    
    # Minimal fallback
    return DriveInfo(
        device=device,
        vendor="Unknown",
        model="Unknown",
        can_write_cd=True,  # Assume yes
        can_write_dvd=True,
        can_write_bd=False,
        max_cd_write_speed=None,
        max_dvd_write_speed=None,
        max_bd_write_speed=None,
        current_media=None,
        media_writable=False,
    )


async def _detect_with_wodim(device: str) -> DriveInfo | None:
    """Detect drive info using wodim/cdrecord."""
    # Try wodim first, then cdrecord
    for cmd in ["wodim", "cdrecord"]:
        try:
            process = await asyncio.create_subprocess_exec(
                cmd, f"dev={device}", "-prcap",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return _parse_prcap_output(device, stdout.decode())
        except FileNotFoundError:
            continue
    
    return None


def _parse_prcap_output(device: str, output: str) -> DriveInfo:
    """Parse wodim/cdrecord -prcap output."""
    lines = output.lower()
    
    # Extract vendor/model
    vendor = "Unknown"
    model = "Unknown"
    vendor_match = re.search(r"vendor_info\s*:\s*'([^']*)'", output, re.I)
    if vendor_match:
        vendor = vendor_match.group(1).strip()
    model_match = re.search(r"identification\s*:\s*'([^']*)'", output, re.I)
    if model_match:
        model = model_match.group(1).strip()
    
    # Check write capabilities
    can_write_cd = "does write cd-r" in lines or "cd-r write" in lines
    can_write_dvd = "does write dvd" in lines or "dvd-r write" in lines or "dvd+r write" in lines
    can_write_bd = "does write bd" in lines or "bd-r write" in lines
    
    # Extract max write speeds
    max_cd_speed = None
    max_dvd_speed = None
    max_bd_speed = None
    
    # Look for CD write speed
    cd_speed_match = re.search(r"max.*cd.*write\s+speed:\s*(\d+)", lines)
    if cd_speed_match:
        max_cd_speed = int(cd_speed_match.group(1))
    
    # Look for DVD write speed  
    dvd_speed_match = re.search(r"max.*dvd.*write\s+speed:\s*(\d+)", lines)
    if dvd_speed_match:
        max_dvd_speed = int(dvd_speed_match.group(1))
    
    # Check current media
    current_media = None
    media_writable = False
    if "current:" in lines:
        if "cd-r" in lines:
            current_media = "CD-R"
            media_writable = True
        elif "cd-rw" in lines:
            current_media = "CD-RW"
            media_writable = True
        elif "dvd-r" in lines or "dvd+r" in lines:
            current_media = "DVD-R"
            media_writable = True
        elif "dvd-rw" in lines or "dvd+rw" in lines:
            current_media = "DVD-RW"
            media_writable = True
        elif "bd-r" in lines:
            current_media = "BD-R"
            media_writable = True
    
    return DriveInfo(
        device=device,
        vendor=vendor,
        model=model,
        can_write_cd=can_write_cd,
        can_write_dvd=can_write_dvd,
        can_write_bd=can_write_bd,
        max_cd_write_speed=max_cd_speed,
        max_dvd_write_speed=max_dvd_speed,
        max_bd_write_speed=max_bd_speed,
        current_media=current_media,
        media_writable=media_writable,
    )


async def _detect_with_udevadm(device: str) -> DriveInfo | None:
    """Detect drive info using udevadm."""
    props = await _get_udevadm_properties(device)
    if not props:
        return None
    
    return DriveInfo(
        device=device,
        vendor=props.get("ID_VENDOR", "Unknown"),
        model=props.get("ID_MODEL", "Unknown"),
        can_write_cd=props.get("ID_CDROM_CD_R") == "1",
        can_write_dvd=props.get("ID_CDROM_DVD_R") == "1" or props.get("ID_CDROM_DVD_PLUS_R") == "1",
        can_write_bd=props.get("ID_CDROM_BD_R") == "1",
        max_cd_write_speed=None,
        max_dvd_write_speed=None,
        max_bd_write_speed=None,
        current_media=props.get("ID_CDROM_MEDIA"),
        media_writable=props.get("ID_CDROM_MEDIA_STATE") == "blank",
    )


async def _get_udevadm_properties(device: str) -> dict[str, str] | None:
    """Get udevadm properties for a device."""
    try:
        process = await asyncio.create_subprocess_exec(
            "udevadm", "info", "--query=property", f"--name={device}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        
        if process.returncode != 0:
            return None
        
        props = {}
        for line in stdout.decode().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                props[key] = value
        return props
    except FileNotFoundError:
        return None


async def detect_blank_media(device: str) -> tuple[bool, str | None, str]:
    """Detect if blank/writable media is inserted.
    
    Uses udevadm which reliably reports media state.
    
    Args:
        device: Device path (e.g., /dev/sr0).
        
    Returns:
        Tuple of (is_blank, media_type, status_message).
    """
    props = await _get_udevadm_properties(device)
    
    if not props:
        return False, None, "Unable to query device (udevadm not available)"
    
    media_type = props.get("ID_CDROM_MEDIA")
    media_state = props.get("ID_CDROM_MEDIA_STATE")
    
    if not media_type:
        return False, None, "No media inserted"
    
    if media_state == "blank":
        return True, media_type, f"Blank {media_type} detected"
    elif media_state == "complete":
        return False, media_type, f"Media '{media_type}' already burned (complete)"
    elif media_state == "appendable":
        return False, media_type, f"Media '{media_type}' is appendable but not blank"
    else:
        return False, media_type, f"Media '{media_type}' state: {media_state or 'unknown'}"


def calculate_write_speed(
    write_speed_preset: WriteSpeed,
    media_type: MediaType,
    drive_info: DriveInfo | None,
    custom_speed: int | None = None,
) -> SpeedRecommendation:
    """Calculate optimal write speed based on settings and capabilities.
    
    Args:
        write_speed_preset: The speed preset setting
        media_type: The media type being used
        drive_info: Detected drive capabilities (may be None)
        custom_speed: Custom speed value (when preset is CUSTOM)
        
    Returns:
        SpeedRecommendation with calculated speed and explanation.
    """
    # Handle custom speed
    if write_speed_preset == WriteSpeed.CUSTOM:
        if custom_speed is not None and custom_speed > 0:
            family = get_media_family(media_type)
            base_speed = {"cd": 150, "dvd": 1350, "bd": 4500}.get(family, 150)
            return SpeedRecommendation(
                speed_x=custom_speed,
                speed_kbps=custom_speed * base_speed,
                reason=f"Custom speed: {custom_speed}x",
                media_type=media_type,
                is_estimated=False,
            )
        # Fall back to auto if custom not set
        write_speed_preset = WriteSpeed.AUTO
    
    # Get media specs
    if media_type == MediaType.AUTO or media_type not in MEDIA_SPECS:
        # Auto-detect or unknown - use conservative defaults
        return SpeedRecommendation(
            speed_x=0,  # 0 means let the drive decide
            speed_kbps=0,
            reason="Auto-detect: letting drive determine optimal speed",
            media_type=media_type,
            is_estimated=True,
        )
    
    spec = MEDIA_SPECS[media_type]
    media_max_x = spec["max_x"]
    base_speed = spec["base"]
    family = spec["family"]
    
    # Get drive's max speed for this media family
    drive_max_x = None
    if drive_info:
        if family == "cd":
            drive_max_x = drive_info.max_cd_write_speed
        elif family == "dvd":
            drive_max_x = drive_info.max_dvd_write_speed
        elif family == "bd":
            drive_max_x = drive_info.max_bd_write_speed
    
    # Calculate actual max (minimum of media and drive)
    if drive_max_x:
        actual_max_x = min(media_max_x, drive_max_x)
        is_estimated = False
        drive_note = f" (drive max: {drive_max_x}x)"
    else:
        actual_max_x = media_max_x
        is_estimated = True
        drive_note = " (drive speed unknown)"
    
    # Apply preset
    if write_speed_preset == WriteSpeed.MAX:
        speed_x = actual_max_x
        reason = f"Maximum speed for {media_type.value}: {speed_x}x{drive_note}"
    elif write_speed_preset == WriteSpeed.SAFE:
        speed_x = max(1, int(actual_max_x * SAFE_SPEED_RATIO))
        reason = f"Safe speed (50% of max) for {media_type.value}: {speed_x}x"
    else:  # AUTO
        # Auto typically uses a moderate speed for reliability
        # Most drives perform well at 60-80% of max
        speed_x = max(1, int(actual_max_x * 0.7))
        reason = f"Auto speed (70% of max) for {media_type.value}: {speed_x}x{drive_note}"
    
    return SpeedRecommendation(
        speed_x=speed_x,
        speed_kbps=speed_x * base_speed,
        reason=reason,
        media_type=media_type,
        is_estimated=is_estimated,
    )


def format_speed_for_display(speed_x: int, media_type: MediaType) -> str:
    """Format speed for user display.
    
    Args:
        speed_x: Speed multiplier
        media_type: Media type for calculating KB/s
        
    Returns:
        Human-readable speed string like "16x (21.6 MB/s)"
    """
    if speed_x == 0:
        return "Auto (drive selects)"
    
    if media_type != MediaType.AUTO and media_type in MEDIA_SPECS:
        spec = MEDIA_SPECS[media_type]
        speed_kbps = speed_x * spec["base"]
        speed_mbs = speed_kbps / 1024
        return f"{speed_x}x ({speed_mbs:.1f} MB/s)"
    
    return f"{speed_x}x"
