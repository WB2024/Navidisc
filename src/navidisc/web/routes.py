"""API routes for Navidisc web interface."""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from navidisc.api import SubsonicClient
from navidisc.config import (
    NavidiscConfig,
    get_default_config_path,
    save_config,
)
from navidisc.core import Orchestrator, OrchestratorEvent
from navidisc.media.converter import estimate_mp3_size
from navidisc.models import AudioCDBurnMode, ConversionQuality, DiscType, DownloadMode, MediaType, WriteSpeed
from navidisc.planner import DiscPlanningEngine

router = APIRouter()


# =============================================================================
# Dependencies
# =============================================================================


def get_templates(request: Request):
    """Get Jinja2 templates from app state."""
    return request.app.state.templates


def get_config(request: Request) -> NavidiscConfig | None:
    """Get current configuration from app state."""
    return request.app.state.config


# =============================================================================
# Request/Response Models
# =============================================================================


class ConfigUpdate(BaseModel):
    """Configuration update request."""

    navidrome_url: str
    navidrome_username: str
    navidrome_password: str
    device: str = "/dev/sr0"
    disc_type: str = "data"
    disc_size_mb: int = 700


class BurnRequest(BaseModel):
    """Burn request."""

    playlist_id: str | None = None
    playlist_name: str | None = None
    album_id: str | None = None
    album_name: str | None = None
    dry_run: bool = False
    selected_discs: list[int] | None = None  # If None, burn all discs
    
    @property
    def source_id(self) -> str:
        """Get the source ID (playlist or album)."""
        return self.playlist_id or self.album_id or ""
    
    @property
    def source_name(self) -> str:
        """Get the source name (playlist or album)."""
        return self.playlist_name or self.album_name or ""
    
    @property
    def is_album(self) -> bool:
        """Whether this is an album burn request."""
        return self.album_id is not None


# =============================================================================
# Page Routes
# =============================================================================


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page."""
    templates = get_templates(request)
    config = get_config(request)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "config": config,
            "has_config": config is not None,
        },
    )


@router.get("/playlists", response_class=HTMLResponse)
async def playlists_page(request: Request):
    """Playlists page."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "message": "Please configure Navidrome settings first",
            },
        )

    return templates.TemplateResponse(
        "playlists.html",
        {
            "request": request,
            "config": config,
            "has_config": config is not None,
        },
    )


@router.get("/albums", response_class=HTMLResponse)
async def albums_page(request: Request):
    """Albums page."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "message": "Please configure Navidrome settings first",
            },
        )

    return templates.TemplateResponse(
        "albums.html",
        {
            "request": request,
            "config": config,
            "has_config": config is not None,
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    templates = get_templates(request)
    config = get_config(request)

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "config": config,
            "has_config": config is not None,
        },
    )


@router.get("/burn/{playlist_id}", response_class=HTMLResponse)
async def burn_page(request: Request, playlist_id: str):
    """Burn workflow page."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        raise HTTPException(status_code=400, detail="Not configured")

    return templates.TemplateResponse(
        "burn.html",
        {
            "request": request,
            "config": config,
            "playlist_id": playlist_id,
            "album_id": None,
            "source_type": "playlist",
            "has_config": config is not None,
        },
    )


@router.get("/burn/album/{album_id}", response_class=HTMLResponse)
async def burn_album_page(request: Request, album_id: str):
    """Burn workflow page for albums."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        raise HTTPException(status_code=400, detail="Not configured")

    return templates.TemplateResponse(
        "burn.html",
        {
            "request": request,
            "config": config,
            "playlist_id": None,
            "album_id": album_id,
            "source_type": "album",
            "has_config": config is not None,
        },
    )


# =============================================================================
# API Routes - Playlists
# =============================================================================


@router.get("/api/playlists", response_class=HTMLResponse)
async def get_playlists(request: Request):
    """Fetch playlists from Navidrome."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": "Not configured"},
        )

    try:
        async with SubsonicClient(
            base_url=config.navidrome.url,
            username=config.navidrome.username,
            password=config.navidrome.password,
        ) as client:
            playlists = await client.get_playlists()

            return templates.TemplateResponse(
                "partials/playlist_list.html",
                {
                    "request": request,
                    "playlists": playlists,
                },
            )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": str(e)},
        )


