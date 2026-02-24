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
channel_app = typer.Typer(help="Channel tracking commands")
app.add_typer(channel_app, name="channel")
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


# Channel tracking commands


@channel_app.command("add")
def channel_add(
    handle: str = typer.Argument(..., help="Channel handle (e.g., @ChartChampions)"),
):
    """Add a YouTube channel to tracking."""
    from src.channel import resolve_channel_handle
    from src.database import get_db_manager
    from src.channel.schemas import ChannelDocument
    import asyncio

    try:
        rprint(f"\n[bold blue]Adding channel: {handle}[/bold blue]\n")

        # Resolve channel handle
        channel_id, channel_url = resolve_channel_handle(handle)

        # Save to database
        db = get_db_manager()
        channel_doc = ChannelDocument(
            channel_id=channel_id,
            channel_handle=handle.lstrip("@"),
            channel_title=handle,
            channel_url=channel_url,
        )

        async def _save():
            return await db.save_channel(channel_doc)

        doc_id = asyncio.run(_save())

        rprint(f"[green]✓ Channel added successfully![/green]")
        rprint(f"   Channel ID: {channel_id}")
        rprint(f"   Handle: @{channel_doc.channel_handle}")
        rprint(f"   URL: {channel_url}")
        rprint(f"   Database ID: {doc_id[:16]}...\n")

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


@channel_app.command("list")
def channel_list():
    """List all tracked channels."""
    from src.database import get_db_manager
    import asyncio

    try:
        db = get_db_manager()

        async def _fetch():
            return await db.list_channels()

        channels = asyncio.run(_fetch())

        if not channels:
            rprint("\n[yellow]No channels being tracked yet.[/yellow]\n")
            rprint(
                "Use [bold]uv run python -m src.cli channel add @Handle[/bold] to add a channel.\n"
            )
            return

        rprint("\n[bold blue]📺 Tracked Channels[/bold blue]\n")

        table = Table()
        table.add_column("Handle", style="cyan", width=20)
        table.add_column("Title", style="white", width=30)
        table.add_column("Videos", style="green", justify="right")
        table.add_column("Mode", style="yellow", width=10)
        table.add_column("Last Sync", style="dim", width=20)

        for ch in channels:
            last_synced = ch.get("last_synced", "Never")[:10] if ch.get("last_synced") else "Never"
            table.add_row(
                f"@{ch.get('channel_handle', 'N/A')}",
                ch.get("channel_title", "N/A")[:28] + "..."
                if len(ch.get("channel_title", "")) > 30
                else ch.get("channel_title", "N/A"),
                str(ch.get("total_videos_tracked", 0)),
                ch.get("sync_mode", "recent"),
                last_synced,
            )

        console.print(table)
        rprint(f"\n[green]Total: {len(channels)} channel(s)[/green]\n")

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


@channel_app.command("sync")
def channel_sync(
    handle: str = typer.Argument(..., help="Channel handle (e.g., @ChartChampions)"),
    all_videos: bool = typer.Option(
        False, "--all", help="Fetch ALL videos (yt-dlp, may take time)"
    ),
    max_videos: int | None = typer.Option(
        None, "--max-videos", help="Maximum videos to fetch (default: all)"
    ),
    incremental: bool = typer.Option(
        False, "--incremental", "-i", help="Only fetch metadata for NEW videos (smart sync)"
    ),
):
    """Sync videos from a channel."""
    from src.channel import sync_channel

    try:
        mode = "all" if all_videos else "recent"

        if incremental and not all_videos:
            rprint("[yellow]Note: --incremental requires --all, enabling it[/yellow]\n")
            mode = "all"

        rprint(f"\n[bold blue]Syncing channel: {handle} (mode: {mode})[/bold blue]\n")

        result = sync_channel(handle, mode=mode, max_videos=max_videos, incremental=incremental)

        rprint(f"\n[green]✓ Sync complete![/green]")
        rprint(f"   Channel: @{result.channel_handle}")
        rprint(f"   Videos fetched: {result.videos_fetched}")
        rprint(f"   New videos: {result.videos_new}")
        rprint(f"   Existing videos: {result.videos_existing}")
        rprint(f"   Mode: {result.sync_mode}\n")

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


