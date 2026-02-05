"""Console UI for Navidisc.

Provides rich console output using the Rich library.
This module contains NO business logic - only presentation.
"""

from typing import Any

from rich.console import Console as RichConsole
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.theme import Theme

from navidisc.core import OrchestratorEvent
from navidisc.models import BurnPlan, BurnResult, BurnStatus

# Custom theme for Navidisc
NAVIDISC_THEME = Theme({
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "bold red",
    "disc": "bold magenta",
    "track": "dim",
})


class Console:
    """Rich console interface for Navidisc.
    
    Provides formatted output for the burn workflow.
    Contains no business logic - pure presentation.
    """

    def __init__(self, quiet: bool = False):
        """Initialize the console.
        
        Args:
            quiet: If True, minimize output.
        """
        self.console = RichConsole(theme=NAVIDISC_THEME)
        self.quiet = quiet

    def banner(self) -> None:
        """Display the Navidisc banner."""
        if self.quiet:
            return

        self.console.print()
        self.console.print(
            Panel.fit(
                "[bold cyan]Navidisc[/] - Burn Navidrome playlists to CD",
                border_style="cyan",
            )
        )
        self.console.print()

    def info(self, message: str) -> None:
        """Display an info message."""
        if not self.quiet:
            self.console.print(f"[info]ℹ[/] {message}")

    def success(self, message: str) -> None:
        """Display a success message."""
        self.console.print(f"[success]✓[/] {message}")

    def warning(self, message: str) -> None:
        """Display a warning message."""
        self.console.print(f"[warning]⚠[/] {message}")

    def error(self, message: str) -> None:
        """Display an error message."""
        self.console.print(f"[error]✗[/] {message}")

    def print_playlist_info(self, name: str, track_count: int, duration_minutes: float) -> None:
        """Display playlist information."""
        self.console.print()
        self.console.print(f"[bold]Playlist:[/] {name}")
        self.console.print(f"  Tracks: {track_count}")
        self.console.print(f"  Duration: {duration_minutes:.1f} minutes")
        self.console.print()

    def print_plan_summary(self, plan: BurnPlan, plan_summary: dict) -> None:
        """Display a burn plan summary."""
        self.console.print()
        self.console.print(Panel(
            f"[bold]{plan.playlist_name}[/]\n"
            f"Type: {plan.disc_type.value.upper()} disc\n"
            f"Discs required: {plan.total_discs}",
            title="Burn Plan",
            border_style="cyan",
        ))

        # Disc details table
        table = Table(title="Disc Breakdown", show_header=True)
        table.add_column("Disc", style="disc")
        table.add_column("Tracks", justify="right")
        table.add_column("Size (MB)", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("Usage", justify="right")

        for disc_info in plan_summary.get("discs", []):
            duration_min = disc_info["duration_minutes"]
            duration_str = f"{int(duration_min)}:{int((duration_min % 1) * 60):02d}"
            usage = disc_info.get("capacity_percent", 0)

            table.add_row(
                f"Disc {disc_info['disc_number']}",
                str(disc_info["tracks"]),
                f"{disc_info['size_mb']:.1f}",
                duration_str,
                f"{usage:.1f}%",
            )

        self.console.print(table)
        self.console.print()

    def print_disc_prompt(self, disc_number: int, total_discs: int, device: str) -> None:
        """Prompt user to insert a disc."""
        self.console.print()
        self.console.print(Panel(
            f"[bold disc]Insert blank disc {disc_number} of {total_discs}[/]\n"
            f"Device: {device}\n\n"
            "Press [bold]Enter[/] when ready...",
            title="Disc Required",
            border_style="magenta",
        ))

    def print_burn_result(self, result: BurnResult) -> None:
        """Display a burn result."""
        if result.status == BurnStatus.SUCCESS:
            self.success(
                f"Disc {result.disc_number} burned successfully "
                f"({result.duration_seconds:.1f}s)"
            )
        elif result.status == BurnStatus.FAILED:
            self.error(
                f"Disc {result.disc_number} burn failed: {result.error_message}"
            )
        elif result.status == BurnStatus.SKIPPED:
            self.warning(f"Disc {result.disc_number} skipped")

    def print_final_summary(self, results: list[BurnResult]) -> None:
        """Display final burn summary."""
        self.console.print()

        success_count = sum(1 for r in results if r.status == BurnStatus.SUCCESS)
        failed_count = sum(1 for r in results if r.status == BurnStatus.FAILED)

        if failed_count == 0:
            self.console.print(Panel(
                f"[success]All {success_count} disc(s) burned successfully![/]",
                title="Complete",
                border_style="green",
            ))
        else:
            self.console.print(Panel(
                f"[warning]Completed with errors[/]\n"
                f"Success: {success_count}, Failed: {failed_count}",
                title="Complete",
                border_style="yellow",
            ))

        self.console.print()

    def confirm(self, message: str, default: bool = False) -> bool:
        """Ask for user confirmation.
        
        Args:
            message: Confirmation message.
            default: Default value if user just presses Enter.
            
        Returns:
            True if confirmed, False otherwise.
        """
        suffix = "[Y/n]" if default else "[y/N]"
        response = self.console.input(f"{message} {suffix} ").strip().lower()

        if not response:
            return default
        return response in ("y", "yes")

    def wait_for_enter(self) -> None:
        """Wait for user to press Enter."""
        self.console.input()


class ProgressDisplay:
    """Progress display using Rich progress bars.
    
    Provides visual feedback during long-running operations.
    """

    def __init__(self, console: Console):
        """Initialize progress display.
        
        Args:
            console: Console instance to use.
        """
        self.console = console
        self._progress: Progress | None = None
        self._task_id: int | None = None

    def start(self, description: str = "Working...") -> None:
        """Start the progress display."""
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console.console,
        )
        self._progress.start()
        self._task_id = self._progress.add_task(description, total=100)

    def update(self, description: str | None = None, completed: float | None = None) -> None:
        """Update progress.
        
        Args:
            description: New description text.
            completed: Completion percentage (0-100).
        """
        if self._progress and self._task_id is not None:
            kwargs = {}
            if description:
                kwargs["description"] = description
            if completed is not None:
                kwargs["completed"] = completed
            self._progress.update(self._task_id, **kwargs)

    def stop(self) -> None:
        """Stop the progress display."""
        if self._progress:
            self._progress.stop()
            self._progress = None
            self._task_id = None


