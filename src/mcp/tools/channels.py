"""MCP tools for channel management.

Provides tools for:
- Adding channels to tracking
- Syncing channel videos
- Transcribing pending videos from channels
"""

from typing import Any

from src.channel.resolver import resolve_channel_handle
from src.channel.schemas import ChannelDocument, VideoMetadataDocument
from src.channel.sync import get_pending_videos, mark_video_transcribed, sync_channel
from src.core.schemas import TranscriptDocument
from src.database.manager import MongoDBManager
from src.mcp.tools.transcription import transcribe_video
from src.transcription.handler import TranscriptionHandler


async def add_channel(handle: str) -> dict[str, Any]:
    """Add a YouTube channel to tracking.

    This tool resolves a channel handle (e.g., "@ChannelName") to a
    channel ID and saves the channel information to the database.

    Args:
        handle: YouTube channel handle (with or without @ prefix)

    Returns:
        dict with keys:
            - success: Boolean indicating if channel was added
            - channel_id: Resolved channel ID
            - channel_handle: Normalized handle (without @)
            - channel_url: Channel URL
            - channel_title: Channel title/name
            - error: Error message if failed (optional)

    Example:
        result = await add_channel("@MrBeast")
        # Returns: {"success": True, "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA", ...}
    """
    try:
        # Normalize handle
        normalized_handle = handle.lstrip("@")

        # Resolve channel handle to get channel ID and URL
        channel_id, channel_url = resolve_channel_handle(handle)

        # Save channel to database
        async with MongoDBManager() as db:
            channel_doc = ChannelDocument(
                channel_id=channel_id,
                channel_handle=normalized_handle,
                channel_title=normalized_handle,  # Will be updated on sync
                channel_url=channel_url,
            )
            doc_id = await db.save_channel(channel_doc)

        return {
            "success": True,
            "channel_id": channel_id,
            "channel_handle": normalized_handle,
            "channel_url": channel_url,
            "database_id": doc_id,
            "message": f"Channel {normalized_handle} added to tracking",
        }

    except Exception as e:
        return {
            "success": False,
            "channel_handle": handle.lstrip("@"),
            "error": f"Failed to add channel: {e}",
        }


async def sync_channel(handle: str, mode: str = "recent") -> dict[str, Any]:
    """Sync videos from a YouTube channel.

    This tool fetches videos from a channel and saves their metadata
    to the database. Videos are marked as "pending" for transcription.

    Args:
        handle: YouTube channel handle (with or without @ prefix)
        mode: Sync mode - "recent" for ~15 videos via RSS, "all" for all videos

    Returns:
        dict with keys:
            - success: Boolean indicating if sync completed
            - channel_id: Channel ID
            - channel_handle: Normalized handle
            - videos_fetched: Number of videos fetched
            - videos_new: Number of new videos added
            - videos_existing: Number of existing videos updated
            - error: Error message if failed (optional)

    Example:
        result = await sync_channel("@MrBeast", mode="recent")
        # Returns: {"success": True, "videos_fetched": 15, "videos_new": 5, ...}

        result = await sync_channel("@MrBeast", mode="all")
        # Returns: {"success": True, "videos_fetched": 1000, "videos_new": 50, ...}
    """
    try:
        # Normalize handle
        normalized_handle = handle.lstrip("@")

        # Perform sync
        result = sync_channel(
            handle=handle,
            mode=mode,
            db_manager=None,  # Use default
        )

        return {
            "success": True,
            "channel_id": result.channel_id,
            "channel_handle": result.channel_handle,
            "channel_title": result.channel_title,
            "sync_mode": result.sync_mode,
            "videos_fetched": result.videos_fetched,
            "videos_new": result.videos_new,
            "videos_existing": result.videos_existing,
            "message": f"Synced {result.videos_fetched} videos ({result.videos_new} new)",
        }

    except Exception as e:
        return {
            "success": False,
            "channel_handle": normalized_handle,
            "error": f"Failed to sync channel: {e}",
        }


async def transcribe_channel_pending(handle: str, limit: int = 10) -> dict[str, Any]:
    """Transcribe all pending videos from a channel.

    This tool finds videos from a channel that haven't been transcribed
    yet and submits them for transcription.

    Args:
        handle: YouTube channel handle (with or without @ prefix)
        limit: Maximum number of videos to transcribe (default: 10)

    Returns:
        dict with keys:
            - success: Boolean indicating if operation started
            - channel_id: Channel ID
            - channel_handle: Normalized handle
            - jobs: List of job results with job_id and video_id
            - total_submitted: Number of transcription jobs submitted
            - error: Error message if failed (optional)

    Example:
        result = await transcribe_channel_pending("@MrBeast", limit=5)
        # Returns: {"success": True, "total_submitted": 5, "jobs": [...]}
    """
    try:
        # Normalize handle
        normalized_handle = handle.lstrip("@")

        # Resolve channel to get channel ID
        channel_id, _ = resolve_channel_handle(handle)

        # Get pending videos
        pending_videos = get_pending_videos(channel_id=channel_id)

        if not pending_videos:
            return {
                "success": True,
                "channel_id": channel_id,
                "channel_handle": normalized_handle,
                "jobs": [],
                "total_submitted": 0,
                "message": "No pending videos to transcribe",
            }

        # Limit the number of videos to transcribe
        videos_to_process = pending_videos[:limit]

        # Submit transcription jobs
        jobs = []
        for video in videos_to_process:
            # Transcribe the video
            job_result = await transcribe_video(
                source=video.video_id,
                priority="normal",
                save_to_db=True,
            )

            if job_result.get("status") == "completed":
                # Mark as transcribed in database
                if "database_id" in job_result:
                    mark_video_transcribed(
                        video.video_id,
                        job_result["database_id"],
                    )

            jobs.append(
                {
                    "video_id": video.video_id,
                    "video_title": video.title,
                    "job_id": job_result.get("job_id"),
                    "status": job_result.get("status"),
                }
            )

        return {
            "success": True,
            "channel_id": channel_id,
            "channel_handle": normalized_handle,
            "jobs": jobs,
            "total_submitted": len(jobs),
            "total_pending": len(pending_videos),
            "message": f"Submitted {len(jobs)} videos for transcription",
        }

    except Exception as e:
        return {
            "success": False,
            "channel_handle": normalized_handle,
            "error": f"Failed to transcribe pending videos: {e}",
        }


