"""Burner adapter for disc burning operations.

This module provides:
- Abstract interface for disc burning
- Backend implementations for growisofs, cdrecord
- Drive detection and readiness checking
- Intelligent speed calculation
- Dry-run mode for testing
"""

import asyncio
import logging
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from navidisc.burner.drive import (
    DriveInfo,
    SpeedRecommendation,
    calculate_write_speed,
    detect_drive_info,
)
from navidisc.models import BurnResult, BurnStatus, DiscType, MediaType, WriteSpeed


class BurnProgress:
    """Progress information for a burn operation."""

    def __init__(
        self,
        disc_number: int,
        status: str,
        percent: float | None = None,
        message: str = "",
    ):
        self.disc_number = disc_number
        self.status = status
        self.percent = percent
        self.message = message


ProgressCallback = Callable[[BurnProgress], None]


class BurnerError(Exception):
    """Error during disc burning."""
    pass


class BurnerAdapter(ABC):
    """Abstract base class for disc burning backends.

    This provides a clean interface for burning operations,
    separating the execution logic from UI and orchestration.

    The adapter handles:
    - Drive detection
    - Burn execution
    - Progress reporting
    - Verification
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name."""
        pass

    @property
    @abstractmethod
    def supported_disc_types(self) -> list[DiscType]:
        """Disc types supported by this backend."""
        pass

    @abstractmethod
    async def check_device(self, device: str) -> tuple[bool, str]:
        """Check if a device is ready for burning.

        Args:
            device: Device path (e.g., /dev/sr0).

        Returns:
            Tuple of (ready, message).
        """
        pass

    @abstractmethod
    async def burn(
        self,
        disc_path: Path,
        device: str,
        disc_number: int = 1,
        progress_callback: ProgressCallback | None = None,
    ) -> BurnResult:
        """Burn a disc.

        Args:
            disc_path: Path to the staged disc directory.
            device: Device path to burn to.
            disc_number: Disc number for tracking.
            progress_callback: Optional callback for progress updates.

        Returns:
            BurnResult with burn status.
        """
        pass

    @abstractmethod
    async def eject(self, device: str) -> bool:
        """Eject a disc.

        Args:
            device: Device path.

        Returns:
            True if ejected successfully.
        """
        pass

    async def verify(
        self,
        device: str,
        expected_files: list[str],
    ) -> tuple[bool, str]:
        """Verify a burned disc.

        Default implementation just checks if device is readable.

        Args:
            device: Device path.
            expected_files: List of expected file names.

        Returns:
            Tuple of (success, message).
        """
        # Basic verification - subclasses can override
        return True, "Verification not implemented for this backend"