def create_event_handler(console: Console, progress: ProgressDisplay) -> callable:
    """Create an event handler for the orchestrator.
    
    Args:
        console: Console instance.
        progress: Progress display instance.
        
    Returns:
        Event handler callback function.
    """
    def handle_event(event: OrchestratorEvent, data: dict[str, Any]) -> None:
        if event == OrchestratorEvent.STATE_CHANGED:
            # State changes are logged at debug level
            pass

        elif event == OrchestratorEvent.PROGRESS:
            step = data.get("step", "")
            message = data.get("message", "")
            percent = data.get("percent")

            if percent is not None:
                progress.update(description=message, completed=percent)
            else:
                console.info(message)

        elif event == OrchestratorEvent.DISC_REQUIRED:
            progress.stop()
            console.print_disc_prompt(
                data["disc_number"],
                data["total_discs"],
                data["device"],
            )
            console.wait_for_enter()
            progress.start(f"Burning disc {data['disc_number']}...")

        elif event == OrchestratorEvent.BURN_STARTED:
            progress.update(
                description=f"Burning disc {data['disc_number']}/{data['total_discs']}...",
                completed=0,
            )

        elif event == OrchestratorEvent.BURN_PROGRESS:
            percent = data.get("percent", 0)
            message = data.get("message", "Burning...")
            progress.update(description=message, completed=percent)

        elif event == OrchestratorEvent.BURN_COMPLETED:
            progress.stop()
            from navidisc.models import BurnResult
            result = BurnResult.model_validate(data["result"])
            console.print_burn_result(result)

        elif event == OrchestratorEvent.ERROR:
            progress.stop()
            console.error(data.get("message", "Unknown error"))

        elif event == OrchestratorEvent.COMPLETE:
            progress.stop()

    return handle_event