async def list_channels(limit: int = 100) -> dict[str, Any]:
    """List all tracked YouTube channels.

    This tool returns all channels that have been added for tracking,
    sorted by when they were added (newest first).

    Args:
        limit: Maximum number of channels to return (default: 100)

    Returns:
        dict with keys:
            - success: Boolean indicating if query succeeded
            - channels: List of channel documents
            - total: Total number of channels
            - error: Error message if failed (optional)

    Example:
        result = await list_channels()
        # Returns: {"success": True, "channels": [...], "total": 5}
    """
    try:
        async with MongoDBManager() as db:
            channels = await db.list_channels(limit=limit)

            # Get video counts for each channel
            for channel in channels:
                video_count = await db.get_video_count(
                    channel_id=channel.get("channel_id")
                )
                channel["video_count"] = video_count

            return {
                "success": True,
                "channels": channels,
                "total": len(channels),
            }

    except Exception as e:
        return {
            "success": False,
            "channels": [],
            "total": 0,
            "error": f"Failed to list channels: {e}",
        }


async def remove_channel(channel_id: str) -> dict[str, Any]:
    """Remove a channel from tracking.

    This tool removes a channel from the tracked channels list.
    Video metadata and transcripts are preserved.

    Args:
        channel_id: YouTube channel ID (e.g., UCX6OQ3DkcsbYNE6H8uQQuVA)

    Returns:
        dict with keys:
            - success: Boolean indicating if removal succeeded
            - channel_id: The removed channel ID
            - message: Status message
            - error: Error message if failed (optional)

    Example:
        result = await remove_channel("UCX6OQ3DkcsbYNE6H8uQQuVA")
        # Returns: {"success": True, "message": "Channel removed"}
    """
    try:
        async with MongoDBManager() as db:
            # Check if channel exists
            channel = await db.get_channel(channel_id)
            if channel is None:
                return {
                    "success": False,
                    "channel_id": channel_id,
                    "error": f"Channel {channel_id} not found",
                }

            # Delete the channel
            deleted = await db.delete_channel(channel_id)

            return {
                "success": deleted,
                "channel_id": channel_id,
                "message": f"Channel {channel_id} removed from tracking" if deleted else "Failed to remove channel",
            }

    except Exception as e:
        return {
            "success": False,
            "channel_id": channel_id,
            "error": f"Failed to remove channel: {e}",
        }


async def list_channel_videos(channel_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """List videos for a specific channel.

    This tool returns video metadata for all tracked videos from a channel,
    sorted by publication date (newest first).

    Args:
        channel_id: YouTube channel ID (e.g., UCX6OQ3DkcsbYNE6H8uQQuVA)
        limit: Maximum number of videos to return (default: 100)
        offset: Number of videos to skip (default: 0)

    Returns:
        dict with keys:
            - success: Boolean indicating if query succeeded
            - channel_id: The channel ID
            - videos: List of video metadata documents
            - total: Total number of videos returned
            - error: Error message if failed (optional)

    Example:
        result = await list_channel_videos("UCX6OQ3DkcsbYNE6H8uQQuVA")
        # Returns: {"success": True, "videos": [...], "total": 50}
    """
    try:
        async with MongoDBManager() as db:
            # Check if channel exists
            channel = await db.get_channel(channel_id)
            if channel is None:
                return {
                    "success": False,
                    "channel_id": channel_id,
                    "videos": [],
                    "total": 0,
                    "error": f"Channel {channel_id} not found",
                }

            # Get videos
            videos = await db.list_videos_by_channel(
                channel_id=channel_id,
                limit=limit,
                offset=offset,
            )

            # Get total count
            total_count = await db.get_video_count(channel_id=channel_id)

            return {
                "success": True,
                "channel_id": channel_id,
                "channel_title": channel.get("channel_title", "Unknown"),
                "videos": videos,
                "total": len(videos),
                "total_in_channel": total_count,
            }

    except Exception as e:
        return {
            "success": False,
            "channel_id": channel_id,
            "videos": [],
            "total": 0,
            "error": f"Failed to list channel videos: {e}",
        }
