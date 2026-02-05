"""Navidisc CLI entry point.

Provides the command-line interface for Navidisc.
"""

import asyncio
import json
import sys
from pathlib import Path

import click

from navidisc import __version__
from navidisc.config import (
    NavidiscConfig,
    create_example_config,
    get_default_config_path,
    load_config,
)
from navidisc.core import Orchestrator
from navidisc.models import DiscType
from navidisc.planner import DiscPlanningEngine
from navidisc.ui import Console, ProgressDisplay
from navidisc.ui.console import create_event_handler


# Common options
def common_options(f):
    """Common CLI options."""
    f = click.option(
        "--config", "-c",
        type=click.Path(exists=True, path_type=Path),
        help="Path to configuration file.",
    )(f)
    f = click.option(
        "--verbose", "-v",
        is_flag=True,
        help="Enable verbose output.",
    )(f)
    f = click.option(
        "--quiet", "-q",
        is_flag=True,
        help="Minimize output.",
    )(f)
    return f


def load_config_with_fallback(config_path: Path | None) -> NavidiscConfig:
    """Load configuration with fallback to default path.
    
    Args:
        config_path: Explicit config path or None.
        
    Returns:
        Loaded configuration.
        
    Raises:
        click.ClickException: If config cannot be loaded.
    """
    path = config_path or get_default_config_path()

    if not path.exists():
        raise click.ClickException(
            f"Configuration file not found: {path}\n"
            f"Run 'navidisc config init' to create one."
        )

    try:
        return load_config(path)
    except Exception as e:
        raise click.ClickException(f"Failed to load configuration: {e}")


@click.group()
@click.version_option(version=__version__)
def cli():
    """Navidisc - Burn Navidrome playlists to CD."""
    pass


# =============================================================================
# Burn commands
# =============================================================================

@cli.group()
def burn():
    """Burn playlists to disc."""
    pass


@burn.command(name="playlist")
@click.argument("name", required=False)
@click.option("--id", "playlist_id", help="Playlist ID (alternative to name).")
@click.option(
    "--disc-type", "-t",
    type=click.Choice(["data", "audio"]),
    help="Override disc type from config.",
)
@click.option("--device", "-d", help="Override device from config.")
@click.option("--dry-run", is_flag=True, help="Plan only, don't burn.")
@click.option("--no-verify", is_flag=True, help="Skip post-burn verification.")
@click.option("--no-eject", is_flag=True, help="Don't eject disc after burn.")
@click.option("--output-plan", "-o", type=click.Path(path_type=Path), help="Save plan to JSON.")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompts.")
@common_options
def burn_playlist(
    name: str | None,
    playlist_id: str | None,
    disc_type: str | None,
    device: str | None,
    dry_run: bool,
    no_verify: bool,
    no_eject: bool,
    output_plan: Path | None,
    force: bool,
    config: Path | None,
    verbose: bool,
    quiet: bool,
):
    """Burn a playlist to disc.
    
    Specify the playlist by NAME or use --id for the playlist ID.
    
    Examples:
    
        navidisc burn playlist "Road Trip"
        
        navidisc burn playlist --id abc123 --disc-type audio
        
        navidisc burn playlist "Road Trip" --dry-run
    """
    if not name and not playlist_id:
        raise click.UsageError("Must provide playlist name or --id")

    # Load configuration
    cfg = load_config_with_fallback(config)

    # Apply overrides
    if disc_type:
        cfg.burning.disc_type = DiscType(disc_type)
    if device:
        cfg.burning.device = device
    if no_verify:
        cfg.burning.verify_after_burn = False
    if no_eject:
        cfg.burning.eject_after_burn = False

    # Set up console
    console = Console(quiet=quiet)
    progress = ProgressDisplay(console)

    if not quiet:
        console.banner()

    # Run the workflow
    async def run():
        async with Orchestrator(cfg, dry_run=dry_run) as orchestrator:
            if dry_run or output_plan:
                # Plan-only mode
                plan = await orchestrator.plan_only(
                    playlist_name=name,
                    playlist_id=playlist_id,
                    event_handler=create_event_handler(console, progress),
                )

                planner = DiscPlanningEngine(
                    disc_type=cfg.burning.disc_type,
                    disc_capacity_bytes=cfg.burning.disc_size_bytes,
                )
                summary = planner.get_plan_summary(plan)

                console.print_plan_summary(plan, summary)

                if output_plan:
                    output_plan.write_text(plan.model_dump_json(indent=2))
                    console.success(f"Plan saved to {output_plan}")

                if dry_run:
                    console.info("Dry run complete - no discs were burned")
                    return

            # Confirm before burning
            if not force and not quiet:
                if not console.confirm("Proceed with burning?"):
                    console.info("Cancelled")
                    return

            # Full burn workflow
            progress.start("Starting...")

            session = await orchestrator.run_playlist_burn(
                playlist_name=name,
                playlist_id=playlist_id,
                event_handler=create_event_handler(console, progress),
            )

            console.print_final_summary(session.burn_results)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        console.warning("Interrupted")
        sys.exit(1)
    except Exception as e:
        console.error(str(e))
        if verbose:
            raise
        sys.exit(1)


