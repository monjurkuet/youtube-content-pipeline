"""Channel sync module - syncs channel videos to database."""

from datetime import datetime

from rich.console import Console

from src.video.cookie_manager import YouTubeCookieManager

from .feed_fetcher import fetch_videos
from .resolver import resolve_channel_handle
from .schemas import ChannelDocument, SyncResult, VideoMetadata, VideoMetadataDocument

console = Console()

# Global cookie manager instance
_cookie_manager: YouTubeCookieManager | None = None


def _get_cookie_manager() -> YouTubeCookieManager:
    """Get or create cookie manager instance."""
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = YouTubeCookieManager(auto_extract=True)
    return _cookie_manager


def sync_channel(
    handle: str | None = None,
    mode: str = "recent",
    db_manager=None,
    max_videos: int | None = None,
    incremental: bool = False,
    channel_id: str | None = None,
    channel_url: str | None = None,
) -> SyncResult:
    """
    Sync channel videos to database.

    Args:
        handle: Channel handle (e.g., "@ChartChampions") - optional if channel_id/channel_url provided
        mode: "recent" for RSS (~15 videos) or "all" for yt-dlp (all videos)
        db_manager: Optional MongoDB manager instance
        max_videos: Maximum videos to fetch (None = all)
        incremental: If True, only fetch metadata for new videos (slower but efficient)
        channel_id: YouTube channel ID - optional if handle provided
        channel_url: YouTube channel URL - optional if handle provided

    Returns:
        SyncResult with sync statistics
    """
    from src.database import get_db_manager as get_default_db

    db = db_manager or get_default_db()

    # Resolve channel handle or use provided channel_id/channel_url
    if channel_id and channel_url:
        # Use provided channel_id and channel_url directly
        pass
    elif handle:
        # Resolve channel handle
        channel_id, channel_url = resolve_channel_handle(handle)
    else:
        raise ValueError("Either handle or both channel_id and channel_url must be provided")

    # Fetch videos
    console.print(f"\n[bold blue]Fetching videos (mode: {mode})...[/bold blue]\n")

    videos_fetched = []

    def progress_callback(count: int):
        console.print(f"[dim]   Processed {count} videos...[/dim]")

    if mode == "all":
        if incremental:
            # Smart incremental sync: fetch IDs first, then only new videos
            videos_fetched = _fetch_new_videos_only(channel_id, channel_url, db, max_videos)
        else:
            videos_fetched = fetch_videos(
                channel_id,
                channel_url,
                "all",
                max_videos=max_videos,
            )
    else:
        videos_fetched = fetch_videos(channel_id, channel_url, "recent")

    if not videos_fetched:
        raise RuntimeError("No videos fetched from channel")

    # Save channel and videos to database in a single async context
    import asyncio

    async def _save_all():
        # Save channel to database
        console.print("\n[bold blue]Updating channel record...[/bold blue]")

        channel_doc = ChannelDocument(
            channel_id=channel_id,
            channel_handle=handle.lstrip("@") if handle else channel_id,
            channel_title=videos_fetched[0].channel_title or handle or channel_id,
            channel_url=channel_url,
            last_synced=datetime.utcnow(),
            total_videos_tracked=len(videos_fetched),
            sync_mode=mode if mode in ("recent", "all") else "recent",  # type: ignore
        )

        channel_db_id = await db.save_channel(channel_doc)
        console.print(f"[green]✓ Channel saved (ID: {channel_db_id[:16]}...)[/green]")

        # Save videos to database
        console.print(
            f"\n[bold blue]Saving {len(videos_fetched)} videos to database...[/bold blue]"
        )

        videos_new = 0
        videos_existing = 0

        for video in videos_fetched:
            video_doc = VideoMetadataDocument(
                video_id=video.video_id,
                channel_id=channel_id,
                title=video.title,
                description=video.description,
                thumbnail_url=video.thumbnail_url,
                duration_seconds=video.duration_seconds,
                view_count=video.view_count,
                published_at=video.published_at,
                transcript_status="pending",
                transcript_id=None,
                synced_at=datetime.utcnow(),
            )

            try:
                result = await db.save_video_metadata(video_doc)
                if result.get("new", False):
                    videos_new += 1
                else:
                    videos_existing += 1
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Failed to save video {video.video_id}: {e}[/yellow]"
                )
                videos_existing += 1  # Assume it exists

        console.print("\n[green]✓ Sync complete![/green]")
        console.print(f"   [dim]New videos: {videos_new}[/dim]")
        console.print(f"   [dim]Existing videos: {videos_existing}[/dim]")

        return channel_doc, videos_new, videos_existing

    # Note: asyncio.run() is safe here because sync_channel() is designed to be
    # called from synchronous contexts (CLI commands).
    channel_doc, videos_new, videos_existing = asyncio.run(_save_all())

    return SyncResult(
        channel_id=channel_id,
        channel_handle=handle.lstrip("@") if handle else channel_id,
        channel_title=channel_doc.channel_title,
        sync_mode=mode if mode in ("recent", "all") else "recent",  # type: ignore
        videos_fetched=len(videos_fetched),
        videos_new=videos_new,
        videos_existing=videos_existing,
    )


