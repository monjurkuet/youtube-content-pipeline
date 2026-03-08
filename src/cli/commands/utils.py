"""Utility commands for CLI."""

import os
import shutil
import subprocess

import typer
from rich import print as rprint

from src.core.constants import APP_NAME, APP_VERSION

utils_app = typer.Typer(help="Utility commands")


@utils_app.command("check-dependencies")
def check_dependencies():
    """Check and update yt-dlp and Bun runtime for 2026 YouTube compatibility.

    YouTube now requires:
    - Latest yt-dlp version (for signature deciphering)
    - Bun JS runtime (for player JS execution - preferred over deno/node)

    This command checks and updates both dependencies.
    """
    rprint("\n[bold blue]Checking YouTube Download Dependencies[/bold blue]\n")

    # Check yt-dlp version
    rprint("[bold]1. Checking yt-dlp...[/bold]")
    try:
        result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=10)
        current_version = result.stdout.strip()
        rprint(f"   Current version: [cyan]{current_version}[/cyan]")

        # Check if update is available
        rprint("   Checking for updates...")
        update_result = subprocess.run(
            ["yt-dlp", "-U"], capture_output=True, text=True, timeout=60
        )

        if "is up to date" in update_result.stdout.lower() or "is up to date" in update_result.stderr.lower():
            rprint("   [green]✓ yt-dlp is up to date[/green]")
        else:
            rprint(f"   [green]✓ yt-dlp updated[/green]")
            if update_result.stdout:
                for line in update_result.stdout.strip().split("\n"):
                    rprint(f"   [dim]{line}[/dim]")
    except FileNotFoundError:
        rprint("   [red]✗ yt-dlp not found. Install with: pip install -U yt-dlp[/red]")
    except Exception as e:
        rprint(f"   [yellow]⚠ Error checking yt-dlp: {e}[/yellow]")

    # Check Bun runtime (preferred for YouTube JS challenges)
    rprint("\n[bold]2. Checking Bun runtime...[/bold]")

    bun_path = shutil.which("bun")
    if not bun_path:
        bun_paths = ["/root/.bun/bin/bun", "/home/linuxbrew/.linuxbrew/bin/bun"]
        for path in bun_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                bun_path = path
                break

    if bun_path:
        try:
            result = subprocess.run([bun_path, "--version"], capture_output=True, text=True, timeout=10)
            rprint(f"   Bun path: [cyan]{bun_path}[/cyan]")
            rprint(f"   Version: [cyan]{result.stdout.strip()}[/cyan]")
            rprint("   [green]✓ Bun is installed[/green]")
        except Exception as e:
            rprint(f"   [yellow]⚠ Error checking Bun: {e}[/yellow]")
    else:
        rprint("   [yellow]⚠ Bun not found.[/yellow]")
        rprint("   [dim]   Install with: curl -fsSL https://bun.sh/install | bash[/dim]")

    # Check Deno runtime (fallback)
    rprint("\n[bold]3. Checking Deno runtime...[/bold]")

    deno_path = shutil.which("deno")
    if not deno_path:
        deno_paths = ["/root/.deno/bin/deno", "/home/linuxbrew/.linuxbrew/bin/deno"]
        for path in deno_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                deno_path = path
                break

    if deno_path:
        try:
            result = subprocess.run([deno_path, "--version"], capture_output=True, text=True, timeout=10)
            rprint(f"   Deno path: [cyan]{deno_path}[/cyan]")
            rprint(f"   Version: [cyan]{result.stdout.strip().split(chr(10))[0]}[/cyan]")
            rprint("   [green]✓ Deno is installed[/green]")
        except Exception as e:
            rprint(f"   [yellow]⚠ Error checking Deno: {e}[/yellow]")
    else:
        rprint("   [yellow]⚠ Deno not found.[/yellow]")
        rprint("   [dim]   Install with: curl -fsSL https://deno.land/install.sh | sh[/dim]")

    # Summary
    rprint("\n[bold]Summary[/bold]")
    rprint("   These dependencies are required for 2026 YouTube downloads.")
    rprint("   YouTube uses SABR and JS signature deciphering to block outdated tools.")
    rprint("   [bold]Bun[/bold] is the recommended JS runtime (with Deno as fallback).\n")


@utils_app.command("version")
def show_version():
    """Show version information."""
    rprint(f"\n[bold]{APP_NAME}[/bold] v[cyan]{APP_VERSION}[/cyan]\n")