@channel_app.command("videos")
def channel_videos(
    handle: str = typer.Argument(..., help="Channel handle (e.g., @ChartChampions)"),
    limit: int = typer.Option(20, "-l", "--limit", help="Maximum videos to show"),
    status: str | None = typer.Option(
        None, "-s", "--status", help="Filter by status (pending/completed/failed)"
    ),
):
    """List videos from a tracked channel."""
    from src.database import get_db_manager
    import asyncio

    try:
        # Get channel and videos in a single async context
        db = get_db_manager()

        async def _fetch_all():
            # Try to find by handle
            channel = await db.channels.find_one({"channel_handle": handle.lstrip("@")})
            if not channel:
                # Try to find by channel_id if handle is actually a channel ID
                channel = await db.channels.find_one({"channel_id": handle})

            if not channel:
                return None, []

            channel_id = channel["channel_id"]

            if status:
                # Filter by status
                query = {"channel_id": channel_id}
                if status != "all":
                    query["transcript_status"] = status
                cursor = db.video_metadata.find(query).sort("published_at", -1).limit(limit)
                results = []
                async for doc in cursor:
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])
                    results.append(doc)
                return channel, results
            else:
                videos = await db.list_videos_by_channel(channel_id, limit=limit)
                return channel, videos

        channel, videos = asyncio.run(_fetch_all())

        if not channel:
            rprint(f"[red]Channel not found: {handle}[/red]")
            rprint(
                "Use [bold]uv run python -m src.cli channel list[/bold] to see tracked channels.\n"
            )
            raise typer.Exit(1)

        if not videos:
            rprint(f"\n[yellow]No videos found for @{handle.lstrip('@')}[/yellow]\n")
            return

        rprint(f"\n[bold blue]📹 Videos from @{handle.lstrip('@')}[/bold blue]\n")

        table = Table()
        table.add_column("Status", style="cyan", width=10)
        table.add_column("Title", style="white", width=60)
        table.add_column("Published", style="dim", width=12)
        table.add_column("Duration", style="green", justify="right")

        for vid in videos:
            status_icon = {
                "pending": "[yellow]⏳[/yellow]",
                "completed": "[green]✓[/green]",
                "failed": "[red]✗[/red]",
            }.get(vid.get("transcript_status", "pending"), "⏳")

            title = vid.get("title", "Unknown")
            if len(title) > 58:
                title = title[:55] + "..."

            published = vid.get("published_at", "N/A")
            if published and published != "N/A":
                published = published[:10]

            duration = vid.get("duration_seconds")
            if duration:
                mins, secs = divmod(duration, 60)
                duration_str = f"{mins}:{secs:02d}"
            else:
                duration_str = "N/A"

            table.add_row(status_icon, title, published, duration_str)

        console.print(table)
        rprint(f"\n[green]Showing {len(videos)} video(s)[/green]\n")

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


@channel_app.command("transcribe-pending")
def channel_transcribe_pending(
    handle: str | None = typer.Argument(
        None, help="Channel handle (optional, transcribe all if not specified)"
    ),
    batch_size: int = typer.Option(5, "-b", "--batch-size", help="Number of videos to transcribe"),
):
    """Transcribe pending videos from channel."""
    from src.channel import resolve_channel_handle, get_pending_videos, mark_video_transcribed
    from src.pipeline import get_transcript
    import asyncio

    try:
        channel_id = None
        channel_handle = "all channels"

        if handle:
            channel_id, _ = resolve_channel_handle(handle)
            channel_handle = f"@{handle.lstrip('@')}"

        rprint(f"\n[bold blue]Transcribing pending videos from {channel_handle}[/bold blue]\n")

        # Get pending videos
        pending = get_pending_videos(channel_id)

        if not pending:
            rprint("[green]✓ No pending videos to transcribe![/green]\n")
            return

        rprint(
            f"Found {len(pending)} pending video(s), processing {min(batch_size, len(pending))}...\n"
        )

        successes = 0
        failures = 0

        for i, video in enumerate(pending[:batch_size], 1):
            rprint(f"[dim]{i}/{min(batch_size, len(pending))}[/dim] {video.title[:50]}...")

            try:
                # Transcribe video
                video_url = f"https://www.youtube.com/watch?v={video.video_id}"
                result = get_transcript(video_url, save_to_db=True)

                # Mark as completed
                from src.database import get_db_manager

                db = get_db_manager()

                async def _mark():
                    # Get transcript ID
                    transcript = await db.get_transcript(video.video_id)
                    if transcript:
                        await db.mark_transcript_completed(video.video_id, transcript["_id"])
                        return True
                    return False

                marked = asyncio.run(_mark())

                if marked:
                    rprint(f"  [green]✓ Transcribed and marked complete[/green]")
                    successes += 1
                else:
                    rprint(f"  [yellow]⚠ Transcribed but failed to mark complete[/yellow]")
                    successes += 1

            except Exception as e:
                rprint(f"  [red]✗ Error: {escape(str(e)[:50])}[/red]")
                failures += 1

                # Mark as failed
                from src.database import get_db_manager

                db = get_db_manager()

                async def _mark_failed():
                    await db.mark_transcript_failed(video.video_id, str(e))

                asyncio.run(_mark_failed())

        rprint(f"\n[bold]Transcription Complete[/bold]")
        rprint(f"  [green]Successes: {successes}[/green]")
        rprint(f"  [red]Failures: {failures}[/red]\n")

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


@channel_app.command("remove")
def channel_remove(
    handle: str = typer.Argument(..., help="Channel handle to remove"),
    force: bool = typer.Option(False, "-f", "--force", help="Force removal without confirmation"),
):
    """Remove a channel from tracking."""
    from src.channel import resolve_channel_handle
    from src.database import get_db_manager
    import asyncio

    try:
        # Resolve channel handle
        channel_id, _ = resolve_channel_handle(handle)

        if not force:
            # Confirm removal
            confirm = typer.confirm(f"Remove channel @{handle.lstrip('@')} from tracking?")
            if not confirm:
                rprint("[yellow]Cancelled[/yellow]")
                return

        db = get_db_manager()

        async def _delete():
            return await db.delete_channel(channel_id)

        deleted = asyncio.run(_delete())

        if deleted:
            rprint(f"[green]✓ Channel @{handle.lstrip('@')} removed successfully[/green]\n")
        else:
            rprint(f"[yellow]Channel not found[/yellow]\n")

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