# =============================================================================
# API Routes - Albums
# =============================================================================


@router.get("/api/albums", response_class=HTMLResponse)
async def get_albums(request: Request):
    """Fetch albums from Navidrome."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": "Not configured"},
        )

    try:
        async with SubsonicClient(
            base_url=config.navidrome.url,
            username=config.navidrome.username,
            password=config.navidrome.password,
        ) as client:
            albums = await client.get_albums()

            return templates.TemplateResponse(
                "partials/album_list.html",
                {
                    "request": request,
                    "albums": albums,
                },
            )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": str(e)},
        )


@router.get("/api/album/{album_id}", response_class=HTMLResponse)
async def get_album_details(request: Request, album_id: str):
    """Get album details with tracks."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": "Not configured"},
        )

    try:
        async with SubsonicClient(
            base_url=config.navidrome.url,
            username=config.navidrome.username,
            password=config.navidrome.password,
        ) as client:
            album = await client.get_album(album_id)

            # Create a plan to show disc breakdown
            planner = DiscPlanningEngine(
                disc_type=config.burning.disc_type,
                disc_capacity_bytes=config.burning.disc_size_bytes,
                disc_capacity_seconds=config.burning.audio_disc_seconds,
            )

            # Build size lookup from track data
            # If conversion is enabled, estimate post-conversion MP3 sizes
            quality = config.media.conversion_quality
            size_lookup = {}
            for t in album.tracks:
                if quality != ConversionQuality.DISABLED and t.duration_seconds and t.format and t.format.lower() != "mp3":
                    size_lookup[t.id] = estimate_mp3_size(t.duration_seconds, quality)
                elif t.size_bytes:
                    size_lookup[t.id] = t.size_bytes

            try:
                plan = planner.plan(album, size_lookup)
                plan_summary = planner.get_plan_summary(plan)
            except Exception:
                plan = None
                plan_summary = None

            return templates.TemplateResponse(
                "partials/album_details.html",
                {
                    "request": request,
                    "album": album,
                    "plan": plan,
                    "plan_summary": plan_summary,
                    "config": config,
                },
            )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": str(e)},
        )


@router.get("/api/playlist/{playlist_id}", response_class=HTMLResponse)
async def get_playlist_details(request: Request, playlist_id: str):
    """Get playlist details with tracks."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": "Not configured"},
        )

    try:
        async with SubsonicClient(
            base_url=config.navidrome.url,
            username=config.navidrome.username,
            password=config.navidrome.password,
        ) as client:
            playlist = await client.get_playlist(playlist_id)

            # Create a plan to show disc breakdown
            planner = DiscPlanningEngine(
                disc_type=config.burning.disc_type,
                disc_capacity_bytes=config.burning.disc_size_bytes,
                disc_capacity_seconds=config.burning.audio_disc_seconds,
            )

            # Build size lookup from track data
            # If conversion is enabled, estimate post-conversion MP3 sizes
            quality = config.media.conversion_quality
            size_lookup = {}
            for t in playlist.tracks:
                if quality != ConversionQuality.DISABLED and t.duration_seconds and t.format and t.format.lower() != "mp3":
                    size_lookup[t.id] = estimate_mp3_size(t.duration_seconds, quality)
                elif t.size_bytes:
                    size_lookup[t.id] = t.size_bytes

            try:
                plan = planner.plan(playlist, size_lookup)
                plan_summary = planner.get_plan_summary(plan)
            except Exception:
                plan = None
                plan_summary = None

            return templates.TemplateResponse(
                "partials/playlist_details.html",
                {
                    "request": request,
                    "playlist": playlist,
                    "plan": plan,
                    "plan_summary": plan_summary,
                    "config": config,
                },
            )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": str(e)},
        )


# =============================================================================
# API Routes - Albums
# =============================================================================


@router.get("/api/albums", response_class=HTMLResponse)
async def get_albums(request: Request):
    """Fetch albums from Navidrome."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": "Not configured"},
        )

    try:
        async with SubsonicClient(
            base_url=config.navidrome.url,
            username=config.navidrome.username,
            password=config.navidrome.password,
        ) as client:
            albums = await client.get_albums()

            return templates.TemplateResponse(
                "partials/album_list.html",
                {
                    "request": request,
                    "albums": albums,
                },
            )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": str(e)},
        )