# =============================================================================
# Plan commands
# =============================================================================

@cli.group()
def plan():
    """Plan disc burns without burning."""
    pass


@plan.command(name="playlist")
@click.argument("name", required=False)
@click.option("--id", "playlist_id", help="Playlist ID.")
@click.option("--disc-type", "-t", type=click.Choice(["data", "audio"]))
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Save plan to JSON.")
@common_options
def plan_playlist(
    name: str | None,
    playlist_id: str | None,
    disc_type: str | None,
    output: Path | None,
    config: Path | None,
    verbose: bool,
    quiet: bool,
):
    """Plan how a playlist would be split across discs.
    
    This is equivalent to 'burn playlist --dry-run'.
    """
    # Delegate to burn with dry-run
    ctx = click.get_current_context()
    ctx.invoke(
        burn_playlist,
        name=name,
        playlist_id=playlist_id,
        disc_type=disc_type,
        dry_run=True,
        output_plan=output,
        force=True,
        config=config,
        verbose=verbose,
        quiet=quiet,
        device=None,
        no_verify=False,
        no_eject=False,
    )


# =============================================================================
# List commands
# =============================================================================

@cli.group(name="list")
def list_cmd():
    """List available resources."""
    pass


@list_cmd.command(name="playlists")
@common_options
def list_playlists(config: Path | None, verbose: bool, quiet: bool):
    """List available playlists from Navidrome."""
    cfg = load_config_with_fallback(config)
    console = Console(quiet=quiet)

    from rich.table import Table

    from navidisc.api import SubsonicClient

    async def run():
        async with SubsonicClient(
            base_url=cfg.navidrome.url,
            username=cfg.navidrome.username,
            password=cfg.navidrome.password,
        ) as client:
            playlists = await client.get_playlists()

            if not playlists:
                console.info("No playlists found")
                return

            table = Table(title="Playlists", show_header=True)
            table.add_column("ID", style="dim")
            table.add_column("Name")
            table.add_column("Tracks", justify="right")
            table.add_column("Duration", justify="right")

            for p in playlists:
                duration_min = p.duration_seconds / 60
                duration_str = f"{int(duration_min)}:{int((duration_min % 1) * 60):02d}"

                table.add_row(
                    p.id,
                    p.name,
                    str(p.track_count),
                    duration_str,
                )

            console.console.print(table)

    try:
        asyncio.run(run())
    except Exception as e:
        console.error(str(e))
        if verbose:
            raise
        sys.exit(1)


# =============================================================================
# Config commands
# =============================================================================

@cli.group()
def config():
    """Manage configuration."""
    pass


@config.command(name="init")
@click.option(
    "--path", "-p",
    type=click.Path(path_type=Path),
    help="Path for config file (default: ~/.config/navidisc/config.yaml)",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config.")
def config_init(path: Path | None, force: bool):
    """Create an example configuration file."""
    config_path = path or get_default_config_path()

    if config_path.exists() and not force:
        raise click.ClickException(
            f"Configuration file already exists: {config_path}\n"
            f"Use --force to overwrite."
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(create_example_config())

    click.echo(f"Created configuration file: {config_path}")
    click.echo("Edit this file with your Navidrome settings.")


@config.command(name="show")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path))
def config_show(config: Path | None):
    """Show current configuration."""
    cfg = load_config_with_fallback(config)

    # Mask password
    output = cfg.model_dump()
    if "navidrome" in output and "password" in output["navidrome"]:
        output["navidrome"]["password"] = "****"

    click.echo(json.dumps(output, indent=2, default=str))


@config.command(name="path")
def config_path():
    """Show default configuration file path."""
    click.echo(get_default_config_path())


# =============================================================================
# Entry point
# =============================================================================

def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
