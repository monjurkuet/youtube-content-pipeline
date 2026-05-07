"""Channel management commands for CLI."""

import asyncio
from collections import Counter
from datetime import datetime, timezone

import typer
from rich import print as rprint
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from src.channel.resolver import resolve_channel_handle
from src.channel.schemas import ChannelDocument
from src.channel.sync import sync_channel
from src.database.manager import MongoDBManager
from src.services.channel_service import add_channels_from_videos_service

channel_app = typer.Typer(help="Channel tracking commands")
console = Console()


@channel_app.command("add")
def channel_add(
    handle: str = typer.Argument(..., help="Channel handle (e.g., @ChartChampions)"),
):
    """Add a YouTube channel to tracking.

    This command resolves a channel handle (e.g., "@ChannelName") to a
    channel ID and saves it to the database for future tracking.
    """

    async def _save():
        async with MongoDBManager() as db:
            try:
                channel_id, channel_url = resolve_channel_handle(handle)

                normalized_handle = handle.lstrip("@").replace(" ", "").replace("-", "")

                channel_doc = ChannelDocument(
                    channel_id=channel_id,
                    channel_handle=normalized_handle,
                    channel_title=normalized_handle,
                    channel_url=channel_url,
                )

                doc_id = await db.save_channel(channel_doc)
                return True, channel_id, channel_url, doc_id
            except Exception as e:
                return False, str(e), None, None

    rprint(f"\n[bold blue]Resolving channel: {handle}...[/bold blue]\n")
    success, result, url, doc_id = asyncio.run(_save())

    if success:
        rprint(f"[green]✓ Channel added successfully![/green]")
        rprint(f" [dim]Channel ID: {result}[/dim]")
        rprint(f" [dim]Channel URL: {url}[/dim]")
        rprint(f" [dim]Database ID: {doc_id}[/dim]\n")
        rprint(f"Use [bold]youtube-content sync {handle}[/bold] to fetch the latest videos.\n")
    else:
        rprint(f"[red]✗ Failed to add channel: {result}[/red]\n")


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
    """Add channels from YouTube video URLs."""

    async def _run():
        async with MongoDBManager() as db_manager:
            return await add_channels_from_videos_service(
                video_urls=video_urls,
                db_manager=db_manager,
                auto_sync=auto_sync,
                sync_mode=sync_mode,
            )

    try:
        results = asyncio.run(_run())

        rprint("\n" + "=" * 60)
        rprint("[bold]Summary[/bold]")
        rprint("=" * 60)
        rprint(f" [green]Channels added: {len(results['added'])}[/green]")
        if results["added"]:
            for entry in results["added"]:
                sync_info = ""
                if "sync_videos_fetched" in entry and entry["sync_videos_fetched"] is not None:
                    sync_info = f" ({entry['sync_videos_fetched']} videos)"
                elif "sync_error" in entry and entry["sync_error"]:
                    sync_info = f" (Sync failed: {entry['sync_error']})"
                rprint(f" • {entry['channel_title']}{sync_info}")

        if results["skipped_duplicate"]:
            rprint(
                f" [yellow]Skipped (duplicate in batch): {len(results['skipped_duplicate'])}[/yellow]"
            )

        if results["skipped_existing"]:
            rprint(f" [dim]Skipped (already tracked): {len(results['skipped_existing'])}[/dim]")
            for entry in results["skipped_existing"]:
                rprint(f" • {entry['channel_handle']}")

        if results["failed"]:
            rprint(f" [red]Failed: {len(results['failed'])}[/red]")
            for entry in results["failed"]:
                error_msg = entry.get("error", "Unknown error")[:50]
                rprint(f" • {entry.get('url', 'Unknown')}: {error_msg}")

        rprint("=" * 60 + "\n")
    except Exception as e:
        rprint(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)


