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
from navidisc.burner import BurnerAdapter, detect_backend, AudioTrack, write_toc_file
from navidisc.config import NavidiscConfig
from navidisc.media import AudioConverter, Downloader, MediaResolver, ResolvedTrack, WavConverter
from navidisc.media.converter import estimate_mp3_size, estimate_mp3_size_from_file, ffprobe_duration
from navidisc.media.resolver import ResolveMethod
from navidisc.models import (
    Album,
    BurnPlan,
    BurnStatus,
    ConversionQuality,
    DiscType,
    NavidiscError,
    OrchestratorState,
    Playlist,
    SessionState,
    StagedDisc,
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
        
        # Log key config values for debugging
        logger.info(f"Orchestrator initialized with config:")
        logger.info(f"  - local_library_path: {config.media.local_library_path}")
        logger.info(f"  - download_mode: {config.media.download_mode.value}")
        logger.info(f"  - conversion_quality: {config.media.conversion_quality.value}")
        logger.info(f"  - staging_dir: {config.media.staging_dir}")

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
        self._wav_converter: WavConverter | None = None
        self._planner: DiscPlanningEngine | None = None
        self._staging: StagingManager | None = None
        self._burner: BurnerAdapter | None = None

        # Workflow data
        self._source: Playlist | Album | None = None  # Can be playlist or album
        self._is_album: bool = False  # Whether burning an album
        self._resolved_tracks: list[ResolvedTrack] | None = None
        self._track_paths: dict[str, Path] = {}
        self._staged_discs: dict[int, Any] = {}  # keyed by disc number

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
            # Use local library path if configured
            library_paths = []
            if self.config.media.local_library_path:
                library_paths.append(self.config.media.local_library_path)
            
            logger.info(f"Creating resolver: library_paths={library_paths}, download_mode={self.config.media.download_mode}")
            
            self._resolver = MediaResolver(
                library_paths=library_paths,
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

    def _get_wav_converter(self) -> WavConverter:
        """Get or create the WAV converter for audio CDs."""
        if self._wav_converter is None:
            wav_dir = self.config.media.staging_dir / "wav"
            self._wav_converter = WavConverter(output_dir=wav_dir)
        return self._wav_converter

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
                # Audio CD settings
                audio_burn_mode=self.config.burning.audio_burn_mode.value,
                audio_gap_seconds=self.config.burning.track_gap_seconds,
                audio_cd_text=self.config.burning.cd_text,
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
        selected_discs: list[int] | None = None,
    ) -> SessionState:
        """Run the complete playlist burn workflow.

        Args:
            playlist_name: Name of playlist to burn (mutually exclusive with id).
            playlist_id: ID of playlist to burn (mutually exclusive with name).
            event_handler: Callback for workflow events.
            selected_discs: List of disc numbers to burn (1-indexed). If None, burn all.

        Returns:
            Final session state.
        """
        if not playlist_name and not playlist_id:
            raise ValueError("Must provide playlist_name or playlist_id")

        self._event_callback = event_handler
        self._is_album = False

        try:
            # Step 1: Authenticate
            await self._step_authenticate()

            # Step 2: Fetch playlist metadata
            await self._step_fetch_source(playlist_name=playlist_name, playlist_id=playlist_id)

            # Step 3-8: Common burn workflow
            await self._run_common_burn_workflow(selected_discs)

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

    async def run_album_burn(
        self,
        album_id: str,
        event_handler: EventCallback | None = None,
        selected_discs: list[int] | None = None,
    ) -> SessionState:
        """Run the complete album burn workflow.

        Args:
            album_id: ID of album to burn.
            event_handler: Callback for workflow events.
            selected_discs: List of disc numbers to burn (1-indexed). If None, burn all.

        Returns:
            Final session state.
        """
        self._event_callback = event_handler
        self._is_album = True

        try:
            # Step 1: Authenticate
            await self._step_authenticate()

            # Step 2: Fetch album metadata
            await self._step_fetch_source(album_id=album_id)

            # Step 3-8: Common burn workflow
            await self._run_common_burn_workflow(selected_discs)

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

    async def _run_common_burn_workflow(self, selected_discs: list[int] | None = None) -> None:
        """Run the common burn workflow steps (resolve, plan, download, burn).
        
        Args:
            selected_discs: List of disc numbers to burn (1-indexed). If None, burn all.
        """
        # Step 3: Resolve ALL tracks (determine local vs download, no actual downloading)
        await self._step_resolve_all_tracks()

        # Step 4: Plan discs (using actual/estimated sizes accounting for conversion)
        await self._step_plan()

        # Step 5: Determine which discs to burn
        total_discs = self.session.burn_plan.total_discs
        if selected_discs:
            # Filter to only selected discs (validate they exist in plan)
            discs_to_burn = [d for d in selected_discs if 1 <= d <= total_discs]
            discs_to_burn.sort()  # Burn in order
            logger.info(f"Burning selected discs: {discs_to_burn} of {total_discs} total")
        else:
            # Burn all discs
            discs_to_burn = list(range(1, total_discs + 1))
            logger.info(f"Burning all {total_discs} disc(s)")

        # Step 6: Get track IDs from selected discs only
        selected_track_ids = set()
        for disc_num in discs_to_burn:
            disc_plan = self.session.burn_plan.discs[disc_num - 1]
            selected_track_ids.update(disc_plan.track_ids)
        
        logger.info(f"Selected discs contain {len(selected_track_ids)} tracks to prepare")

        # Step 7: Download and convert only selected tracks
        await self._step_prepare_selected_tracks(selected_track_ids)

        # Step 8: Stage and burn each selected disc
        for disc_number in discs_to_burn:
            await self._step_stage_disc(disc_number)
            await self._step_burn_disc(disc_number)

        # Complete
        self._set_state(OrchestratorState.COMPLETE)
        self._emit(OrchestratorEvent.COMPLETE, {
            "session_id": self.session.session_id,
            "total_discs": len(discs_to_burn),
            "selected_discs": discs_to_burn,
            "results": [r.model_dump(mode='json') for r in self.session.burn_results],
        })

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

    async def _step_fetch_source(
        self,
        playlist_name: str | None = None,
        playlist_id: str | None = None,
        album_id: str | None = None,
    ) -> None:
        """Fetch playlist or album metadata (no downloading yet)."""
        client = self._get_api_client()

        if album_id:
            # Fetch album
            logger.debug(f"Fetching album: id={album_id}")
            self._emit(OrchestratorEvent.PROGRESS, {
                "step": "fetch_album",
                "message": "Fetching album...",
            })

            self._source = await client.get_album(album_id)
            self.session.album_id = self._source.id
            logger.info(f"Album loaded: '{self._source.name}' ({len(self._source.tracks)} tracks)")
        else:
            # Fetch playlist
            logger.debug(f"Fetching playlist: name={playlist_name}, id={playlist_id}")
            self._emit(OrchestratorEvent.PROGRESS, {
                "step": "fetch_playlist",
                "message": "Fetching playlist...",
            })

            if playlist_id:
                self._source = await client.get_playlist(playlist_id)
            else:
                self._source = await client.get_playlist_by_name(playlist_name)

            self.session.playlist_id = self._source.id
            logger.info(f"Playlist loaded: '{self._source.name}' ({len(self._source.tracks)} tracks)")
        
        # Log first track's path for debugging
        if self._source.tracks:
            first_track = self._source.tracks[0]
            logger.debug(f"Example track path from Navidrome: {first_track.path}")

    async def _step_resolve_all_tracks(self) -> None:
        """Resolve ALL tracks to determine local vs download status.
        
        This does NOT download anything - it just determines how each track
        will be obtained and gets actual sizes for local files.
        """
        client = self._get_api_client()
        resolver = self._get_resolver()

        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "resolve_tracks",
            "message": f"Resolving {len(self._source.tracks)} tracks...",
        })

        self._resolved_tracks = resolver.resolve_many(
            self._source.tracks,
            lambda track_id: client.get_download_url(track_id),
        )
        
        # Log resolution summary
        resolution_summary = resolver.get_resolution_summary(self._resolved_tracks)
        logger.info(f"Track resolution complete: {resolution_summary['local']} local, {resolution_summary['download']} download, {resolution_summary['not_found']} not found")
        
        # Log first track's path for debugging
        if self._resolved_tracks:
            first_rt = self._resolved_tracks[0]
            logger.debug(f"Example resolved track: {first_rt.track.title} -> {first_rt.method.value}")

    async def _step_prepare_selected_tracks(self, selected_track_ids: set[str]) -> None:
        """Download and convert only the tracks that will be burned.
        
        Uses already-resolved track info from _step_resolve_all_tracks.
        
        Args:
            selected_track_ids: Set of track IDs to prepare (from selected discs).
        """
        downloader = self._get_downloader()

        # Filter resolved tracks to only selected ones
        selected_resolved = [rt for rt in self._resolved_tracks if rt.track.id in selected_track_ids]
        logger.info(f"Preparing {len(selected_resolved)} tracks for selected discs")

        # Check for NOT_FOUND tracks and fail early with helpful message
        not_found_tracks = [rt for rt in selected_resolved if rt.method == ResolveMethod.NOT_FOUND]
        if not_found_tracks:
            for rt in not_found_tracks[:5]:
                logger.error(f"Track not found: '{rt.track.title}' by {rt.track.artist} (path: {rt.track.path})")
            if len(not_found_tracks) > 5:
                logger.error(f"... and {len(not_found_tracks) - 5} more tracks not found")
            
            library_paths_str = ', '.join(str(p) for p in (self.config.media.local_library_path,)) if self.config.media.local_library_path else 'None'
            error_msg = (
                f"{len(not_found_tracks)} track(s) could not be found locally. "
                f"Local library path: {library_paths_str}. "
                f"Download mode: {self.config.media.download_mode.value}. "
                f"Check that the path matches your Navidrome music folder."
            )
            raise OrchestratorError(error_msg)

        # Download any tracks that need downloading
        download_tracks = [rt for rt in selected_resolved if rt.method == ResolveMethod.DOWNLOAD]

        if download_tracks:
            logger.info(f"Starting download of {len(download_tracks)} tracks")
            self._emit(OrchestratorEvent.PROGRESS, {
                "step": "download_tracks",
                "message": f"Downloading {len(download_tracks)} tracks...",
            })

            downloaded = await downloader.download_many(
                download_tracks,
                progress_callback=lambda p: self._emit(
                    OrchestratorEvent.PROGRESS,
                    {"step": "download", "track": p.filename, "percent": p.percent}
                ),
            )
            self._track_paths.update(downloaded)
            logger.debug(f"Downloaded {len(downloaded)} tracks")

        # Add local tracks to paths
        for rt in selected_resolved:
            if rt.method == ResolveMethod.LOCAL and rt.local_path:
                self._track_paths[rt.track.id] = rt.local_path
        
        logger.debug(f"Total tracks prepared: {len(self._track_paths)}")

        # Convert tracks to MP3 if conversion is enabled
        converter = self._get_converter()
        if converter is not None:
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
        """Create the disc burn plan using accurate sizes.
        
        For local files that need conversion, uses ffprobe to get the actual
        audio duration for accurate size estimation. This avoids relying on
        potentially inaccurate API metadata.
        """
        planner = self._get_planner()
        converter = self._get_converter()
        conversion_quality = self.config.media.conversion_quality
        
        logger.info("Creating burn plan...")
        logger.info(f"Conversion quality: {conversion_quality.value}")

        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "planning",
            "message": "Calculating accurate file sizes...",
        })

        # Build size lookup with accurate sizes using ffprobe when possible
        size_lookup = {}
        total_tracks = len(self._resolved_tracks)
        
        for idx, rt in enumerate(self._resolved_tracks, 1):
            track = rt.track
            
            if rt.method == ResolveMethod.LOCAL and rt.local_path:
                # Local file - use ffprobe for accurate sizing
                if converter and converter.needs_conversion(rt.local_path):
                    # File will be converted - get accurate size using ffprobe
                    logger.debug(f"[{idx}/{total_tracks}] Probing '{track.title}' for accurate duration...")
                    estimated_size = await estimate_mp3_size_from_file(
                        rt.local_path,
                        conversion_quality,
                        fallback_duration_seconds=track.duration_seconds,
                    )
                    size_lookup[track.id] = estimated_size
                    logger.info(
                        f"Track '{track.title}': {rt.size_bytes or 0} bytes source -> "
                        f"~{estimated_size} bytes after conversion ({estimated_size / 1024 / 1024:.2f} MB)"
                    )
                else:
                    # No conversion needed - use actual file size
                    actual_size = rt.size_bytes or track.size_bytes or 0
                    size_lookup[track.id] = actual_size
                    logger.debug(f"Track '{track.title}': {actual_size} bytes (no conversion)")
            else:
                # Download track - must use API duration estimate (no local file yet)
                if converter and conversion_quality != ConversionQuality.DISABLED and track.duration_seconds:
                    estimated_size = estimate_mp3_size(track.duration_seconds, conversion_quality)
                    size_lookup[track.id] = estimated_size
                    logger.debug(
                        f"Track '{track.title}': ~{estimated_size} bytes (estimated from API duration {track.duration_seconds}s)"
                    )
                else:
                    # Use API-reported size
                    size_lookup[track.id] = track.size_bytes or 0
                    logger.debug(f"Track '{track.title}': {track.size_bytes or 0} bytes (from API)")

        # Log total sizes for debugging
        total_size = sum(size_lookup.values())
        logger.info(f"Total planned size: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)")

        plan = planner.plan(self._source, size_lookup)
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
        plan = self.session.burn_plan
        disc_plan = plan.discs[disc_number - 1]
        
        logger.info(f"Staging disc {disc_number}/{plan.total_discs} ({disc_plan.track_count} tracks)")

        self._set_state(OrchestratorState.STAGING_DISC)
        self.session.current_disc = disc_number

        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "staging",
            "disc_number": disc_number,
            "message": f"Staging disc {disc_number}/{plan.total_discs}...",
        })

        # Build track lookup
        track_lookup = {t.id: t for t in self._source.tracks}

        # Different staging for audio CDs vs data discs
        if self.config.burning.disc_type == DiscType.AUDIO:
            staged = await self._stage_audio_cd(disc_number, disc_plan, track_lookup)
        else:
            staging = self._get_staging()
            staged = staging.stage_disc(disc_plan, self._track_paths, track_lookup)
        
        self._staged_discs[disc_number] = staged  # key by disc number, not append
        logger.debug(f"Staged {len(staged.files)} files to {staged.directory}")

        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "staged",
            "disc_number": disc_number,
            "message": f"Staged {len(staged.files)} files",
        })

    async def _step_burn_disc(self, disc_number: int) -> None:
        """Burn a disc."""
        burner = self._get_burner()
        staged = self._staged_discs[disc_number]  # use disc number directly as key
        plan = self.session.burn_plan

        # === DETAILED DEBUG INFO ABOUT THE BURN ===
        logger.debug("=" * 60)
        logger.debug("ORCHESTRATOR: BURN DISC DEBUG INFO")
        logger.debug("=" * 60)
        logger.debug(f"Session ID: {self.session.session_id}")
        logger.debug(f"Disc number: {disc_number} of {plan.total_discs}")
        logger.debug(f"Device: {self.config.burning.device}")
        logger.debug(f"Disc type: {self.config.burning.disc_type}")
        logger.debug(f"Media type: {self.config.burning.media_type}")
        logger.debug(f"Write speed: {self.config.burning.write_speed}")
        logger.debug(f"Dry run: {self.dry_run}")
        logger.debug(f"Burner backend: {burner.name}")
        logger.debug(f"Staged directory: {staged.directory}")
        logger.debug(f"Staged files count: {len(staged.files)}")
        if staged.files:
            logger.debug(f"Staged files (first 10):")
            for f in staged.files[:10]:
                logger.debug(f"  - {f}")
            if len(staged.files) > 10:
                logger.debug(f"  ... and {len(staged.files) - 10} more files")
        logger.debug(f"Verify after burn: {self.config.burning.verify_after_burn}")
        logger.debug(f"Eject after burn: {self.config.burning.eject_after_burn}")
        logger.debug("=" * 60)

        # Wait for disc insertion
        self._set_state(OrchestratorState.WAIT_FOR_DISC)
        logger.info(f"Waiting for disc {disc_number} to be inserted into {self.config.burning.device}")

        self._emit(OrchestratorEvent.DISC_REQUIRED, {
            "disc_number": disc_number,
            "total_discs": plan.total_discs,
            "device": self.config.burning.device,
        })

        # First check device exists
        ready, message = await burner.check_device(self.config.burning.device)
        logger.debug(f"Device check: ready={ready}, message={message}")
        if not ready and not self.dry_run:
            self._add_error(
                error_type="DeviceNotReady",
                message=message,
                suggested_action=f"Ensure {self.config.burning.device} is connected",
                recoverable=True,
            )
            self._set_state(OrchestratorState.ERROR)
            return

        # Wait for blank media to be inserted (poll indefinitely)
        if not self.dry_run:
            logger.info(f"Polling for blank media in {self.config.burning.device}...")
            
            def wait_progress(p):
                self._emit(OrchestratorEvent.PROGRESS, {
                    "step": "waiting_for_disc",
                    "disc_number": disc_number,
                    "message": p.message,
                })
            
            has_blank, blank_status = await burner.wait_for_blank_media(
                device=self.config.burning.device,
                poll_interval=3.0,  # Check every 3 seconds
                timeout=None,  # Wait indefinitely
                progress_callback=wait_progress,
            )
            
            logger.debug(f"Blank media check: has_blank={has_blank}, status={blank_status}")
            
            if not has_blank:
                self._add_error(
                    error_type="NoBlankMedia",
                    message=blank_status,
                    suggested_action=f"Insert a blank disc into {self.config.burning.device}",
                    recoverable=True,
                )
                self._set_state(OrchestratorState.ERROR)
                return
            
            logger.info(f"Blank media ready: {blank_status}")

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
        
        # === DETAILED POST-BURN DEBUG LOGGING ===
        logger.debug("=" * 60)
        logger.debug("ORCHESTRATOR: BURN RESULT DEBUG INFO")
        logger.debug("=" * 60)
        logger.info(f"Burn completed: disc {disc_number}, status={result.status.value}")
        logger.debug(f"Started at: {result.started_at}")
        logger.debug(f"Completed at: {result.completed_at}")
        if result.started_at and result.completed_at:
            logger.debug(f"Duration: {result.completed_at - result.started_at}")
        if result.error_message:
            logger.error(f"Error message: {result.error_message}")
        if result.command_output:
            logger.debug(f"Command output length: {len(result.command_output)} chars")
            logger.debug(f"Command output (last 50 lines):")
            output_lines = result.command_output.split('\\n')
            for line in output_lines[-50:]:
                logger.debug(f"  | {line}")
        else:
            logger.warning("No command output captured - this may indicate the burn didn't execute properly")
        logger.debug("=" * 60)

        # Verify if enabled
        if self.config.burning.verify_after_burn and result.status == BurnStatus.SUCCESS:
            self._set_state(OrchestratorState.VERIFYING)
            # Basic verification would go here

        # Export track list if burn was successful
        if result.status == BurnStatus.SUCCESS:
            track_list_path = self._export_track_list(disc_number, staged)
            if track_list_path:
                self._emit(OrchestratorEvent.PROGRESS, {
                    "step": "track_list_exported",
                    "disc_number": disc_number,
                    "message": f"Track list exported to {track_list_path.name}",
                })

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
        await self._step_fetch_playlist(playlist_name, playlist_id)
        await self._step_resolve_all_tracks()
        await self._step_plan()

        return self.session.burn_plan

    # =========================================================================
    # Audio CD Staging
    # =========================================================================

    async def _stage_audio_cd(
        self,
        disc_number: int,
        disc_plan,
        track_lookup: dict[str, Any],
    ) -> StagedDisc:
        """Stage files for an audio CD (Red Book).
        
        Audio CDs require:
        - WAV format (16-bit, 44.1kHz, stereo PCM)
        - TOC file for cdrdao
        
        Args:
            disc_number: Disc number being staged.
            disc_plan: DiscPlan with track assignments.
            track_lookup: Map of track IDs to Track objects.
            
        Returns:
            StagedDisc with WAV files and TOC.
        """
        from navidisc.models import StagedFile
        
        # Create disc directory
        disc_dir = self.config.media.staging_dir / f"disc_{disc_number:02d}"
        disc_dir.mkdir(parents=True, exist_ok=True)
        
        wav_converter = self._get_wav_converter()
        wav_converter.prepare()
        
        staged_files = []
        audio_tracks = []
        
        self._emit(OrchestratorEvent.PROGRESS, {
            "step": "converting_wav",
            "disc_number": disc_number,
            "message": f"Converting {disc_plan.track_count} tracks to WAV for audio CD...",
        })
        
        for idx, track_entry in enumerate(disc_plan.tracks, start=1):
            track_id = track_entry.track_id
            source_path = self._track_paths.get(track_id)
            track = track_lookup.get(track_id)
            
            if not source_path or not track:
                logger.warning(f"Track {track_id} not found, skipping")
                continue
            
            # Convert to WAV
            logger.debug(f"Converting track {idx}/{disc_plan.track_count}: {track.title}")
            wav_path = await wav_converter.convert(source_path)
            
            # Copy/move WAV to disc directory with proper naming
            dest_filename = f"{idx:02d} - {self._sanitize_filename(track.title)}.wav"
            dest_path = disc_dir / dest_filename
            
            # Copy the WAV file to disc directory
            shutil.copy2(wav_path, dest_path)
            
            # Get duration for TOC
            duration = await ffprobe_duration(dest_path)
            if duration is None:
                duration = float(track.duration)
            
            # Track staged file
            staged_files.append(StagedFile(
                track_id=track_id,
                source_path=source_path,
                staged_path=dest_path,
                filename=dest_filename,
            ))
            
            # Build AudioTrack for TOC
            audio_tracks.append(AudioTrack(
                track_number=idx,
                file_path=dest_path,
                title=track.title,
                artist=track.artist,
                duration_seconds=duration,
                album=self._source.name if self._source else "",
            ))
            
            self._emit(OrchestratorEvent.PROGRESS, {
                "step": "converting_wav",
                "disc_number": disc_number,
                "message": f"Converted {idx}/{disc_plan.track_count}: {track.title}",
                "percent": (idx / disc_plan.track_count) * 100,
            })
        
        # Generate TOC file for cdrdao
        toc_path = disc_dir / "disc.toc"
        album_title = f"{self._source.name} - Disc {disc_number}" if self._source else f"Disc {disc_number}"
        
        write_toc_file(
            output_path=toc_path,
            tracks=audio_tracks,
            album_title=album_title,
            album_artist="",  # Could extract from tracks if all same artist
            gap_seconds=self.config.burning.track_gap_seconds,
            include_cd_text=self.config.burning.cd_text,
        )
        
        logger.info(f"Generated TOC file: {toc_path}")
        
        # Calculate total size (for info)
        total_size = sum(f.staged_path.stat().st_size for f in staged_files if f.staged_path.exists())
        
        return StagedDisc(
            disc_number=disc_number,
            directory=disc_dir,
            files=staged_files,
            total_size_bytes=total_size,
        )

    # =========================================================================
    # Track List Export
    # =========================================================================

    def _export_track_list(self, disc_number: int, staged: StagedDisc) -> Path | None:
        """Export track list for a burned disc.
        
        Creates a text file with the actual track list that was burned,
        based on the staged files (not the burn plan, which may differ).
        
        Args:
            disc_number: Disc number that was burned.
            staged: StagedDisc containing the actual files burned.
            
        Returns:
            Path to the exported file, or None if export failed.
        """
        if not self._source:
            logger.warning("Cannot export track list: no source loaded")
            return None
        
        # Build track lookup
        track_lookup = {t.id: t for t in self._source.tracks}
        
        # Sanitize source name for filename
        safe_name = self._sanitize_filename(self._source.name)
        filename = f"{safe_name} - Disc {disc_number:02d}.txt"
        
        # Write to staging directory
        output_path = self.config.media.staging_dir / filename
        
        try:
            lines = []
            lines.append(f"{self._source.name} - Disc {disc_number}")
            lines.append("=" * len(lines[0]))
            lines.append("")
            
            for idx, staged_file in enumerate(staged.files, start=1):
                track = track_lookup.get(staged_file.track_id)
                if track:
                    lines.append(f"{idx:02d}. {track.title} - {track.artist}")
                else:
                    # Fallback to filename if track not found
                    lines.append(f"{idx:02d}. {staged_file.filename}")
            
            lines.append("")
            lines.append(f"Total tracks: {len(staged.files)}")
            
            output_path.write_text("\n".join(lines), encoding="utf-8")
            logger.info(f"Exported track list to {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to export track list: {e}")
            return None
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as a filename.
        
        Removes or replaces characters that are invalid in filenames.
        """
        # Replace invalid characters with underscores
        invalid_chars = '<>:"/\\|?*'
        result = name
        for char in invalid_chars:
            result = result.replace(char, '_')
        # Collapse multiple underscores
        while '__' in result:
            result = result.replace('__', '_')
        # Strip leading/trailing whitespace and underscores
        return result.strip(' _')

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
