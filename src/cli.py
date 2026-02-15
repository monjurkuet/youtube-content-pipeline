"""CLI for Transcription Pipeline."""

import json
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from src.core.schemas import ProcessingResult
from src.pipeline import get_transcript

app = typer.Typer(help="Transcription Pipeline - Get transcripts and save to DB")
console = Console()


@app.command()
def transcribe(
    source: str = typer.Argument(
        ..., help="Video source: YouTube URL/ID, local path, or remote URL"
    ),
    work_dir: Path | None = typer.Option(None, help="Working directory for temporary files"),
    output: Path | None = typer.Option(None, help="Output JSON file path (optional)"),
    no_db: bool = typer.Option(False, help="Skip saving to database"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Show detailed output"),
):
    """
    Transcribe a video and save transcript to database.

    Simple 2-step process:
    1. Get transcript (via YouTube API or Whisper fallback)
    2. Save to MongoDB
    """
    try:
        # Run transcription
        result = get_transcript(source, work_dir, save_to_db=not no_db)

        # Display results
        _display_summary(result)

        if verbose:
            _display_details(result)

        # Save to file if requested
        if output:
            output_path = Path(output)
            with open(output_path, "w") as f:
                json.dump(result.model_dump_for_mongo(), f, indent=2, default=str)
            rprint(f"\n[green]✓ Results saved to: {output_path}[/green]")

        # Print JSON to stdout
        if not verbose:
            rprint("\n[dim]--- JSON Output ---[/dim]")
            console.print_json(json.dumps(result.model_dump_for_mongo(), default=str))

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


def _display_summary(result: ProcessingResult):
    """Display transcription summary."""
    rprint("\n[bold blue]📄 Transcription Summary[/bold blue]\n")

    summary_table = Table(show_header=False, box=None)
    summary_table.add_column("Field", style="cyan", width=20)
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Video ID", result.video_id)
    summary_table.add_row("Source Type", result.source_type)
    summary_table.add_row("Transcript Source", result.transcript_source)
    summary_table.add_row("Language", result.language)
    summary_table.add_row("Duration", f"{result.duration_seconds:.1f}s")
    summary_table.add_row("Segments", str(result.segment_count))
    summary_table.add_row("Text Length", f"{result.total_text_length:,} chars")
    summary_table.add_row("Processing Time", f"{result.duration_seconds_total:.1f}s")
    summary_table.add_row("Saved to DB", "✓" if result.saved_to_db else "✗")

    console.print(summary_table)


def _display_details(result: ProcessingResult):
    """Display detailed transcription info."""
    rprint("\n[bold]Transcript Details:[/bold]")
    rprint(
        Panel(
            f"Video ID: {result.video_id}\n"
            f"Source: {result.source_type}\n"
            f"URL: {result.source_url or 'N/A'}\n"
            f"Segments: {result.segment_count}\n"
            f"Duration: {result.duration_seconds:.1f}s",
            expand=False,
        )
    )


@app.command()
def batch(
    sources_file: Path = typer.Argument(..., help="File containing video sources (one per line)"),
    work_dir: Path | None = typer.Option(None, help="Working directory for temporary files"),
    no_db: bool = typer.Option(False, help="Skip saving to database"),
):
    """Batch transcribe multiple videos from a file.

    Each line in the file should be a YouTube URL/ID, local path, or remote URL.
    """
    try:
        if not sources_file.exists():
            rprint(f"[red]Error: File not found: {sources_file}[/red]")
            raise typer.Exit(1)

        sources = [line.strip() for line in sources_file.read_text().splitlines() if line.strip()]

        if not sources:
            rprint("[red]Error: No sources found in file[/red]")
            raise typer.Exit(1)

        rprint("\n[bold blue]📄 Batch Transcription[/bold blue]")
        rprint(f"Processing {len(sources)} sources...\n")

        results: list[dict] = []
        successes = 0
        failures = 0

        for i, source in enumerate(sources, 1):
            rprint(f"[dim]{i}/{len(sources)}[/dim] Processing: {source[:50]}...")

            try:
                result = get_transcript(source, work_dir, save_to_db=not no_db)
                results.append(
                    {
                        "source": source,
                        "video_id": result.video_id,
                        "status": "success",
                        "segments": result.segment_count,
                        "duration": result.duration_seconds,
                    }
                )
                successes += 1
                rprint(f"  [green]✓[/green] {result.video_id} ({result.segment_count} segments)")
            except Exception as e:
                results.append(
                    {
                        "source": source,
                        "status": "failed",
                        "error": str(e),
                    }
                )
                failures += 1
                rprint(f"  [red]✗[/red] Error: {escape(str(e)[:50])}")

        # Summary
        rprint("\n[bold]Batch Complete[/bold]")
        rprint(f"  [green]Successes: {successes}[/green]")
        rprint(f"  [red]Failures: {failures}[/red]")

    except Exception as e:
        rprint(f"[red]Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