@channel_app.command("list")
def channel_list():
    """List all tracked channels."""

    async def _fetch():
        async with MongoDBManager() as db:
            return await db.list_channels()

    channels = asyncio.run(_fetch())

    if not channels:
        rprint("\n[yellow]No channels being tracked yet.[/yellow]\n")
        rprint("Use [bold]uv run python -m src.cli channel add @Handle[/bold] to add a channel.\n")
        return

    table = Table(title="Tracked YouTube Channels")
    table.add_column("Handle", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("ID", style="dim")
    table.add_column("Last Synced", style="magenta")
    table.add_column("Videos", style="green", justify="right")

    for ch in channels:
        last_synced = ch.get("last_synced", "Never")
        if last_synced and last_synced != "Never":
            try:
                dt = datetime.fromisoformat(str(last_synced))
                last_synced = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        table.add_row(
            f"@{ch.get('channel_handle', '')}",
            ch.get("channel_title", "Unknown"),
            ch.get("channel_id", ""),
            str(last_synced),
            str(ch.get("total_videos_tracked", 0)),
        )

    rprint("\n", Panel(table, expand=False), "\n")


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
    mode = "all" if all_videos else "recent"

    rprint(f"\n[bold blue]Syncing {handle} (mode: {mode})...[/bold blue]\n")

    try:
        result = sync_channel(
            handle=handle,
            mode=mode,
            max_videos=max_videos,
            incremental=incremental,
        )

        rprint(f"\n[green]✓ Sync completed successfully![/green]")
        rprint(f" [dim]Channel: {result.channel_title}[/dim]")
        rprint(f" [dim]Videos fetched: {result.videos_fetched}[/dim]")
        rprint(f" [dim]New videos added: {result.videos_new}[/dim]")
        rprint(f" [dim]Existing videos: {result.videos_existing}[/dim]\n")
    except Exception as e:
        rprint(f"[red]✗ Sync failed: {e}[/red]\n")


@channel_app.command("sync-all")
def channel_sync_all(
    all_videos: bool = typer.Option(
        False, "--all", help="Fetch ALL videos (yt-dlp, may take time)"
    ),
    incremental: bool = typer.Option(
        True, "--incremental/--no-incremental", "-i", help="Smart incremental sync"
    ),
    max_videos: int | None = typer.Option(
        None, "--max-videos", help="Maximum videos to fetch per channel"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be synced without actually syncing"
    ),
):
    """Sync videos from all tracked channels."""

    async def _get_channels():
        async with MongoDBManager() as db:
            return await db.list_channels()

    channels = asyncio.run(_get_channels())

    if not channels:
        rprint("[yellow]No channels found. Add channels first using 'channel add'.[/yellow]")
        return

    mode = "all" if all_videos else "recent"
    rprint(
        f"\n[bold blue]Syncing {len(channels)} channels (mode: {mode}, incremental: {incremental})...[/bold blue]\n"
    )

    total_fetched = 0
    total_new = 0

    if dry_run:
        rprint("[yellow]Dry run: Information only, no changes will be made.[/yellow]\n")

    for ch in channels:
        handle = ch.get("channel_handle")
        if not handle:
            continue

        rprint(f"Processing @{handle}...")
        if dry_run:
            continue

        try:
            result = sync_channel(
                handle=f"@{handle}",
                mode=mode,
                max_videos=max_videos,
                incremental=incremental,
            )
            total_fetched += result.videos_fetched
            total_new += result.videos_new
            rprint(f" [green]✓ {result.videos_fetched} fetched ({result.videos_new} new)[/green]")
        except Exception as e:
            rprint(f" [red]✗ Failed: {e}[/red]")

    rprint(f"\n[bold green]✓ All channels synced![/bold green]")
    rprint(f" [dim]Total videos fetched: {total_fetched}[/dim]")
    rprint(f" [dim]Total new videos: {total_new}[/dim]\n")


@channel_app.command("videos")
def channel_videos(
    handle: str = typer.Argument(..., help="Channel handle (e.g., @ChartChampions)"),
    limit: int = typer.Option(20, "-l", "--limit", help="Maximum videos to show"),
    status: str | None = typer.Option(
        None, "-s", "--status", help="Filter by status (pending/completed/failed)"
    ),
):
    """List videos from a tracked channel."""

    async def _fetch_all():
        async with MongoDBManager() as db:
            ch_handle = handle.lstrip("@").replace(" ", "").replace("-", "")
            channel = await db.channels.find_one(
                {"$or": [{"channel_handle": ch_handle}, {"channel_id": handle}]}
            )

            if not channel:
                return None, None

            query = {"channel_id": channel["channel_id"]}
            if status:
                query["transcript_status"] = status

            videos = await db.video_metadata.find(query).sort("published_at", -1).to_list(limit)
            return channel, videos

    channel, videos = asyncio.run(_fetch_all())

    if not channel:
        rprint(f"[red]✗ Channel not found: {handle}[/red]")
        return

    if not videos:
        rprint(f"\n[yellow]No videos found for {channel.get('channel_title')}.[/yellow]\n")
        return

    table = Table(title=f"Videos for {channel.get('channel_title')}")
    table.add_column("Published", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("ID", style="dim")
    table.add_column("Status", style="magenta")

    for v in videos:
        pub_at = v.get("published_at", "Unknown")
        if isinstance(pub_at, datetime):
            pub_at = pub_at.strftime("%Y-%m-%d")
        elif isinstance(pub_at, str):
            try:
                dt = datetime.fromisoformat(pub_at)
                pub_at = dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        status_style = "yellow"
        if v.get("transcript_status") == "completed":
            status_style = "green"
        elif v.get("transcript_status") == "failed":
            status_style = "red"

        table.add_row(
            str(pub_at),
            escape(
                v.get("title", "Unknown")[:50] + ("..." if len(v.get("title", "")) > 50 else "")
            ),
            v.get("video_id", ""),
            f"[{status_style}]{v.get('transcript_status', 'pending')}[/{status_style}]",
        )

    rprint("\n", table, "\n")


def _classify_error_category(error: Exception) -> str:
    """Classify an exception into an error category for structured tracking."""
    from src.core.exceptions import TranscriptionFailureError
    from src.transcription.failures import classify_error_message

    if isinstance(error, TranscriptionFailureError) and error.failure:
        return error.failure.category

    return classify_error_message(str(error))


def _is_permanent_category(category: str) -> bool:
    """Check if an error category represents a permanent failure."""
    from src.transcription.failures import PERMANENT_FAILURE_CATEGORIES
    return category in PERMANENT_FAILURE_CATEGORIES


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
    include_restricted: bool = typer.Option(
        False,
        "--include-restricted",
        help="Include permanently restricted videos (members-only, private, etc.)",
    ),
    include_retryable_failed: bool = typer.Option(
        False,
        "--include-retryable-failed",
        help="Requeue retryable failed videos before processing pending",
    ),
):
    """Transcribe pending videos from channel.

    Batch size defaults to config.yaml setting (default: 5).
    Videos are processed sequentially with rate limiting delays.
    Use --all to transcribe all pending videos.
    Use --include-retryable-failed to automatically requeue transient
    failures before processing pending videos.

    The redundant pre-transcription availability check has been removed.
    The TranscriptionHandler already checks availability during download
    and raises TranscriptionFailureError with proper categories.
    """
    from src.channel.sync import get_pending_videos, mark_video_transcribed, requeue_retryable_failed
    from src.core.config import get_settings_with_yaml
    from src.pipeline import get_transcript
    from src.services.video_service import mark_video_transcription_failed

    settings = get_settings_with_yaml()

    if batch_size is None:
        batch_size = settings.batch_default_size

    try:
        channel_id = None
        channel_handle = "all channels"

        if handle:
            channel_id, _ = resolve_channel_handle(handle)
            channel_handle = f"@{handle.lstrip('@')}"

        rprint(f"\n[bold blue]Transcribing pending videos from {channel_handle}[/bold blue]\n")

        requeued_count = 0
        if include_retryable_failed:
            requeued_count = asyncio.run(requeue_retryable_failed(channel_id))
            if requeued_count > 0:
                rprint(f"[yellow]Requeued {requeued_count} retryable-failed video(s)[/yellow]\n")

        pending = asyncio.run(
            get_pending_videos(
                channel_id, skip_permanent_failures=not include_restricted
            )
        )

        if not pending:
            rprint("[green]✓ No pending videos to transcribe![/green]\n")
            return

        videos_to_process = pending if all_videos else pending[:batch_size]

        if all_videos:
            msg = f"[yellow]⚠ Processing ALL {len(videos_to_process)} pending videos"
            msg += " (this may take a while)[/yellow]"
            rprint(msg)
            if batch_size < len(videos_to_process):
                rprint(f"[dim]Processing in batches of {batch_size}[/dim]\n")
            else:
                rprint("[dim]Processing all at once[/dim]\n")
        else:
            rprint(
                f"[dim]Processing {len(videos_to_process)} video(s) "
                "(use --all to process all)[/dim]\n"
            )

        rprint(f"Found {len(pending)} pending video(s), processing {len(videos_to_process)}...\n")

        successes = 0
        failures = 0
        skipped = 0
        # Structured error tracking for summary
        category_counts: Counter = Counter()

        async def process_all():
            nonlocal successes, failures, skipped

            total_to_process = len(videos_to_process)
            for batch_start in range(0, total_to_process, batch_size):
                batch = videos_to_process[batch_start : batch_start + batch_size]
                if all_videos and total_to_process > batch_size:
                    batch_number = (batch_start // batch_size) + 1
                    total_batches = (total_to_process + batch_size - 1) // batch_size
                    rprint(
                        f"[bold]Batch {batch_number}/{total_batches}[/bold] ({len(batch)} video(s))"
                    )

                for index_in_batch, video in enumerate(batch, 1):
                    i = batch_start + index_in_batch
                    rprint(f"[dim]{i}/{total_to_process}[/dim] {video.title[:50]}...")

                    # Apply rate limiting delay between videos
                    if i > 1 and settings.rate_limiting_enabled:
                        import random

                        delay = random.uniform(
                            settings.rate_limiting_min_delay, settings.rate_limiting_max_delay
                        )
                        rprint(f" [dim]Rate limiting: waiting {delay:.1f}s...[/dim]")
                        await asyncio.sleep(delay)

                    try:
                        rprint(" [dim]Starting transcription...[/dim]")
                        video_url = f"https://www.youtube.com/watch?v={video.video_id}"
                        get_transcript(video_url, save_to_db=True)

                        # Get transcript ID and mark as completed
                        transcript = None
                        max_retries = 3
                        for attempt in range(max_retries):
                            async with MongoDBManager() as db:
                                transcript = await db.get_transcript(video.video_id)
                                if transcript:
                                    break
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(0.5 * (attempt + 1))

                        if transcript:
                            await mark_video_transcribed(video.video_id, transcript["_id"])
                            rprint(" [green]✓ Transcribed and marked complete[/green]")
                            successes += 1
                        else:
                            rprint(
                                " [yellow]⚠ Transcribed but transcript not found in DB[/yellow]"
                            )
                            successes += 1

                    except Exception as e:
                        error_msg = str(e)[:100]
                        category = _classify_error_category(e)
                        category_counts[category] += 1

                        if _is_permanent_category(category):
                            rprint(f" [red]✗ Permanent: {category}[/red] — {escape(error_msg)}")
                            skipped += 1
                        else:
                            rprint(f" [red]✗ Error ({category})[/red]: {escape(error_msg)}")
                            failures += 1

                        await mark_video_transcription_failed(
                            video.video_id,
                            error_msg,
                            category,
                        )

        asyncio.run(process_all())

        # Summary with structured error categories
        rprint("\n[bold]Transcription Complete[/bold]")
        if requeued_count > 0:
            rprint(f" [yellow]Requeued (retryable-failed): {requeued_count}[/yellow]")
        rprint(f" [green]Successes: {successes}[/green]")
        rprint(f" [red]Failures: {failures}[/red]")
        if skipped > 0:
            rprint(f" [yellow]Skipped (permanent): {skipped}[/yellow]")

        if category_counts:
            rprint("\n[bold]Error Breakdown[/bold]")
            permanent_total = 0
            retryable_total = 0
            for cat, count in category_counts.most_common():
                if _is_permanent_category(cat):
                    rprint(f" [red]{cat}[/red]: {count}")
                    permanent_total += count
                elif cat in ("temporary_block", "timeout", "remote_service"):
                    rprint(f" [yellow]{cat}[/yellow]: {count}")
                    retryable_total += count
                else:
                    rprint(f" [dim]{cat}[/dim]: {count}")

            if permanent_total or retryable_total:
                rprint(
                    f"\n [red]Permanent: {permanent_total}[/red] | "
                    f"[yellow]Retryable: {retryable_total}[/yellow]"
                )
        rprint()

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)


@channel_app.command("retry-failed")
def channel_retry_failed(
    handle: str | None = typer.Argument(
        None, help="Channel handle (optional, retry all if not specified)"
    ),
    batch_size: int | None = typer.Option(
        None,
        "-b",
        "--batch-size",
        help="Number of videos to retry per batch (default: from config.yaml)",
    ),
    all_videos: bool = typer.Option(
        False, "--all", "-a", help="Retry ALL failed videos (no limit)"
    ),
    reset_only: bool = typer.Option(
        False, "--reset", help="Reset status to pending only, don't retry now"
    ),
    category: str | None = typer.Option(
        None,
        "-c",
        "--category",
        help="Filter by error category.",
    ),
    skip_permanent: bool = typer.Option(
        True,
        "--include-restricted",
        help="Include permanently restricted videos (negates default skip)",
    ),
):
    """Retry failed transcriptions from channel.

    Resets failed transcription status to pending and optionally transcribes them.

    The redundant pre-transcription availability check has been removed.
    The TranscriptionHandler already checks availability during download
    and raises TranscriptionFailureError with proper categories.
    """
    from src.channel.sync import get_failed_videos, mark_video_transcribed
    from src.core.config import get_settings_with_yaml
    from src.pipeline import get_transcript
    from src.services.video_service import mark_video_transcription_failed

    settings = get_settings_with_yaml()

    if batch_size is None:
        batch_size = settings.batch_default_size

    try:
        channel_id = None
        channel_handle = "all channels"

        if handle:
            channel_id, _ = resolve_channel_handle(handle)
            channel_handle = f"@{handle.lstrip('@')}"

        rprint(f"\n[bold blue]Retrying failed transcriptions from {channel_handle}[/bold blue]\n")

        failed = asyncio.run(get_failed_videos(channel_id, skip_permanent_failures=skip_permanent))

        if not failed:
            rprint("[green]✓ No failed transcriptions to retry![/green]\n")
            return

        if category:
            failed = [
                v for v in failed if getattr(v, "transcript_error_category", None) == category
            ]

        if not failed:
            rprint("[yellow]✓ No failed videos match the filter criteria![/yellow]\n")
            return

        num_to_process = len(failed) if all_videos else min(batch_size, len(failed))

        if reset_only:

            async def reset_all():
                from src.services.video_service import reset_failed_transcription as do_reset

                for video in failed[:num_to_process]:
                    await do_reset(video.video_id)

            asyncio.run(reset_all())
            rprint(f"\n[green]✓ Reset {num_to_process} videos to pending status[/green]\n")
            return

        successes = failures = skipped = 0
        category_counts: Counter = Counter()

        async def process_all():
            nonlocal successes, failures, skipped
            for i, video in enumerate(failed[:num_to_process], 1):
                rprint(f"[dim]{i}/{num_to_process}[/dim] {video.title[:50]}...")

                if i > 1 and settings.rate_limiting_enabled:
                    import random

                    delay = random.uniform(
                        settings.rate_limiting_min_delay, settings.rate_limiting_max_delay
                    )
                    await asyncio.sleep(delay)

                try:
                    video_url = f"https://www.youtube.com/watch?v={video.video_id}"
                    get_transcript(video_url, save_to_db=True)

                    transcript = None
                    for attempt in range(3):
                        async with MongoDBManager() as db:
                            transcript = await db.get_transcript(video.video_id)
                            if transcript:
                                break
                            await asyncio.sleep(0.5 * (attempt + 1))

                    if transcript:
                        await mark_video_transcribed(video.video_id, transcript["_id"])
                        rprint(" [green]✓ Transcribed[/green]")
                        successes += 1
                    else:
                        successes += 1
                except Exception as e:
                    error_msg = str(e)[:100]
                    fail_category = _classify_error_category(e)
                    category_counts[fail_category] += 1

                    if _is_permanent_category(fail_category):
                        rprint(f" [red]⊘ Permanent: {fail_category}[/red] — {escape(error_msg)}")
                        skipped += 1
                    else:
                        rprint(f" [red]✗ Error ({fail_category})[/red]: {escape(error_msg)}")
                        failures += 1

                    await mark_video_transcription_failed(
                        video.video_id,
                        error_msg,
                        fail_category,
                        current_failure_count=getattr(video, "transcript_failure_count", 0) or 0,
                    )

        asyncio.run(process_all())

        # Summary with structured error categories
        rprint(f"\n[bold]Retry Complete[/bold]")
        rprint(f" [green]Successes: {successes}[/green]")
        rprint(f" [red]Failures: {failures}[/red]")
        if skipped > 0:
            rprint(f" [yellow]Skipped (permanent): {skipped}[/yellow]")

        if category_counts:
            rprint("\n[bold]Error Breakdown[/bold]")
            permanent_total = 0
            retryable_total = 0
            for cat, count in category_counts.most_common():
                if _is_permanent_category(cat):
                    rprint(f" [red]{cat}[/red]: {count}")
                    permanent_total += count
                elif cat in ("temporary_block", "timeout", "remote_service"):
                    rprint(f" [yellow]{cat}[/yellow]: {count}")
                    retryable_total += count
                else:
                    rprint(f" [dim]{cat}[/dim]: {count}")

            if permanent_total or retryable_total:
                rprint(
                    f"\n [red]Permanent: {permanent_total}[/red] | "
                    f"[yellow]Retryable: {retryable_total}[/yellow]"
                )
        rprint()

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)


