"""CLI for Transcription Pipeline."""

import json
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from src.core.logging_config import get_logger, setup_logging
from src.core.schemas import ProcessingResult
from src.pipeline import get_transcript

app = typer.Typer(help="Transcription Pipeline - Get transcripts and save to DB")
channel_app = typer.Typer(help="Channel tracking commands")
cookie_app = typer.Typer(help="Cookie management commands")
app.add_typer(channel_app, name="channel")
app.add_typer(cookie_app, name="cookie")
console = Console()
log = get_logger("cli")


# Cookie management commands
@cookie_app.command("extract")
def cookie_extract():
    """Extract cookies from Chrome browser for YouTube.

    This command extracts authentication cookies from Chrome browser
    which are required for accessing age-restricted content.
    """
    from src.video.cookie_manager import get_cookie_manager

    try:
        rprint("\n[bold blue]Extracting YouTube cookies from Chrome...[/bold blue]\n")

        manager = get_cookie_manager()
        success = manager.ensure_cookies()

        if success:
            status = manager.get_status()
            rprint("\n[green]✓ Cookies extracted successfully![/green]")
            rprint(f"   YouTube cookies: {status.get('youtube_cookies', 'N/A')}")
            rprint(f"   Google cookies: {status.get('google_cookies', 'N/A')}")
            rprint(f"   Has auth: {'✓ Yes' if status.get('has_auth') else '✗ No'}")
            rprint(f"   Cookie age: {status.get('cookie_age_hours', 'N/A'):.1f} hours\n")
        else:
            rprint("\n[red]✗ Failed to extract cookies[/red]")
            rprint("[dim]   Make sure Chrome is installed and you're logged into YouTube[/dim]\n")
            raise typer.Exit(1)

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


@cookie_app.command("status")
def cookie_status():
    """Show current cookie status and metadata."""
    from src.video.cookie_manager import get_cookie_manager

    try:
        rprint("\n[bold]Cookie Status[/bold]\n")

        manager = get_cookie_manager()
        status = manager.get_status()

        table = Table(show_header=False, box=None)
        table.add_column("Field", style="cyan", width=30)
        table.add_column("Value", style="white")

        table.add_row("Cookie file exists", "✓ Yes" if status.get("cookie_file_exists") else "✗ No")
        table.add_row(
            "Auto-extract enabled", "✓ Yes" if status.get("auto_extract_enabled") else "✗ No"
        )

        if status.get("cookie_file_exists"):
            table.add_row("Cookie age", f"{status.get('cookie_age_hours', 0):.1f} hours")
            table.add_row("Is fresh (not expired)", "✓ Yes" if status.get("is_fresh") else "✗ No")

        if status.get("youtube_cookies"):
            table.add_row("YouTube cookies", str(status.get("youtube_cookies")))
        if status.get("google_cookies"):
            table.add_row("Google cookies", str(status.get("google_cookies")))
        table.add_row("Has authentication", "✓ Yes" if status.get("has_auth") else "✗ No")

        if status.get("last_extracted"):
            table.add_row("Last extracted", status.get("last_extracted"))

        console.print(table)
        rprint()

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


@cookie_app.command("invalidate")
def cookie_invalidate():
    """Invalidate cookie cache to force re-extraction on next use."""
    from src.video.cookie_manager import get_cookie_manager

    try:
        rprint("\n[bold yellow]Invalidating cookie cache...[/bold yellow]\n")

        manager = get_cookie_manager()
        manager.invalidate_cache()

        rprint("[green]✓ Cookie cache invalidated[/green]")
        rprint("[dim]   Cookies will be re-extracted on next use\n")

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Enable verbose logging"),
    log_file: Path | None = typer.Option(None, help="Log file path"),
):
    """
    Transcription Pipeline - Get transcripts and save to DB.

    Set up logging configuration before running commands.
    """
    level = "DEBUG" if verbose else "INFO"
    setup_logging(level=level, log_file=log_file)


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
        log.info(f"📝 Starting transcription: {source[:50]}...")

        # Run transcription
        result = get_transcript(source, work_dir, save_to_db=not no_db)

        # Log result
        log.info(
            f"✅ Transcription complete: {result.video_id} "
            f"(source={result.transcript_source}, segments={result.segment_count})"
        )

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
            log.info(f"💾 Results saved to file: {output_path}")

        # Print JSON to stdout
        if not verbose:
            rprint("\n[dim]--- JSON Output ---[/dim]")
            console.print_json(json.dumps(result.model_dump_for_mongo(), default=str))

    except Exception as e:
        log.error(f"❌ Transcription failed: {source[:50]}... - {str(e)[:100]}")
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
    import asyncio

    from src.channel import resolve_channel_handle
    from src.channel.schemas import ChannelDocument
    from src.database import get_db_manager

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

        rprint("[green]✓ Channel added successfully![/green]")
        rprint(f"   Channel ID: {channel_id}")
        rprint(f"   Handle: @{channel_doc.channel_handle}")
        rprint(f"   URL: {channel_url}")
        rprint(f"   Database ID: {doc_id[:16]}...\n")

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


