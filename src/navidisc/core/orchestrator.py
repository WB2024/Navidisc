"""Orchestrator state machine for coordinating the burn workflow.

This module provides:
- Explicit state machine for the burn workflow
- Coordination between all modules
- Error handling and recovery
- Event emission for UI updates
"""

import logging
import shutil
import uuid
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from navidisc.api import SubsonicClient
from navidisc.burner import BurnerAdapter, detect_backend
from navidisc.config import NavidiscConfig
from navidisc.media import AudioConverter, Downloader, MediaResolver, ResolvedTrack
from navidisc.media.resolver import ResolveMethod
from navidisc.models import (
    BurnPlan,
    BurnStatus,
    ConversionQuality,
    NavidiscError,
    OrchestratorState,
    Playlist,
    SessionState,
)
from navidisc.planner import DiscPlanningEngine
from navidisc.staging import StagingManager


class OrchestratorEvent(StrEnum):
    """Events emitted by the orchestrator for UI updates."""
    STATE_CHANGED = "state_changed"
    PROGRESS = "progress"
    DISC_REQUIRED = "disc_required"
    BURN_STARTED = "burn_started"
    BURN_PROGRESS = "burn_progress"
    BURN_COMPLETED = "burn_completed"
    ERROR = "error"
    COMPLETE = "complete"


EventCallback = Callable[[OrchestratorEvent, dict[str, Any]], None]


class OrchestratorError(Exception):
    """Error in orchestrator operation."""
    pass


