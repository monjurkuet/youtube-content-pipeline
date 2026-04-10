"""Transcription commands for CLI."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import typer
from rich import print as rprint
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from src.core.schemas import ProcessingResult
from src.pipeline import get_transcript

transcription_app = typer.Typer(help="Transcription commands")
console = Console()


@transcription_app.command("run")
def transcribe(
    source: str = typer.Argument(
        ..., help="YouTube video ID, URL, local file path, or remote URL"
    ),
    language: str | None = typer.Option(None, "-l", "--lang", help="Preferred language code"),
    output: Path | None = typer.Option(None, help="Output JSON file path (optional)"),
    no_db: bool = typer.Option(False, help="Skip saving to database"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Show detailed output"),
):
    """Transcribe a video and save transcript to database."""
    rprint(f"\n[bold blue]Processing: {source}...[/bold blue]\n")

    try:
        result = get_transcript(
            source=source,
            language=language,
            save_to_db=not no_db,
            verbose=verbose,
        )

        _display_summary(result)

        if verbose:
            _display_details(result)

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result.model_dump(), indent=2))
            rprint(f"\n[dim]Full result saved to {output}[/dim]\n")

        if result.success:
            rprint(f"[green]✓ Transcription completed successfully![/green]\n")
        else:
            rprint(f"[red]✗ Transcription failed: {result.error}[/red]\n")

    except Exception as e:
        rprint(f"[red]✗ Error: {e}[/red]\n")


def _display_summary(result: ProcessingResult):
    """Display transcription summary."""
    status_color = "green" if result.success else "red"
    summary_table = Table(title="Transcription Summary")
    summary_table.add_column("Property", style="cyan")
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Status", f"[{status_color}]{'Success' if result.success else 'Failed'}[/{status_color}]")
    summary_table.add_row("Source Type", result.source_type)
    summary_table.add_row("Video ID", result.video_id or "N/A")
    summary_table.add_row("Language", result.language or "Unknown")
    summary_table.add_row("Source", result.transcript_source or "None")
    summary_table.add_row("Text Length", f"{result.total_text_length} chars")

    rprint(summary_table)


def _display_details(result: ProcessingResult):
    """Display detailed transcription info."""
    details_table = Table(title="Processing Details", box=None)
    details_table.add_column("Metric", style="dim")
    details_table.add_column("Value", style="dim")

    if result.error:
        details_table.add_row("Error", f"[red]{result.error}[/red]")

    if details_table.row_count:
        rprint(details_table)


@transcription_app.command("batch")
def batch(
    sources_file: Path = typer.Argument(..., help="File containing video sources (one per line)"),
    work_dir: Path | None = typer.Option(None, help="Working directory for temporary files"),
    no_db: bool = typer.Option(False, help="Skip saving to database"),
):
    """Batch transcribe multiple videos from a file."""
    if not sources_file.exists():
        rprint(f"[red]Error: {sources_file} not found[/red]")
        return

    sources = [line.strip() for line in sources_file.read_text().splitlines() if line.strip()]

    rprint(f"\n[bold blue]Batch processing {len(sources)} videos...[/bold blue]\n")

    results = []
    for i, source in enumerate(sources):
        rprint(f"[{i+1}/{len(sources)}] Processing: {source}")
        try:
            result = get_transcript(source=source, save_to_db=not no_db)
            results.append(result)
            if result.success:
                rprint(f"  [green]✓ Success ({result.transcript_source})[/green]")
            else:
                rprint(f"  [red]✗ Failed: {result.error}[/red]")
        except Exception as e:
            rprint(f"  [red]✗ Error: {e}[/red]")

    # Show final stats
    success_count = sum(1 for r in results if r.success)
    rprint(f"\n[bold green]✓ Batch completed: {success_count}/{len(sources)} successful[/bold green]\n")
