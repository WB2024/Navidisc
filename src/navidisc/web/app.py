"""FastAPI application for Navidisc web interface."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from navidisc.config import get_default_config_path, load_config
from navidisc.web.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Load configuration on startup
    config_path = get_default_config_path()
    if config_path.exists():
        app.state.config = load_config(config_path)
    else:
        app.state.config = None

    app.state.active_sessions = {}

    yield

    # Cleanup on shutdown
    for session in app.state.active_sessions.values():
        if hasattr(session, 'cancel'):
            session.cancel()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Navidisc",
        description="Burn Navidrome playlists to CD",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Setup templates
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)
    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    # Setup static files
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include routes
    app.include_router(router)

    return app


# Create default app instance
app = create_app()