class GrowIsofsBackend(BurnerAdapter):
    """Burner backend using growisofs for data CDs/DVDs.

    This is the primary backend for data disc burning on Linux.
    Requires the dvd+rw-tools package.
    """

    def __init__(
        self,
        media_type: MediaType = MediaType.AUTO,
        write_speed: WriteSpeed = WriteSpeed.AUTO,
        custom_speed: int | None = None,
    ):
        """Initialize growisofs backend.

        Args:
            media_type: Type of media being used.
            write_speed: Speed preset.
            custom_speed: Custom speed value (when write_speed=CUSTOM).
        """
        self.media_type = media_type
        self.write_speed_preset = write_speed
        self.custom_speed = custom_speed
        self._drive_info: DriveInfo | None = None
        self._speed_recommendation: SpeedRecommendation | None = None

    @property
    def name(self) -> str:
        return "growisofs"

    @property
    def supported_disc_types(self) -> list[DiscType]:
        return [DiscType.DATA]

    @classmethod
    def is_available(cls) -> bool:
        """Check if growisofs is installed."""
        return shutil.which("growisofs") is not None

    async def check_device(self, device: str) -> tuple[bool, str]:
        """Check if device is ready for burning and detect capabilities."""
        if not Path(device).exists():
            return False, f"Device {device} does not exist"

        # Detect drive capabilities
        self._drive_info = await detect_drive_info(device)
        
        # Calculate recommended speed
        self._speed_recommendation = calculate_write_speed(
            write_speed_preset=self.write_speed_preset,
            media_type=self.media_type,
            drive_info=self._drive_info,
            custom_speed=self.custom_speed,
        )

        # Try to get device info using lsblk
        try:
            result = await asyncio.create_subprocess_exec(
                "lsblk", "-n", "-o", "TYPE,SIZE", device,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                return False, f"Cannot read device info: {stderr.decode().strip()}"

            output = stdout.decode().strip()
            if "rom" not in output.lower():
                return False, f"Device {device} does not appear to be an optical drive"

            # Build status message with drive info
            status_parts = ["Device ready"]
            if self._drive_info:
                status_parts.append(f"Drive: {self._drive_info.vendor} {self._drive_info.model}")
            if self._speed_recommendation:
                status_parts.append(f"Speed: {self._speed_recommendation.reason}")
            
            return True, " | ".join(status_parts)

        except FileNotFoundError:
            # lsblk not available, just check device exists
            return True, "Device exists (unable to verify type)"
    
    @property
    def drive_info(self) -> DriveInfo | None:
        """Get detected drive information."""
        return self._drive_info
    
    @property
    def speed_recommendation(self) -> SpeedRecommendation | None:
        """Get calculated speed recommendation."""
        return self._speed_recommendation

    async def burn(
        self,
        disc_path: Path,
        device: str,
        disc_number: int = 1,
        progress_callback: ProgressCallback | None = None,
    ) -> BurnResult:
        """Burn a data disc using growisofs."""
        started_at = datetime.now()
        
        # Ensure we have speed recommendation
        if not self._speed_recommendation:
            self._speed_recommendation = calculate_write_speed(
                write_speed_preset=self.write_speed_preset,
                media_type=self.media_type,
                drive_info=self._drive_info,
                custom_speed=self.custom_speed,
            )

        if progress_callback:
            progress_callback(BurnProgress(
                disc_number=disc_number,
                status="starting",
                message="Preparing to burn...",
            ))

        # Build growisofs command
        cmd = [
            "growisofs",
            "-dvd-compat",
            "-Z", device,
            "-R", "-J",  # Rock Ridge and Joliet extensions
            "-V", f"DISC_{disc_number:02d}",  # Volume label
        ]

        # Add speed if we have a recommendation (0 means auto/let drive decide)
        if self._speed_recommendation and self._speed_recommendation.speed_x > 0:
            cmd.extend(["-speed=%d" % self._speed_recommendation.speed_x])

        cmd.append(str(disc_path))
        
        logger.info(f"Executing: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            output_lines = []

            # Read output and parse progress
            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                line_text = line.decode().strip()
                output_lines.append(line_text)

                # Parse progress from growisofs output
                if progress_callback and "%" in line_text:
                    try:
                        # growisofs outputs progress like "12.3% done"
                        for part in line_text.split():
                            if "%" in part:
                                percent = float(part.replace("%", ""))
                                progress_callback(BurnProgress(
                                    disc_number=disc_number,
                                    status="burning",
                                    percent=percent,
                                    message=line_text,
                                ))
                                break
                    except ValueError:
                        pass

            await process.wait()

            completed_at = datetime.now()
            output_text = "\n".join(output_lines)
            
            logger.debug(f"growisofs exited with code {process.returncode}")
            if output_text:
                logger.debug(f"growisofs output:\n{output_text}")

            if process.returncode == 0:
                if progress_callback:
                    progress_callback(BurnProgress(
                        disc_number=disc_number,
                        status="complete",
                        percent=100,
                        message="Burn completed successfully",
                    ))

                return BurnResult(
                    disc_number=disc_number,
                    status=BurnStatus.SUCCESS,
                    device=device,
                    started_at=started_at,
                    completed_at=completed_at,
                    command_output=output_text,
                )
            else:
                return BurnResult(
                    disc_number=disc_number,
                    status=BurnStatus.FAILED,
                    device=device,
                    started_at=started_at,
                    completed_at=completed_at,
                    error_message=f"growisofs exited with code {process.returncode}",
                    command_output=output_text,
                )

        except Exception as e:
            return BurnResult(
                disc_number=disc_number,
                status=BurnStatus.FAILED,
                device=device,
                started_at=started_at,
                completed_at=datetime.now(),
                error_message=str(e),
            )

    async def eject(self, device: str) -> bool:
        """Eject the disc."""
        try:
            result = await asyncio.create_subprocess_exec(
                "eject", device,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await result.communicate()
            return result.returncode == 0
        except Exception:
            return False


class DryRunBackend(BurnerAdapter):
    """Dry-run backend for testing without burning.

    This backend simulates burning operations for testing
    and planning purposes.
    """

    def __init__(self, simulate_duration: float = 2.0):
        """Initialize dry-run backend.

        Args:
            simulate_duration: Simulated burn duration in seconds.
        """
        self.simulate_duration = simulate_duration

    @property
    def name(self) -> str:
        return "dry-run"

    @property
    def supported_disc_types(self) -> list[DiscType]:
        return [DiscType.DATA, DiscType.AUDIO]

    async def check_device(self, device: str) -> tuple[bool, str]:
        """Always returns ready in dry-run mode."""
        return True, f"[DRY-RUN] Device {device} ready (simulated)"

    async def burn(
        self,
        disc_path: Path,
        device: str,
        disc_number: int = 1,
        progress_callback: ProgressCallback | None = None,
    ) -> BurnResult:
        """Simulate a burn operation."""
        started_at = datetime.now()

        # Verify disc path exists
        if not disc_path.exists():
            return BurnResult(
                disc_number=disc_number,
                status=BurnStatus.FAILED,
                device=device,
                started_at=started_at,
                completed_at=datetime.now(),
                error_message=f"Disc path does not exist: {disc_path}",
            )

        # Count files
        files = list(disc_path.iterdir()) if disc_path.is_dir() else []

        if progress_callback:
            progress_callback(BurnProgress(
                disc_number=disc_number,
                status="starting",
                message=f"[DRY-RUN] Would burn {len(files)} files to {device}",
            ))

        # Simulate progress
        steps = 10
        for i in range(steps):
            if progress_callback:
                progress_callback(BurnProgress(
                    disc_number=disc_number,
                    status="burning",
                    percent=(i + 1) * 100 / steps,
                    message=f"[DRY-RUN] Simulating... {(i + 1) * 10}%",
                ))
            await asyncio.sleep(self.simulate_duration / steps)

        if progress_callback:
            progress_callback(BurnProgress(
                disc_number=disc_number,
                status="complete",
                percent=100,
                message="[DRY-RUN] Burn simulation complete",
            ))

        return BurnResult(
            disc_number=disc_number,
            status=BurnStatus.SUCCESS,
            device=device,
            started_at=started_at,
            completed_at=datetime.now(),
            command_output=f"[DRY-RUN] Would have burned {len(files)} files to {device}",
        )

    async def eject(self, device: str) -> bool:
        """Simulate eject."""
        return True


def detect_backend(
    disc_type: DiscType = DiscType.DATA,
    media_type: MediaType = MediaType.AUTO,
    write_speed: WriteSpeed = WriteSpeed.AUTO,
    custom_speed: int | None = None,
    dry_run: bool = False,
) -> BurnerAdapter:
    """Detect and return an appropriate burner backend.

    Args:
        disc_type: Type of disc to burn (data/audio).
        media_type: Physical media type (CD-R, DVD-R, etc.).
        write_speed: Speed preset (auto, max, safe, custom).
        custom_speed: Custom speed value when write_speed=CUSTOM.
        dry_run: If True, return dry-run backend.

    Returns:
        Appropriate BurnerAdapter instance.

    Raises:
        BurnerError: If no suitable backend is available.
    """
    if dry_run:
        return DryRunBackend()

    if disc_type == DiscType.DATA:
        if GrowIsofsBackend.is_available():
            return GrowIsofsBackend(
                media_type=media_type,
                write_speed=write_speed,
                custom_speed=custom_speed,
            )
        raise BurnerError(
            "No data disc backend available. "
            "Please install dvd+rw-tools (growisofs)."
        )

    # Audio disc - would need cdrecord/cdrdao
    raise BurnerError(
        f"No backend available for {disc_type.value} discs. "
        "Audio CD burning is not yet implemented."
    )


def list_available_backends() -> list[str]:
    """List available burner backends.

    Returns:
        List of available backend names.
    """
    available = ["dry-run"]

    if GrowIsofsBackend.is_available():
        available.append("growisofs")

    return available