class Orchestrator:
    """State machine orchestrating the complete burn workflow.

    This is the central coordinator that:
    - Manages workflow state transitions
    - Coordinates all modules (API, planner, staging, burner)
    - Handles errors and retries
    - Emits events for UI updates

    The orchestrator is designed to be:
    - Explicit: clear state transitions
    - Debuggable: full state inspection
    - Resumable: state can be serialized
    - AI-friendly: deterministic behavior

    Example:
        orchestrator = Orchestrator(config)

        async with orchestrator:
            await orchestrator.run_playlist_burn(
                playlist_name="Road Trip",
                event_handler=handle_event
            )
    """

    def __init__(
        self,
        config: NavidiscConfig,
        dry_run: bool = False,
    ):
        """Initialize the orchestrator.

        Args:
            config: Navidisc configuration.
            dry_run: If True, don't actually burn discs.
        """
        self.config = config
        self.dry_run = dry_run

        # Initialize session
        self.session = SessionState(
            session_id=str(uuid.uuid4())[:8],
            state=OrchestratorState.INIT,
        )

        # Components (initialized lazily)
        self._api_client: SubsonicClient | None = None
        self._resolver: MediaResolver | None = None
        self._downloader: Downloader | None = None
        self._converter: AudioConverter | None = None
        self._planner: DiscPlanningEngine | None = None
        self._staging: StagingManager | None = None
        self._burner: BurnerAdapter | None = None

        # Workflow data
        self._playlist: Playlist | None = None
        self._resolved_tracks: list[ResolvedTrack] | None = None
        self._track_paths: dict[str, Path] = {}
        self._staged_discs: list = []

        # Event handling
        self._event_callback: EventCallback | None = None

    @property
    def state(self) -> OrchestratorState:
        """Current orchestrator state."""
        return self.session.state

    def _set_state(self, new_state: OrchestratorState) -> None:
        """Transition to a new state."""
        old_state = self.session.state
        self.session.state = new_state
        self.session.updated_at = datetime.now()
        
        logger.debug(f"State transition: {old_state.value} -> {new_state.value}")

        self._emit(OrchestratorEvent.STATE_CHANGED, {
            "old_state": old_state.value,
            "new_state": new_state.value,
        })

    def _emit(self, event: OrchestratorEvent, data: dict[str, Any]) -> None:
        """Emit an event to the callback."""
        if self._event_callback:
            self._event_callback(event, data)

    def _add_error(
        self,
        error_type: str,
        message: str,
        suggested_action: str | None = None,
        recoverable: bool = False,
        context: dict | None = None,
    ) -> NavidiscError:
        """Add an error to the session."""
        error = NavidiscError(
            stage=self.session.state,
            error_type=error_type,
            message=message,
            suggested_action=suggested_action,
            recoverable=recoverable,
            context=context or {},
        )
        self.session.errors.append(error)
        self._emit(OrchestratorEvent.ERROR, error.model_dump(mode='json'))
        return error

    # =========================================================================
    # Component initialization
    # =========================================================================

    def _get_api_client(self) -> SubsonicClient:
        """Get or create the API client."""
        if self._api_client is None:
            self._api_client = SubsonicClient(
                base_url=self.config.navidrome.url,
                username=self.config.navidrome.username,
                password=self.config.navidrome.password,
                api_version=self.config.navidrome.api_version,
            )
        return self._api_client

    def _get_resolver(self) -> MediaResolver:
        """Get or create the media resolver."""
        if self._resolver is None:
            self._resolver = MediaResolver(
                library_paths=[],  # Could add config for local library paths
                download_mode=self.config.media.download_mode,
            )
        return self._resolver

    def _get_downloader(self) -> Downloader:
        """Get or create the downloader."""
        if self._downloader is None:
            download_dir = self.config.media.staging_dir / "downloads"
            self._downloader = Downloader(download_dir=download_dir)
        return self._downloader

    def _get_converter(self) -> AudioConverter | None:
        """Get or create the audio converter, if conversion is enabled."""
        if self.config.media.conversion_quality == ConversionQuality.DISABLED:
            return None
        if self._converter is None:
            convert_dir = self.config.media.staging_dir / "converted"
            self._converter = AudioConverter(
                output_dir=convert_dir,
                quality=self.config.media.conversion_quality,
            )
        return self._converter

    def _get_planner(self) -> DiscPlanningEngine:
        """Get or create the disc planner."""
        if self._planner is None:
            self._planner = DiscPlanningEngine(
                disc_type=self.config.burning.disc_type,
                disc_capacity_bytes=self.config.burning.disc_size_bytes,
                disc_capacity_seconds=self.config.burning.audio_disc_seconds,
            )
        return self._planner

    def _get_staging(self) -> StagingManager:
        """Get or create the staging manager."""
        if self._staging is None:
            self._staging = StagingManager(
                staging_dir=self.config.media.staging_dir,
                use_hardlinks=self.config.media.use_hardlinks,
                normalize_filenames=self.config.media.normalize_filenames,
                include_track_numbers=self.config.media.include_track_numbers,
            )
        return self._staging

    def _get_burner(self) -> BurnerAdapter:
        """Get or create the burner adapter."""
        if self._burner is None:
            self._burner = detect_backend(
                disc_type=self.config.burning.disc_type,
                media_type=self.config.burning.media_type,
                write_speed=self.config.burning.write_speed,
                custom_speed=self.config.burning.custom_speed,
                dry_run=self.dry_run,
            )
        return self._burner

    # =========================================================================
    # Main workflow
    # =========================================================================

    async def run_playlist_burn(
        self,
        playlist_name: str | None = None,
        playlist_id: str | None = None,
        event_handler: EventCallback | None = None,
    ) -> SessionState:
        """Run the complete playlist burn workflow.

        Args:
            playlist_name: Name of playlist to burn (mutually exclusive with id).
            playlist_id: ID of playlist to burn (mutually exclusive with name).
            event_handler: Callback for workflow events.

        Returns:
            Final session state.
        """
        if not playlist_name and not playlist_id:
            raise ValueError("Must provide playlist_name or playlist_id")

        self._event_callback = event_handler

        try:
            # Step 1: Authenticate
            await self._step_authenticate()

            # Step 2: Resolve playlist
            await self._step_resolve_playlist(playlist_name, playlist_id)

            # Step 3: Plan discs
            await self._step_plan()

            # Step 4: Stage and burn each disc
            for disc_number in range(1, self.session.burn_plan.total_discs + 1):
                await self._step_stage_disc(disc_number)
                await self._step_burn_disc(disc_number)

            # Complete
            self._set_state(OrchestratorState.COMPLETE)
            self._emit(OrchestratorEvent.COMPLETE, {
                "session_id": self.session.session_id,
                "total_discs": self.session.burn_plan.total_discs,
                "results": [r.model_dump(mode='json') for r in self.session.burn_results],
            })

        except Exception as e:
            self._set_state(OrchestratorState.ERROR)
            self._add_error(
                error_type=type(e).__name__,
                message=str(e),
                suggested_action="Check logs for details",
            )
            raise

        finally:
            # Clean up downloaded/converted files if auto-cleanup is enabled
            if self.config.media.auto_cleanup:
                self._cleanup_local_files()

        return self.session

    async def _step_authenticate(self) -> None:
        """Authenticate with Navidrome."""
        client = self._get_api_client()
        
        logger.info(f"Authenticating with {self.config.navidrome.url}")

        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "authenticate",
            "message": f"Connecting to {self.config.navidrome.url}...",
        })

        await client.authenticate()
        self._set_state(OrchestratorState.AUTHENTICATED)
        logger.debug("Authentication successful")

    async def _step_resolve_playlist(
        self,
        name: str | None,
        playlist_id: str | None,
    ) -> None:
        """Resolve playlist and track files."""
        client = self._get_api_client()
        resolver = self._get_resolver()
        downloader = self._get_downloader()

        # Fetch playlist
        logger.debug(f"Fetching playlist: name={name}, id={playlist_id}")
        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "fetch_playlist",
            "message": "Fetching playlist...",
        })

        if playlist_id:
            self._playlist = await client.get_playlist(playlist_id)
        else:
            self._playlist = await client.get_playlist_by_name(name)

        self.session.playlist_id = self._playlist.id
        logger.info(f"Playlist loaded: '{self._playlist.name}' ({len(self._playlist.tracks)} tracks)")

        # Resolve tracks
        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "resolve_tracks",
            "message": f"Resolving {len(self._playlist.tracks)} tracks...",
        })

        self._resolved_tracks = resolver.resolve_many(
            self._playlist.tracks,
            lambda track_id: client.get_download_url(track_id),
        )
        logger.debug(f"Track resolution complete: {len(self._resolved_tracks)} tracks")

        # Download any tracks that need downloading
        download_count = sum(
            1 for rt in self._resolved_tracks
            if rt.method == ResolveMethod.DOWNLOAD
        )

        if download_count > 0:
            logger.info(f"Starting download of {download_count} tracks")
            self._emit(OrchestratorEvent.PROGRESS, {
                "step": "download_tracks",
                "message": f"Downloading {download_count} tracks...",
            })

            downloaded = await downloader.download_many(
                self._resolved_tracks,
                progress_callback=lambda p: self._emit(
                    OrchestratorEvent.PROGRESS,
                    {"step": "download", "track": p.filename, "percent": p.percent}
                ),
            )
            self._track_paths.update(downloaded)
            logger.debug(f"Downloaded {len(downloaded)} tracks")

        # Add local tracks to paths
        for rt in self._resolved_tracks:
            if rt.method == ResolveMethod.LOCAL and rt.local_path:
                self._track_paths[rt.track.id] = rt.local_path
        
        logger.debug(f"Total tracks prepared: {len(self._track_paths)}")

        # Convert tracks to MP3 if conversion is enabled
        converter = self._get_converter()
        if converter is not None:
            # Count files that need conversion
            needs_convert = {
                tid: path for tid, path in self._track_paths.items()
                if converter.needs_conversion(path)
            }
            
            if needs_convert:
                logger.info(f"Converting {len(needs_convert)} tracks to MP3 (quality: {self.config.media.conversion_quality})")
                self._emit(OrchestratorEvent.PROGRESS, {
                    "step": "converting",
                    "message": f"Converting {len(needs_convert)} tracks to MP3...",
                })

                converted = await converter.convert_many(
                    needs_convert,
                    progress_callback=lambda p: self._emit(
                        OrchestratorEvent.PROGRESS,
                        {
                            "step": "convert",
                            "track": p.filename,
                            "percent": p.percent,
                            "message": f"Converting: {p.filename}",
                        }
                    ),
                )
                self._track_paths.update(converted)
                logger.debug(f"Converted {len(converted)} tracks")

        self._set_state(OrchestratorState.PLAYLIST_RESOLVED)

    async def _step_plan(self) -> None:
        """Create the disc burn plan."""
        planner = self._get_planner()
        logger.info("Creating burn plan...")

        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "planning",
            "message": "Creating disc plan...",
        })

        # Build size lookup from actual files on disk (which may have been
        # converted to MP3), falling back to the API-reported size only when
        # no local file is available yet.
        size_lookup = {}
        for rt in self._resolved_tracks:
            if rt.track.id in self._track_paths:
                # Prefer actual file size – this reflects post-conversion size
                size_lookup[rt.track.id] = self._track_paths[rt.track.id].stat().st_size
            elif rt.size_bytes:
                size_lookup[rt.track.id] = rt.size_bytes

        plan = planner.plan(self._playlist, size_lookup)
        self.session.burn_plan = plan
        logger.info(f"Burn plan created: {plan.total_discs} disc(s) required")
        logger.debug(f"Plan details: disc_type={plan.disc_type}, capacity={plan.disc_capacity_bytes or plan.disc_capacity_seconds}")

        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "planned",
            "message": f"Plan created: {plan.total_discs} disc(s)",
            "plan": planner.get_plan_summary(plan),
        })

        self._set_state(OrchestratorState.PLANNED)

    async def _step_stage_disc(self, disc_number: int) -> None:
        """Stage files for a disc."""
        staging = self._get_staging()
        plan = self.session.burn_plan
        disc_plan = plan.discs[disc_number - 1]
        
        logger.info(f"Staging disc {disc_number}/{plan.total_discs} ({len(disc_plan.tracks)} tracks)")

        self._set_state(OrchestratorState.STAGING_DISC)
        self.session.current_disc = disc_number

        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "staging",
            "disc_number": disc_number,
            "message": f"Staging disc {disc_number}/{plan.total_discs}...",
        })

        # Build track lookup
        track_lookup = {t.id: t for t in self._playlist.tracks}

        staged = staging.stage_disc(disc_plan, self._track_paths, track_lookup)
        self._staged_discs.append(staged)
        logger.debug(f"Staged {len(staged.files)} files to {staged.directory}")

        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "staged",
            "disc_number": disc_number,
            "message": f"Staged {len(staged.files)} files",
        })

    async def _step_burn_disc(self, disc_number: int) -> None:
        """Burn a disc."""
        burner = self._get_burner()
        staged = self._staged_discs[disc_number - 1]
        plan = self.session.burn_plan

        # Wait for disc insertion
        self._set_state(OrchestratorState.WAIT_FOR_DISC)
        logger.info(f"Waiting for disc {disc_number} to be inserted into {self.config.burning.device}")

        self._emit(OrchestratorEvent.DISC_REQUIRED, {
            "disc_number": disc_number,
            "total_discs": plan.total_discs,
            "device": self.config.burning.device,
        })

        # Check device readiness
        ready, message = await burner.check_device(self.config.burning.device)
        logger.debug(f"Device ready check: ready={ready}, message={message}")
        if not ready and not self.dry_run:
            self._add_error(
                error_type="DeviceNotReady",
                message=message,
                suggested_action=f"Insert a blank disc into {self.config.burning.device}",
                recoverable=True,
            )
            # Cannot proceed with burn if device isn't ready
            self._set_state(OrchestratorState.ERROR)
            return

        # Burn the disc
        self._set_state(OrchestratorState.BURNING_DISC)
        logger.info(f"Starting burn of disc {disc_number}/{plan.total_discs} (dry_run={self.dry_run})")

        self._emit(OrchestratorEvent.BURN_STARTED, {
            "disc_number": disc_number,
            "total_discs": plan.total_discs,
        })

        result = await burner.burn(
            disc_path=staged.directory,
            device=self.config.burning.device,
            disc_number=disc_number,
            progress_callback=lambda p: self._emit(
                OrchestratorEvent.BURN_PROGRESS,
                {
                    "disc_number": p.disc_number,
                    "status": p.status,
                    "percent": p.percent,
                    "message": p.message,
                }
            ),
        )

        self.session.burn_results.append(result)
        logger.info(f"Burn completed: disc {disc_number}, status={result.status}")
        if result.error_message:
            logger.error(f"Burn error: {result.error_message}")

        # Verify if enabled
        if self.config.burning.verify_after_burn and result.status == BurnStatus.SUCCESS:
            self._set_state(OrchestratorState.VERIFYING)
            # Basic verification would go here

        # Eject if enabled
        if self.config.burning.eject_after_burn:
            logger.debug(f"Ejecting disc from {self.config.burning.device}")
            await burner.eject(self.config.burning.device)

        self._emit(OrchestratorEvent.BURN_COMPLETED, {
            "disc_number": disc_number,
            "result": result.model_dump(mode='json'),
        })

    # =========================================================================
    # Plan-only workflow
    # =========================================================================

    async def plan_only(
        self,
        playlist_name: str | None = None,
        playlist_id: str | None = None,
        event_handler: EventCallback | None = None,
    ) -> BurnPlan:
        """Create a burn plan without actually burning.

        Useful for dry-run planning and previewing disc splits.

        Args:
            playlist_name: Name of playlist.
            playlist_id: ID of playlist.
            event_handler: Optional event callback.

        Returns:
            The burn plan.
        """
        if not playlist_name and not playlist_id:
            raise ValueError("Must provide playlist_name or playlist_id")

        self._event_callback = event_handler

        await self._step_authenticate()
        await self._step_resolve_playlist(playlist_name, playlist_id)
        await self._step_plan()

        return self.session.burn_plan

    # =========================================================================
    # Cleanup
    # =========================================================================

    def _cleanup_local_files(self) -> None:
        """Delete locally downloaded and converted files.

        Only removes files managed by Navidisc inside the staging directory
        (downloads/ and converted/ sub-folders).  Never touches files on
        the Navidrome server or any other remote location.
        """
        staging_dir = self.config.media.staging_dir
        removed = 0

        for subdir_name in ("downloads", "converted"):
            subdir = staging_dir / subdir_name
            if subdir.exists() and subdir.is_dir():
                try:
                    shutil.rmtree(subdir)
                    removed += 1
                    logger.info("Auto-cleanup: removed %s", subdir)
                except OSError as exc:
                    logger.warning("Auto-cleanup: failed to remove %s: %s", subdir, exc)

        # Also remove disc staging directories (disc_01, disc_02 …)
        if staging_dir.exists():
            for entry in staging_dir.iterdir():
                if entry.is_dir() and entry.name.startswith("disc_"):
                    try:
                        shutil.rmtree(entry)
                        removed += 1
                        logger.info("Auto-cleanup: removed %s", entry)
                    except OSError as exc:
                        logger.warning("Auto-cleanup: failed to remove %s: %s", entry, exc)

        if removed:
            self._emit(OrchestratorEvent.PROGRESS, {
                "step": "cleanup",
                "message": f"Auto-cleanup: removed {removed} temporary director{'y' if removed == 1 else 'ies'}",
            })

    # =========================================================================
    # Context manager support
    # =========================================================================

    async def __aenter__(self) -> "Orchestrator":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - cleanup resources."""
        if self._api_client:
            await self._api_client.close()
        if self._downloader:
            await self._downloader.close()

    # =========================================================================
    # State inspection
    # =========================================================================

    def get_session_state(self) -> SessionState:
        """Get the current session state."""
        return self.session

    def get_state_summary(self) -> dict[str, Any]:
        """Get a summary of the current state for debugging."""
        return {
            "session_id": self.session.session_id,
            "state": self.session.state.value,
            "playlist_id": self.session.playlist_id,
            "current_disc": self.session.current_disc,
            "total_discs": self.session.burn_plan.total_discs if self.session.burn_plan else 0,
            "completed_burns": len(self.session.burn_results),
            "errors": len(self.session.errors),
            "started_at": self.session.started_at.isoformat(),
            "updated_at": self.session.updated_at.isoformat(),
        }