@channel_app.command("add-from-videos")
def channel_add_from_videos(
    video_urls: list[str] = typer.Argument(..., help="YouTube video URLs"),
    auto_sync: bool = typer.Option(
        True, "--sync/--no-sync", help="Auto-sync channel videos after adding"
    ),
    sync_mode: str = typer.Option(
        "recent",
        "--sync-mode",
        help="Sync mode: 'recent' (~15 videos) or 'all' (all videos)",
    ),
):
    """Add channels from YouTube video URLs.

    Extracts channel information from video URLs and adds channels to tracking.
    Optionally syncs videos from each channel.
    """
    import asyncio
    import json
    import subprocess
    from typing import Any

    from src.channel import resolve_channel_handle
    from src.channel.schemas import ChannelDocument
    from src.channel.sync import sync_channel
    from src.database.manager import MongoDBManager

    def extract_video_id(url: str) -> str | None:
        """Extract video ID from YouTube URL."""
        import re

        match = re.search(r"(?:v=|\.be/)([a-zA-Z0-9_-]{11})", url)
        return match.group(1) if match else None

    def get_channel_from_video(video_id: str) -> dict[str, str] | None:
        """Get channel info from video ID using yt-dlp."""
        from src.video.cookie_manager import YouTubeCookieManager

        try:
            # Ensure cookies are available
            cookie_manager = YouTubeCookieManager(auto_extract=True)
            cookie_manager.ensure_cookies()
            cookie_args = cookie_manager.get_cookie_args()

            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--quiet",
            ]
            cmd.extend(cookie_args)  # Add cookies if available
            cmd.append(f"https://www.youtube.com/watch?v={video_id}")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout.strip())
                channel_id = data.get("channel_id")
                channel_handle = data.get("channel", "") or data.get("uploader", "")

                if channel_id:
                    return {
                        "channel_id": channel_id,
                        "channel_handle": channel_handle,
                    }

            return None
        except Exception as e:
            console.print(f"[dim]   Error fetching video {video_id}: {e}[/dim]")
            return None

    async def _process_all():
        """Process all video URLs and return channels to sync."""
        async with MongoDBManager() as db:
            processed_channels: set[str] = set()
            results = {
                "added": [],
                "skipped_duplicate": [],
                "skipped_existing": [],
                "failed": [],
            }
            channels_to_sync: list[dict[str, Any]] = []

            for url in video_urls:
                video_id = extract_video_id(url)
                if not video_id:
                    rprint(f"[yellow]⚠ Invalid URL: {url}[/yellow]")
                    results["failed"].append({"url": url, "error": "Invalid URL format"})
                    continue

                console.print(f"[dim]Processing: {video_id}[/dim]")

                channel_info = get_channel_from_video(video_id)
                if not channel_info:
                    rprint(f"[yellow]⚠ Could not get channel info for {video_id}[/yellow]")
                    results["failed"].append(
                        {"url": url, "video_id": video_id, "error": "Could not fetch channel info"}
                    )
                    continue

                channel_id = channel_info["channel_id"]
                channel_handle = channel_info["channel_handle"]

                # Check if already processed in this batch
                if channel_id in processed_channels:
                    rprint(
                        f"[green]✓ Channel already processed in this batch: {channel_handle}[/green]"
                    )
                    results["skipped_duplicate"].append(
                        {"url": url, "channel_id": channel_id, "channel_handle": channel_handle}
                    )
                    continue

                # Check if channel already exists in database
                existing_channel = await db.channels.find_one({"channel_id": channel_id})
                if existing_channel:
                    rprint(
                        f"[yellow]⚠ Channel already tracked: @{existing_channel.get('channel_handle')}[/yellow]"
                    )
                    results["skipped_existing"].append(
                        {
                            "url": url,
                            "channel_id": channel_id,
                            "channel_handle": existing_channel.get("channel_handle"),
                        }
                    )
                    processed_channels.add(channel_id)
                    continue

                try:
                    # Use channel_id directly from yt-dlp (more reliable)
                    channel_url = f"https://www.youtube.com/channel/{channel_id}"

                    # Create a normalized handle from the channel name
                    # Remove spaces, special chars, and lowercase for consistency
                    normalized_handle = "".join(c for c in channel_handle if c.isalnum())[
                        :30
                    ]  # Max 30 chars

                    # Check if channel already exists with this ID
                    existing_channel = await db.channels.find_one({"channel_id": channel_id})
                    if existing_channel:
                        rprint(
                            f"[yellow]⚠ Channel already tracked: @{existing_channel.get('channel_handle')}[/yellow]"
                        )
                        results["skipped_existing"].append(
                            {
                                "url": url,
                                "channel_id": channel_id,
                                "channel_handle": existing_channel.get("channel_handle"),
                            }
                        )
                        processed_channels.add(channel_id)
                        continue

                    # Save channel to database
                    channel_doc = ChannelDocument(
                        channel_id=channel_id,
                        channel_handle=normalized_handle,
                        channel_title=channel_handle,
                        channel_url=channel_url,
                    )

                    doc_id = await db.save_channel(channel_doc)

                    result_entry: dict[str, Any] = {
                        "url": url,
                        "channel_id": channel_id,
                        "channel_handle": channel_doc.channel_handle,
                        "channel_title": channel_doc.channel_title,
                        "database_id": doc_id,
                    }

                    # Auto-sync if requested
                    # Note: sync_channel must be called outside async context
                    # Store channel info for syncing after async block
                    channels_to_sync.append(
                        {
                            "channel_id": channel_id,
                            "channel_url": channel_url,
                            "channel_title": channel_doc.channel_title,
                            "result_entry": result_entry,
                        }
                    )

                    results["added"].append(result_entry)
                    processed_channels.add(channel_id)
                    rprint(f"[green]✓ Added: {channel_doc.channel_title}[/green]\n")

                except Exception as e:
                    rprint(f"[red]✗ Failed to add channel: {e}[/red]")
                    results["failed"].append({"url": url, "video_id": video_id, "error": str(e)})

        # Summary
        rprint("\n" + "=" * 60)
        rprint("[bold]Summary[/bold]")
        rprint("=" * 60)
        rprint(f"  [green]Channels added: {len(results['added'])}[/green]")
        if results["added"]:
            for entry in results["added"]:
                sync_info = ""
                if "sync_videos_fetched" in entry:
                    sync_info = f" ({entry['sync_videos_fetched']} videos)"
                rprint(f"    • {entry['channel_title']}{sync_info}")

        if results["skipped_duplicate"]:
            rprint(
                f"  [yellow]Skipped (duplicate in batch): {len(results['skipped_duplicate'])}[/yellow]"
            )

        if results["skipped_existing"]:
            rprint(f"  [dim]Skipped (already tracked): {len(results['skipped_existing'])}[/dim]")
            for entry in results["skipped_existing"]:
                rprint(f"    • {entry['channel_handle']}")

        if results["failed"]:
            rprint(f"  [red]Failed: {len(results['failed'])}[/red]")
            for entry in results["failed"]:
                error_msg = entry.get("error", "Unknown error")[:50]
                rprint(f"    • {entry.get('url', 'Unknown')}: {error_msg}")

        rprint("=" * 60 + "\n")
        return results, channels_to_sync

    # Run the async processing
    try:
        results, channels_to_sync = asyncio.run(_process_all())
    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e

    # Sync channels outside async context (sync_channel uses asyncio.run internally)
    if auto_sync and channels_to_sync:
        rprint("\n[bold blue]Syncing channels...[/bold blue]\n")
        for ch_info in channels_to_sync:
            try:
                sync_result = sync_channel(
                    channel_id=ch_info["channel_id"],
                    channel_url=ch_info["channel_url"],
                    mode=sync_mode,
                    db_manager=None,  # sync_channel will create its own DB connection
                )
                ch_info["result_entry"]["sync_videos_fetched"] = str(sync_result.videos_fetched)
                ch_info["result_entry"]["sync_videos_new"] = str(sync_result.videos_new)
                rprint(
                    f"[green]✓ {ch_info['channel_title']}: {sync_result.videos_fetched} videos "
                    f"({sync_result.videos_new} new)[/green]"
                )
            except Exception as sync_error:
                rprint(f"[yellow]⚠ {ch_info['channel_title']}: Sync failed - {sync_error}[/yellow]")
                ch_info["result_entry"]["sync_error"] = str(sync_error)
        rprint()