def get_pending_videos(
    channel_id: str | None = None, db_manager=None
) -> list[VideoMetadataDocument]:
    """
    Get videos pending transcription.

    Args:
        channel_id: Optional channel ID filter
        db_manager: Optional MongoDB manager instance

    Returns:
        List of VideoMetadataDocument objects
    """
    import asyncio

    from src.database import MongoDBManager

    async def _fetch():
        async with MongoDBManager() as db:
            return await db.get_pending_transcription_videos(channel_id)

    pending = asyncio.run(_fetch())

    return [
        VideoMetadataDocument(
            video_id=v["video_id"],
            channel_id=v["channel_id"],
            title=v["title"],
            description=v.get("description"),
            thumbnail_url=v.get("thumbnail_url"),
            duration_seconds=v.get("duration_seconds"),
            view_count=v.get("view_count"),
            published_at=datetime.fromisoformat(v["published_at"])
            if v.get("published_at")
            else None,
            transcript_status=v["transcript_status"],
            transcript_id=v.get("transcript_id"),
            synced_at=datetime.fromisoformat(v["synced_at"])
            if v.get("synced_at")
            else datetime.utcnow(),
        )
        for v in pending
    ]


def mark_video_transcribed(
    video_id: str,
    transcript_id: str,
    db_manager=None,
) -> bool:
    """
    Mark video as transcribed.

    Args:
        video_id: Video ID
        transcript_id: Transcript document ID
        db_manager: Optional MongoDB manager instance

    Returns:
        True if successful
    """
    import asyncio

    from src.database import MongoDBManager

    async def _mark():
        async with MongoDBManager() as db:
            return await db.mark_transcript_completed(video_id, transcript_id)

    return asyncio.run(_mark())


