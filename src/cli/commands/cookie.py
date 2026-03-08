"""Cookie management commands for CLI."""

import typer
from rich import print as rprint

from src.video.cookie_manager import get_cookie_manager

cookie_app = typer.Typer(help="Cookie management commands")


@cookie_app.command("extract")
def cookie_extract():
    """Extract cookies from Chrome browser for YouTube.

    This command extracts authentication cookies from Chrome browser
    which are required for accessing age-restricted content.
    """
    try:
        rprint("\n[bold blue]Extracting YouTube cookies from Chrome...[/bold blue]\n")

        manager = get_cookie_manager()
        success = manager.ensure_cookies()

        if success:
            status = manager.get_status()
            rprint(f"[green]✓ Successfully extracted and cached cookies[/green]")
            rprint(f"  [dim]Expires in approx: {status.get('cache_duration_hours', 24):.1f}h[/dim]")
            rprint(f"  [dim]Cookies: {status.get('youtube_cookies', 0)} YouTube, {status.get('google_cookies', 0)} Google[/dim]\n")
        else:
            rprint("[red]✗ Cookie extraction failed.[/red]")
            rprint("[yellow]Ensure you are logged into YouTube in Chrome browser.[/yellow]\n")
    except Exception as e:
        rprint(f"[red]✗ Error: {e}[/red]\n")


@cookie_app.command("status")
def cookie_status():
    """Show current cookie status and metadata."""
    manager = get_cookie_manager()
    status = manager.get_status()

    from rich.panel import Panel
    from rich.table import Table

    table = Table(title="YouTube Cookie Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Cache File Exists", str(status["cookie_file_exists"]))
    if status["cookie_file_exists"]:
        table.add_row("Age (hours)", f"{status['cookie_age_hours']:.2f}")
        table.add_row("Status", "Fresh" if status["is_fresh"] else "Expired")

    if "last_extracted" in status:
        table.add_row("Last Extracted", status["last_extracted"])
        table.add_row("YouTube Cookies", str(status["youtube_cookies"]))
        table.add_row("Google Cookies", str(status["google_cookies"]))
        table.add_row("Authentication Found", "Yes" if status["has_auth"] else "No")

    rprint("\n", Panel(table, expand=False), "\n")


@cookie_app.command("invalidate")
def cookie_invalidate():
    """Invalidate cookie cache to force re-extraction on next use."""
    manager = get_cookie_manager()
    manager.invalidate_cache()
    rprint("[yellow]Cookie cache invalidated. Next operation will trigger re-extraction.[/yellow]")