@channel_app.command("list")
def channel_list():
    """List all tracked channels."""
    import asyncio

    from src.database import get_db_manager

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

        log.info(f"🔄 Starting channel sync: {handle} (mode={mode})")
        rprint(f"\n[bold blue]Syncing channel: {handle} (mode: {mode})[/bold blue]\n")

        result = sync_channel(handle, mode=mode, max_videos=max_videos, incremental=incremental)

        log.info(
            f"✅ Channel sync complete: @{result.channel_handle} "
            f"({result.videos_fetched} videos, {result.videos_new} new)"
        )

        rprint("\n[green]✓ Sync complete![/green]")
        rprint(f"   Channel: @{result.channel_handle}")
        rprint(f"   Videos fetched: {result.videos_fetched}")
        rprint(f"   New videos: {result.videos_new}")
        rprint(f"   Existing videos: {result.videos_existing}")
        rprint(f"   Mode: {result.sync_mode}\n")

    except Exception as e:
        log.error(f"❌ Channel sync failed: {handle} - {str(e)[:100]}")
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
    import asyncio

    from src.database import get_db_manager

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
    batch_size: int | None = typer.Option(
        None,
        "-b",
        "--batch-size",
        help="Number of videos to transcribe per batch (default: from config.yaml)",
    ),
    all_videos: bool = typer.Option(
        False, "--all", "-a", help="Transcribe ALL pending videos (no limit)"
    ),
):
    """Transcribe pending videos from channel.

    Batch size defaults to config.yaml setting (default: 5).
    Videos are processed sequentially with rate limiting delays.
    Use --all to transcribe all pending videos.
    """
    import asyncio
    import json
    import subprocess

    from src.channel import get_pending_videos, resolve_channel_handle
    from src.core.config import get_settings_with_yaml
    from src.pipeline import get_transcript

    # Load settings from config.yaml
    settings = get_settings_with_yaml()

    # Use CLI batch_size if provided, otherwise use config
    if batch_size is None:
        batch_size = settings.batch_default_size

    def check_video_availability(video_id: str) -> tuple[bool, str]:
        """
        Check if video is available for transcription using yt-dlp.

        Note: In --simulate mode, 'url' field is None even for playable videos.
        We check for errors and basic metadata instead.

        Returns:
            Tuple of (is_available, reason)
        """
        try:
            # Use --flat-playlist for faster metadata-only check
            cmd = [
                "yt-dlp",
                "--flat-playlist",
                "--dump-json",
                "--no-warnings",
                "--quiet",
                f"https://www.youtube.com/watch?v={video_id}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            # Check stderr for errors (yt-dlp reports errors there)
            if result.returncode != 0:
                error_msg = result.stderr.strip().lower()
                if "live event" in error_msg or "upcoming" in error_msg:
                    return False, "Live stream (upcoming)"
                elif "private" in error_msg:
                    return False, "Video is private"
                elif "unavailable" in error_msg or "not available" in error_msg:
                    return False, "Video unavailable"
                elif "members-only" in error_msg or "join" in error_msg:
                    return False, "Members-only video"
                elif "age" in error_msg and "restricted" in error_msg:
                    return False, "Age-restricted"
                else:
                    return False, f"Video error: {result.stderr.strip()[:50]}"

            if not result.stdout.strip():
                return False, "No video metadata"

            data = json.loads(result.stdout.strip())

            # Check for live stream indicators
            live_status = data.get("live_status")
            if live_status in ["is_live", "is_upcoming", "post_live"]:
                return False, f"Live stream ({live_status})"

            # Check availability field
            availability = data.get("availability")
            if availability in ["private", "unavailable"]:
                return False, f"Video {availability}"

            # Check for basic metadata (if we have title, it's likely playable)
            if not data.get("title"):
                return False, "Missing video title"

            return True, "Available"

        except subprocess.TimeoutExpired:
            return False, "Timeout checking video"
        except json.JSONDecodeError:
            return False, "Invalid video metadata"
        except Exception as e:
            return False, f"Check failed: {str(e)[:50]}"

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

        # Determine how many to process
        if all_videos:
            num_to_process = len(pending)
            msg = f"[yellow]⚠ Processing ALL {len(pending)} pending videos"
            msg += " (this may take a while)[/yellow]"
            rprint(msg)
            if batch_size < len(pending):
                rprint(f"[dim]Processing in batches of {batch_size}[/dim]\n")
            else:
                rprint("[dim]Processing all at once[/dim]\n")
        else:
            num_to_process = min(batch_size, len(pending))
            rprint(f"[dim]Processing {num_to_process} video(s) (use --all to process all)[/dim]\n")

        rprint(f"Found {len(pending)} pending video(s), processing {num_to_process}...\n")

        successes = 0
        failures = 0
        skipped = 0

        from src.database import MongoDBManager

        async def process_all():
            nonlocal successes, failures, skipped

            for i, video in enumerate(pending[:num_to_process], 1):
                rprint(f"[dim]{i}/{num_to_process}[/dim] {video.title[:50]}...")

                # Apply rate limiting delay between videos
                # (in addition to handler's internal rate limiting)
                if i > 1 and settings.rate_limiting_enabled:
                    import random

                    delay = random.uniform(
                        settings.rate_limiting_min_delay, settings.rate_limiting_max_delay
                    )
                    rprint(f"  [dim]Rate limiting: waiting {delay:.1f}s...[/dim]")
                    await asyncio.sleep(delay)

                # Check video availability first
                rprint("  [dim]Checking availability...[/dim]")
                is_available, reason = check_video_availability(video.video_id)

                if not is_available:
                    rprint(f"  [yellow]⊘ Skipped: {reason}[/yellow]")
                    skipped += 1

                    # Mark as failed with reason using context manager
                    async with MongoDBManager() as db:
                        await db.mark_transcript_failed(video.video_id, reason)
                    continue

                try:
                    # Transcribe video synchronously (OpenVINO is not thread-safe)
                    rprint("  [dim]Starting transcription...[/dim]")
                    video_url = f"https://www.youtube.com/watch?v={video.video_id}"

                    # Run transcription synchronously - OpenVINO Whisper crashes in threads
                    # due to longjmp/setjmp stack frame issues
                    get_transcript(video_url, save_to_db=True)

                    # Get transcript ID and mark as completed using context manager
                    # Add retry logic in case DB write hasn't completed yet
                    transcript = None
                    max_retries = 3
                    for attempt in range(max_retries):
                        async with MongoDBManager() as db:
                            transcript = await db.get_transcript(video.video_id)
                        if transcript:
                            break
                        if attempt < max_retries - 1:
                            msg = "  [dim]   Waiting for DB write to complete "
                            msg += f"(attempt {attempt + 1}/{max_retries})...[/dim]"
                            rprint(msg)
                            await asyncio.sleep(0.5 * (attempt + 1))

                    if transcript:
                        async with MongoDBManager() as db:
                            await db.mark_transcript_completed(video.video_id, transcript["_id"])
                        rprint("  [green]✓ Transcribed and marked complete[/green]")
                        successes += 1
                    else:
                        msg = "  [yellow]⚠ Transcribed but transcript not found "
                        msg += f"in DB after {max_retries} attempts[/yellow]"
                        rprint(msg)
                        successes += 1

                except Exception as e:
                    error_msg = str(e)[:100]
                    rprint(f"  [red]✗ Error: {escape(error_msg)}[/red]")
                    failures += 1

                    # Mark as failed with error message using context manager
                    async with MongoDBManager() as db:
                        await db.mark_transcript_failed(video.video_id, error_msg)

        asyncio.run(process_all())

        # Summary
        rprint("\n[bold]Transcription Complete[/bold]")
        rprint(f"  [green]Successes: {successes}[/green]")
        rprint(f"  [red]Failures: {failures}[/red]")
        if skipped > 0:
            rprint(f"  [yellow]Skipped: {skipped}[/yellow]")
        rprint()

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


@channel_app.command("remove")
def channel_remove(
    handle: str = typer.Argument(..., help="Channel handle to remove"),
    force: bool = typer.Option(False, "-f", "--force", help="Force removal without confirmation"),
):
    """Remove a channel from tracking."""
    import asyncio

    from src.channel import resolve_channel_handle
    from src.database import get_db_manager

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
            rprint("[yellow]Channel not found[/yellow]\n")

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