def _fetch_new_videos_only(
    channel_id: str,
    channel_url: str,
    db,
    max_videos: int | None = None,
) -> list[VideoMetadata]:
    """
    Fetch only NEW videos (not in database) with full metadata.

    Strategy:
    1. Fast fetch video IDs with --flat-playlist
    2. Check which IDs are already in DB
    3. Only fetch full metadata for new videos with --simulate

    Args:
        channel_id: YouTube channel ID
        channel_url: YouTube channel URL
        db: Database manager
        max_videos: Maximum videos to check

    Returns:
        List of NEW VideoMetadata objects
    """
    import asyncio
    import json
    import subprocess

    console.print("[dim]Step 1: Fetching video IDs (fast mode)...[/dim]")

    # Get cookie args
    cookie_manager = _get_cookie_manager()
    cookie_manager.ensure_cookies()
    cookie_args = cookie_manager.get_cookie_args()

    # Step 1: Fast fetch all video IDs
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--quiet",
    ]
    cmd.extend(cookie_args)  # Add cookies if available
    if max_videos:
        cmd.append(f"--playlist-end={max_videos}")
    cmd.append(channel_url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        youtube_video_ids = set()
        video_titles = {}

        for line in result.stdout.strip().split("\n"):
            if line.strip():
                try:
                    data = json.loads(line)
                    video_id = data.get("id")
                    if video_id:
                        youtube_video_ids.add(video_id)
                        video_titles[video_id] = data.get("title", "Unknown")
                except json.JSONDecodeError:
                    continue

        console.print(f"[dim]   Found {len(youtube_video_ids)} videos on YouTube[/dim]")

        # Step 2: Check which are already in DB
        async def _get_existing_ids():
            from src.database import MongoDBManager

            async with MongoDBManager() as db:
                existing = await db.list_videos_by_channel(channel_id, limit=max_videos or 10000)
                return {v["video_id"] for v in existing}

        existing_ids = asyncio.run(_get_existing_ids())
        console.print(f"[dim]   {len(existing_ids)} videos already in database[/dim]")

        # Step 3: Find new videos
        new_video_ids = youtube_video_ids - existing_ids
        console.print(f"[dim]   {len(new_video_ids)} NEW videos to fetch[/dim]")

        if not new_video_ids:
            console.print("[green]✓ No new videos![/green]")
            return []

        # Step 4: Fetch full metadata for new videos only
        console.print(
            f"\n[dim]Step 2: Fetching metadata for {len(new_video_ids)} new videos...[/dim]"
        )

        new_videos = []
        for i, video_id in enumerate(new_video_ids, 1):
            title = video_titles.get(video_id, video_id)[:50]
            console.print(f"[dim]   {i}/{len(new_video_ids)} Fetching: {title}...[/dim]")

            try:
                cmd = [
                    "yt-dlp",
                    "--simulate",
                    "--dump-json",
                    "--no-warnings",
                    "--quiet",
                ]
                cmd.extend(cookie_args)  # Add cookies if available
                cmd.append(f"https://www.youtube.com/watch?v={video_id}")

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                stderr = result.stderr.lower()

                # Check for age-restricted or private videos
                if "age" in stderr and "restrict" in stderr:
                    console.print(f"[dim]   ⊘ Skipped (age-restricted): {video_id}[/dim]")
                    continue
                if "private" in stderr or "unavailable" in stderr:
                    console.print(f"[dim]   ⊘ Skipped (private): {video_id}[/dim]")
                    continue

                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout.strip())

                    # Parse date
                    published_at = None
                    upload_date = data.get("upload_date")
                    if upload_date:
                        try:
                            from datetime import datetime

                            published_at = datetime.strptime(upload_date, "%Y%m%d")
                        except ValueError:
                            pass

                    video = VideoMetadata(
                        video_id=video_id,
                        title=data.get("title", video_titles.get(video_id, "Unknown")),
                        description=data.get("description"),
                        thumbnail_url=data.get("thumbnail"),
                        duration_seconds=int(data.get("duration"))
                        if data.get("duration")
                        else None,
                        view_count=int(data.get("view_count")) if data.get("view_count") else None,
                        published_at=published_at,
                        channel_id=channel_id,
                        channel_title=data.get("channel") or data.get("uploader"),
                    )
                    new_videos.append(video)

            except Exception as e:
                console.print(f"[yellow]   Warning: Failed to fetch {video_id}: {e}[/yellow]")
                continue

        console.print(f"\n[green]✓ Fetched {len(new_videos)} new videos with full metadata[/green]")
        return new_videos

    except subprocess.TimeoutExpired:
        console.print("[red]Error: Timeout fetching video list[/red]")
        return []
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return []
