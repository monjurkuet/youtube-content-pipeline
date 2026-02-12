"""CLI for LLM-driven video analysis pipeline."""

import json
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from src.core.schemas import VideoAnalysisResult
from src.pipeline import analyze_video

app = typer.Typer(help="LLM-Driven Video Analysis Pipeline")
console = Console()


@app.command()
def analyze(
    source: str = typer.Argument(
        ..., help="Video source: YouTube URL/ID, local path, or remote URL"
    ),
    work_dir: Path | None = typer.Option(None, help="Working directory for temporary files"),
    output: Path | None = typer.Option(None, help="Output JSON file path (optional)"),
    no_db: bool = typer.Option(False, help="Skip saving to database"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Show detailed output"),
):
    """
    Analyze a video using LLM-driven pipeline.

    Makes exactly 3 LLM calls:
    1. Gemini 2.5 Flash - Analyzes transcript
    2. qwen3-vl-plus - Analyzes video frames
    3. Gemini 2.5 Flash - Synthesizes final analysis
    """
    try:
        # Run analysis
        result = analyze_video(source, work_dir)

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


def _display_summary(result: VideoAnalysisResult):
    """Display analysis summary."""
    rprint("\n[bold blue]📊 Analysis Summary[/bold blue]\n")

    summary_table = Table(show_header=False, box=None)
    summary_table.add_column("Field", style="cyan", width=20)
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Video ID", result.video_id)
    summary_table.add_row("Source Type", result.source_type)
    summary_table.add_row("Content Type", result.content_type.replace("_", " ").title())
    summary_table.add_row("Primary Asset", result.primary_asset or "N/A")
    summary_table.add_row("Market Context", result.transcript_intelligence.market_context.upper())
    summary_table.add_row("Duration", f"{result.duration_seconds:.1f}s")
    summary_table.add_row("Processing Time", f"{result.processing.duration_seconds:.1f}s")
    summary_table.add_row("LLM Calls", str(result.processing.llm_calls_made))

    console.print(summary_table)

    # Executive Summary
    rprint("\n[bold]Executive Summary:[/bold]")
    rprint(Panel(result.synthesis.executive_summary, expand=False))


def _display_details(result: VideoAnalysisResult):
    """Display detailed analysis."""
    intel = result.transcript_intelligence

    # Trading Signals
    if intel.signals:
        rprint("\n[bold yellow]📈 Trading Signals[/bold yellow]")
        for signal in intel.signals:
            direction_color = (
                "green"
                if signal.direction == "long"
                else "red"
                if signal.direction == "short"
                else "yellow"
            )
            rprint(
                f"\n[{direction_color}]• {signal.asset} "
                f"{signal.direction.upper()}[/{direction_color}]"
            )
            if signal.entry_price:
                rprint(f"  Entry: {signal.entry_price}")
            if signal.target_price:
                rprint(f"  Target: {signal.target_price}")
            if signal.stop_loss:
                rprint(f"  Stop Loss: {signal.stop_loss}")
            if signal.rationale:
                rprint(f"  [dim]{signal.rationale}[/dim]")

    # Price Levels
    if intel.price_levels:
        rprint("\n[bold cyan]🎯 Price Levels[/bold cyan]")
        for level in intel.price_levels:
            type_color = {
                "support": "green",
                "resistance": "red",
                "entry": "blue",
                "target": "yellow",
            }.get(level.type, "white")
            rprint(f"  [{type_color}]{level.type.upper()}[/{type_color}]: {level.label}")

    # Key Takeaways
    if result.synthesis.key_takeaways:
        rprint("\n[bold green]💡 Key Takeaways[/bold green]")
        for i, takeaway in enumerate(result.synthesis.key_takeaways, 1):
            rprint(f"  {i}. {takeaway}")

    # Consistency Notes
    if result.synthesis.consistency_notes:
        rprint("\n[bold dim]📝 Consistency Notes[/bold dim]")
        rprint(f"[dim]{result.synthesis.consistency_notes}[/dim]")

    # Visual Summary
    if result.frame_intelligence.summary.frames_selected > 0:
        rprint("\n[bold magenta]🖼️  Visual Analysis[/bold magenta]")
        rprint(f"  Frames Analyzed: {result.frame_intelligence.summary.total_frames_analyzed}")
        rprint(f"  Frames Selected: {result.frame_intelligence.summary.frames_selected}")
        if result.frame_intelligence.summary.primary_assets_visualized:
            assets = result.frame_intelligence.summary.primary_assets_visualized
            rprint(f"  Assets Visualized: {', '.join(assets)}")


@app.command()
def quick(
    source: str = typer.Argument(..., help="YouTube URL/ID to analyze"),
):
    """Quick analysis - minimal output, just key points."""
    try:
        result = analyze_video(source)

        rprint(
            f"\n[bold]{result.video_id}[/bold] - {result.content_type.replace('_', ' ').title()}"
        )
        rprint(f"[dim]{result.synthesis.executive_summary}[/dim]\n")

        if result.transcript_intelligence.signals:
            rprint("[bold]Signals:[/bold]")
            for signal in result.transcript_intelligence.signals:
                rprint(
                    f"  • {signal.asset} {signal.direction.upper()} @ {signal.entry_price or 'N/A'}"
                )

        if result.transcript_intelligence.price_levels:
            rprint("\n[bold]Key Levels:[/bold]")
            for level in result.transcript_intelligence.price_levels[:3]:
                rprint(f"  • {level.label} ({level.type})")

        rprint()

    except Exception as e:
        rprint(f"[red]Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def review_normalizations(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries to review"),
    min_confidence: float = typer.Option(
        0.0, "--min-confidence", help="Minimum confidence threshold"
    ),
    max_confidence: float = typer.Option(
        1.0, "--max-confidence", help="Maximum confidence threshold"
    ),
    show_stats: bool = typer.Option(False, "--stats", help="Show statistics only"),
):
    """Review and manage price level normalization history."""
    try:
        from src.core.normalizer import get_normalizer

        normalizer = get_normalizer()

        if show_stats:
            stats = normalizer.get_statistics()
            rprint("\n[bold blue]📊 Normalization Statistics[/bold blue]\n")

            stats_table = Table(show_header=False, box=None)
            stats_table.add_column("Metric", style="cyan", width=30)
            stats_table.add_column("Value", style="white")

            stats_table.add_row("Total Normalizations", str(stats["total_normalizations"]))
            stats_table.add_row("Learned Patterns", str(stats["learned_patterns"]))
            stats_table.add_row("Low Confidence Count", str(stats["low_confidence_count"]))

            console.print(stats_table)

            rprint("\n[bold]By Method:[/bold]")
            for method, count in stats["by_method"].items():
                rprint(f"  • {method}: {count}")

            rprint("\n[bold]Average Confidence by Method:[/bold]")
            for method, avg_conf in stats["avg_confidence_by_method"].items():
                rprint(f"  • {method}: {avg_conf:.2f}")

            return

        # Get recent normalizations
        normalizations = normalizer.review_recent_normalizations(
            limit=limit, min_confidence=min_confidence, max_confidence=max_confidence
        )

        if not normalizations:
            rprint("\n[yellow]No normalizations found matching criteria.[/yellow]")
            return

        rprint(
            f"\n[bold blue]📝 Recent Normalizations (showing {len(normalizations)})[/bold blue]\n"
        )

        norm_table = Table(show_header=True)
        norm_table.add_column("ID", style="dim", width=6)
        norm_table.add_column("Original", style="yellow", width=20)
        norm_table.add_column("Normalized", style="green", width=15)
        norm_table.add_column("Confidence", width=10)
        norm_table.add_column("Method", width=15)
        norm_table.add_column("Context", style="dim", max_width=40)

        for norm in normalizations:
            confidence_color = (
                "green"
                if norm["confidence"] >= 0.8
                else "yellow"
                if norm["confidence"] >= 0.5
                else "red"
            )
            context_preview = (
                (norm.get("context", "") or "")[:40] + "..."
                if len(norm.get("context", "") or "") > 40
                else (norm.get("context", "") or "")
            )

            norm_table.add_row(
                str(norm["id"]),
                norm["original_type"],
                norm["normalized_type"],
                f"[{confidence_color}]{norm['confidence']:.2f}[/{confidence_color}]",
                norm["method"],
                context_preview,
            )

        console.print(norm_table)

        rprint("\n[dim]Use --stats to see overall statistics[/dim]")
        rprint("[dim]To correct a normalization, use the correct command with the ID[/dim]")

    except Exception as e:
        rprint(f"[red]Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def correct_normalization(
    history_id: int = typer.Argument(..., help="ID of the normalization to correct"),
    correct_type: str = typer.Argument(..., help="The correct price level type"),
):
    """Correct a previous normalization to improve learning."""
    try:
        from src.core.normalizer import get_normalizer

        valid_types = ["support", "resistance", "entry", "target", "stop_loss", "other"]
        if correct_type not in valid_types:
            rprint(f"[red]Invalid type. Must be one of: {', '.join(valid_types)}[/red]")
            raise typer.Exit(1)

        normalizer = get_normalizer()
        success = normalizer.correct_normalization(history_id, correct_type)

        if success:
            rprint(f"[green]✓ Normalization {history_id} corrected to '{correct_type}'[/green]")
            rprint("[dim]Learning pattern updated with high confidence.[/dim]")
        else:
            rprint(f"[red]✗ Could not find normalization with ID {history_id}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        rprint(f"[red]Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)


@app.command()
def reset_normalizer(
    confirm: bool = typer.Option(
        False, "--confirm", help="Confirm deletion of all learned patterns"
    ),
):
    """Reset the normalizer learning database (use with caution)."""
    if not confirm:
        rprint(
            "[yellow]⚠️  This will delete all learned patterns and normalization history.[/yellow]"
        )
        rprint("[yellow]   Use --confirm flag to proceed.[/yellow]")
        raise typer.Exit(1)

    try:
        from src.core.normalizer import get_normalizer

        normalizer = get_normalizer()

        import sqlite3

        with sqlite3.connect(normalizer.db_path) as conn:
            conn.execute("DELETE FROM price_level_patterns")
            conn.execute("DELETE FROM normalization_history")
            conn.execute("DELETE FROM context_rules")
            conn.commit()

        rprint("[green]✓ Normalizer database reset successfully[/green]")

    except Exception as e:
        rprint(f"[red]Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