@router.get("/api/album/{album_id}", response_class=HTMLResponse)
async def get_album_details(request: Request, album_id: str):
    """Get album details with tracks."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": "Not configured"},
        )

    try:
        async with SubsonicClient(
            base_url=config.navidrome.url,
            username=config.navidrome.username,
            password=config.navidrome.password,
        ) as client:
            album = await client.get_album(album_id)

            # Create a plan to show disc breakdown
            planner = DiscPlanningEngine(
                disc_type=config.burning.disc_type,
                disc_capacity_bytes=config.burning.disc_size_bytes,
                disc_capacity_seconds=config.burning.audio_disc_seconds,
            )

            # Build size lookup from track data
            # If conversion is enabled, estimate post-conversion MP3 sizes
            quality = config.media.conversion_quality
            size_lookup = {}
            for t in album.tracks:
                if quality != ConversionQuality.DISABLED and t.duration_seconds and t.format and t.format.lower() != "mp3":
                    size_lookup[t.id] = estimate_mp3_size(t.duration_seconds, quality)
                elif t.size_bytes:
                    size_lookup[t.id] = t.size_bytes

            try:
                plan = planner.plan(album, size_lookup)
                plan_summary = planner.get_plan_summary(plan)
            except Exception:
                plan = None
                plan_summary = None

            return templates.TemplateResponse(
                "partials/album_details.html",
                {
                    "request": request,
                    "album": album,
                    "plan": plan,
                    "plan_summary": plan_summary,
                    "config": config,
                },
            )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": str(e)},
        )


# =============================================================================
# API Routes - Configuration
# =============================================================================


@router.post("/api/config", response_class=HTMLResponse)
async def save_configuration(request: Request):
    """Save configuration."""
    templates = get_templates(request)

    try:
        # Get form data
        form = await request.form()
        navidrome_url = form.get("navidrome_url", "").strip()
        navidrome_username = form.get("navidrome_username", "").strip()
        navidrome_password = form.get("navidrome_password", "")
        device = form.get("device", "/dev/sr0")
        disc_type = form.get("disc_type", "data")
        media_type = form.get("media_type", "auto")
        write_speed = form.get("write_speed", "auto")
        conversion_quality = form.get("conversion_quality", "disabled")
        auto_cleanup = form.get("auto_cleanup") == "true"
        local_library_path = form.get("local_library_path", "").strip() or None
        download_mode = form.get("download_mode", "download-if-missing")
        staging_dir = form.get("staging_dir", "").strip() or "/tmp/navidisc"
        
        # Audio CD settings
        audio_burn_mode = form.get("audio_burn_mode", "dao")
        track_gap_seconds_str = form.get("track_gap_seconds", "2")
        cd_text = form.get("cd_text") == "true"
        
        try:
            track_gap_seconds = int(track_gap_seconds_str)
        except ValueError:
            track_gap_seconds = 2
        
        # Validate required fields
        if not navidrome_url or not navidrome_username or not navidrome_password:
            return templates.TemplateResponse(
                "partials/error.html",
                {"request": request, "message": "All Navidrome fields are required"},
            )
        
        # Validate disc size
        try:
            disc_size_mb = int(form.get("disc_size_mb", "700"))
        except ValueError:
            return templates.TemplateResponse(
                "partials/error.html",
                {"request": request, "message": "Invalid disc size value"},
            )

        # Build config object
        from navidisc.config import (
            BurningConfig,
            LoggingConfig,
            MediaConfig,
            NavidiscConfig,
            NavidromeConfig,
        )

        config = NavidiscConfig(
            navidrome=NavidromeConfig(
                url=navidrome_url,
                username=navidrome_username,
                password=navidrome_password,
            ),
            burning=BurningConfig(
                device=device,
                disc_type=DiscType(disc_type),
                disc_size_mb=disc_size_mb,
                media_type=MediaType(media_type),
                write_speed=WriteSpeed(write_speed),
                audio_burn_mode=AudioCDBurnMode(audio_burn_mode),
                track_gap_seconds=track_gap_seconds,
                cd_text=cd_text,
            ),
            media=MediaConfig(
                staging_dir=Path(staging_dir),
                local_library_path=Path(local_library_path) if local_library_path else None,
                download_mode=DownloadMode(download_mode),
                conversion_quality=ConversionQuality(conversion_quality),
                auto_cleanup=auto_cleanup,
            ),
            logging=LoggingConfig(),
        )

        # Save to file
        config_path = get_default_config_path()
        save_config(config, config_path)
        
        # Log what was saved for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Config saved: staging_dir={config.media.staging_dir}, local_library_path={config.media.local_library_path}, download_mode={config.media.download_mode.value}")

        # Update app state
        request.app.state.config = config

        return templates.TemplateResponse(
            "partials/success.html",
            {
                "request": request,
                "message": "Configuration saved successfully!",
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": str(e)},
        )


@router.post("/api/test-connection", response_class=HTMLResponse)
async def test_connection(request: Request):
    """Test Navidrome connection."""
    templates = get_templates(request)

    # Get form data
    try:
        form = await request.form()
        navidrome_url = form.get("navidrome_url")
        navidrome_username = form.get("navidrome_username")
        navidrome_password = form.get("navidrome_password")

        if not all([navidrome_url, navidrome_username, navidrome_password]):
            return templates.TemplateResponse(
                "partials/error.html",
                {"request": request, "message": "Missing required fields"},
            )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": f"Form error: {e}"},
        )

    try:
        async with SubsonicClient(
            base_url=navidrome_url,
            username=navidrome_username,
            password=navidrome_password,
        ) as client:
            await client.authenticate()
            playlists = await client.get_playlists()
            albums = await client.get_albums(size=10)  # Just get first 10 to verify

            return templates.TemplateResponse(
                "partials/success.html",
                {
                    "request": request,
                    "message": f"Connected! Found {len(playlists)} playlists and {len(albums)}+ albums.",
                },
            )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": f"Connection failed: {e}"},
        )


# =============================================================================
# API Routes - Burn Workflow
# =============================================================================


@router.post("/api/burn/start")
async def start_burn(request: Request, burn_request: BurnRequest):
    """Start a burn workflow."""
    config = get_config(request)

    if not config:
        raise HTTPException(status_code=400, detail="Not configured")

    # Generate session ID
    session_id = str(uuid.uuid4())[:8]

    # Store session info
    request.app.state.active_sessions[session_id] = {
        "playlist_id": burn_request.playlist_id,
        "playlist_name": burn_request.playlist_name,
        "album_id": burn_request.album_id,
        "album_name": burn_request.album_name,
        "is_album": burn_request.is_album,
        "dry_run": burn_request.dry_run,
        "selected_discs": burn_request.selected_discs,  # None = all discs
        "status": "starting",
        "events": asyncio.Queue(),
        "cancelled": False,
    }

    return {"session_id": session_id}


@router.post("/api/burn/cancel/{session_id}")
async def cancel_burn(request: Request, session_id: str):
    """Cancel a running burn workflow."""
    if session_id not in request.app.state.active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = request.app.state.active_sessions[session_id]
    session["cancelled"] = True
    session["events"].put_nowait({
        "event": "cancelled",
        "data": {"message": "Burn cancelled by user"},
    })

    return {"status": "cancelled"}


@router.get("/api/burn/stream/{session_id}")
async def burn_stream(request: Request, session_id: str):
    """Server-Sent Events stream for burn progress."""
    config = get_config(request)

    if session_id not in request.app.state.active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = request.app.state.active_sessions[session_id]

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        try:
            # Create orchestrator
            orchestrator = Orchestrator(config, dry_run=session["dry_run"])

            # Event handler that puts events in the queue
            def handle_event(event: OrchestratorEvent, data: dict[str, Any]):
                session["events"].put_nowait(
                    {"event": event.value, "data": data}
                )

            # Start the burn workflow in background
            async def run_burn():
                try:
                    async with orchestrator:
                        if session.get("is_album") and session.get("album_id"):
                            # Burn album
                            await orchestrator.run_album_burn(
                                album_id=session["album_id"],
                                event_handler=handle_event,
                                selected_discs=session.get("selected_discs"),
                            )
                        else:
                            # Burn playlist
                            await orchestrator.run_playlist_burn(
                                playlist_id=session["playlist_id"],
                                event_handler=handle_event,
                                selected_discs=session.get("selected_discs"),
                            )
                except Exception as e:
                    session["events"].put_nowait(
                        {
                            "event": "error",
                            "data": {"message": str(e)},
                        }
                    )
                finally:
                    session["events"].put_nowait({"event": "done", "data": {}})

            # Start burn task
            burn_task = asyncio.create_task(run_burn())

            # Stream events
            while True:
                try:
                    event = await asyncio.wait_for(
                        session["events"].get(), timeout=30.0
                    )

                    yield f"data: {json.dumps(event)}\n\n"

                    if event["event"] == "done":
                        break
                except TimeoutError:
                    # Send keepalive
                    yield f"data: {json.dumps({'event': 'keepalive', 'data': {}})}\n\n"

            await burn_task

        finally:
            # Cleanup session
            if session_id in request.app.state.active_sessions:
                del request.app.state.active_sessions[session_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/burn/plan/{playlist_id}", response_class=HTMLResponse)
async def get_burn_plan(request: Request, playlist_id: str):
    """Get burn plan for a playlist."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": "Not configured"},
        )

    try:
        async with SubsonicClient(
            base_url=config.navidrome.url,
            username=config.navidrome.username,
            password=config.navidrome.password,
        ) as client:
            playlist = await client.get_playlist(playlist_id)

        planner = DiscPlanningEngine(
            disc_type=config.burning.disc_type,
            disc_capacity_bytes=config.burning.disc_size_bytes,
            disc_capacity_seconds=config.burning.audio_disc_seconds,
        )

        # Build size lookup - estimate post-conversion sizes if conversion enabled
        quality = config.media.conversion_quality
        size_lookup = {}
        for t in playlist.tracks:
            if quality != ConversionQuality.DISABLED and t.duration_seconds and t.format and t.format.lower() != "mp3":
                size_lookup[t.id] = estimate_mp3_size(t.duration_seconds, quality)
            elif t.size_bytes:
                size_lookup[t.id] = t.size_bytes
        plan = planner.plan(playlist, size_lookup)
        plan_summary = planner.get_plan_summary(plan)

        return templates.TemplateResponse(
            "partials/burn_plan.html",
            {
                "request": request,
                "playlist": playlist,
                "plan": plan,
                "plan_summary": plan_summary,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": str(e)},
        )


@router.get("/api/burn/plan/album/{album_id}", response_class=HTMLResponse)
async def get_burn_plan_album(request: Request, album_id: str):
    """Get burn plan for an album."""
    templates = get_templates(request)
    config = get_config(request)

    if not config:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": "Not configured"},
        )

    try:
        async with SubsonicClient(
            base_url=config.navidrome.url,
            username=config.navidrome.username,
            password=config.navidrome.password,
        ) as client:
            album = await client.get_album(album_id)

        planner = DiscPlanningEngine(
            disc_type=config.burning.disc_type,
            disc_capacity_bytes=config.burning.disc_size_bytes,
            disc_capacity_seconds=config.burning.audio_disc_seconds,
        )

        # Build size lookup - estimate post-conversion sizes if conversion enabled
        quality = config.media.conversion_quality
        size_lookup = {}
        for t in album.tracks:
            if quality != ConversionQuality.DISABLED and t.duration_seconds and t.format and t.format.lower() != "mp3":
                size_lookup[t.id] = estimate_mp3_size(t.duration_seconds, quality)
            elif t.size_bytes:
                size_lookup[t.id] = t.size_bytes
        plan = planner.plan(album, size_lookup)
        plan_summary = planner.get_plan_summary(plan)

        return templates.TemplateResponse(
            "partials/burn_plan.html",
            {
                "request": request,
                "album": album,
                "plan": plan,
                "plan_summary": plan_summary,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": str(e)},
        )