@channel_app.command("restricted")
def channel_restricted(
    handle: str | None = typer.Argument(
        None, help="Channel handle (optional, list all if not specified)"
    ),
    availability_filter: str | None = typer.Option(
        None,
        "-a",
        "--availability",
        help="Filter by availability type (members_only, premium_only, private, etc.)",
    ),
):
    """List permanently restricted videos for a channel.

    Shows videos tagged as members-only, premium-only, subscriber-only,
    private, or unavailable. These are typically skipped during transcription.
    """
    from src.core.constants import PERMANENT_AVAILABILITY
    from src.database.manager import MongoDBManager

    try:
        channel_id = None
        channel_handle = "all channels"

        if handle:
            channel_id, _ = resolve_channel_handle(handle)
            channel_handle = f"@{handle.lstrip('@')}"

        rprint(f"\n[bold blue]Restricted videos for {channel_handle}[/bold blue]\n")

        async def _fetch_restricted():
            async with MongoDBManager() as db:
                query: dict = {"availability": {"$in": list(PERMANENT_AVAILABILITY)}}
                if channel_id:
                    query["channel_id"] = channel_id
                if availability_filter:
                    query["availability"] = availability_filter

                cursor = db.video_metadata.find(query).sort("published_at", -1)
                results = []
                async for doc in cursor:
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])
                    results.append(doc)
                return results

        results = asyncio.run(_fetch_restricted())

        if not results:
            rprint("[green]✓ No restricted videos found![/green]\n")
            return

        avail_counts = Counter(doc.get("availability", "unknown") for doc in results)

        rprint(f"[bold]Total: {len(results)} restricted videos[/bold]")
        for avail_type, count in avail_counts.most_common():
            rprint(f" {avail_type}: {count}")

        rprint()
        for doc in results[:50]:
            avail = doc.get("availability", "unknown")
            title = doc.get("title", "Unknown")[:60]
            video_id = doc.get("video_id", "?")
            rprint(f" [{avail}] {title}... ({video_id})")

        if len(results) > 50:
            rprint(f"\n ... and {len(results) - 50} more")

    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)


@channel_app.command("remove")
def channel_remove(
    handle: str = typer.Argument(..., help="Channel handle to remove"),
    force: bool = typer.Option(False, "-f", "--force", help="Force removal without confirmation"),
):
    """Remove a channel from tracking."""
    try:
        channel_id, _ = resolve_channel_handle(handle)
        if not force:
            if not typer.confirm(f"Remove channel @{handle.lstrip('@')} from tracking?"):
                return

        async def _delete():
            async with MongoDBManager() as db:
                return await db.delete_channel(channel_id)

        if asyncio.run(_delete()):
            rprint(f"[green]✓ Channel @{handle.lstrip('@')} removed successfully[/green]\n")
        else:
            rprint("[yellow]Channel not found[/yellow]\n")
    except Exception as e:
        rprint(f"[red]✗ Error: {escape(str(e))}[/red]")
        raise typer.Exit(1)
