"""Channel management endpoints.

This module provides endpoints for:
- Listing tracked channels
- Getting channel details
- Removing channels from tracking
- Listing videos for a channel
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.api.dependencies import get_db
from src.api.models.errors import ErrorCodes
from src.api.models.requests import (
    AddChannelsFromVideosRequest,
    AddChannelsFromVideosResponse,
)
from src.api.security import validate_api_key
from src.channel.resolver import resolve_channel_handle
from src.channel.schemas import ChannelDocument
from src.channel.sync import sync_channel
from src.core.constants import DEFAULT_LIMIT, MAX_LIMIT

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get(
    "/",
    response_model=list[dict[str, Any]],
    summary="List channels",
    description="""
    List all tracked YouTube channels.

    Returns a list of channels that have been added for tracking,
    sorted by when they were added (newest first).

    **Pagination:**
    - `limit`: Maximum number of results (default: 100, max: 1000)
    """,
    operation_id="list_channels",
    responses={
        200: {
            "description": "List of tracked channels",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
                            "channel_handle": "MrBeast",
                            "channel_title": "MrBeast",
                            "channel_url": "https://www.youtube.com/@MrBeast",
                            "tracked_since": "2024-01-15T10:30:00Z",
                            "last_sync": "2024-01-20T15:45:00Z",
                            "video_count": 750,
                        }
                    ]
                }
            },
        },
    },
)
async def list_channels(
    limit: int = Query(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of results to return",
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> list[dict[str, Any]]:
    """List all tracked channels.

    Args:
        limit: Maximum results to return (1-1000)
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        List of channel documents
    """
    cursor = db.channels.find({}).sort("tracked_since", -1).limit(limit)

    results = []
    async for doc in cursor:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        # Get video count for this channel
        video_count = await db.video_metadata.count_documents({"channel_id": doc.get("channel_id")})
        doc["video_count"] = video_count
        results.append(doc)

    return results


@router.get(
    "/{channel_id}",
    response_model=dict[str, Any],
    summary="Get channel",
    description="""
    Get details for a specific tracked channel.

    Returns channel information including:
    - Channel ID and handle
    - Channel title and URL
    - Tracking metadata
    - Video count
    """,
    operation_id="get_channel",
    responses={
        200: {
            "description": "Channel details",
        },
        404: {
            "description": "Channel not found",
        },
    },
)
async def get_channel(
    channel_id: str = Path(
        ...,
        description="YouTube channel ID",
        examples=["UCX6OQ3DkcsbYNE6H8uQQuVA"],
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> dict[str, Any]:
    """Get channel details.

    Args:
        channel_id: YouTube channel identifier
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        Channel document with video count

    Raises:
        HTTPException: If channel not found (404)
    """
    doc = await db.channels.find_one({"channel_id": channel_id})

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )

    if "_id" in doc:
        doc["_id"] = str(doc["_id"])

    # Get video count
    video_count = await db.video_metadata.count_documents({"channel_id": channel_id})
    doc["video_count"] = video_count

    # Get transcript stats
    # Get video IDs for this channel
    video_ids = []
    async for video in db.video_metadata.find({"channel_id": channel_id}, {"video_id": 1}):
        video_ids.append(video["video_id"])

    transcript_count = await db.transcripts.count_documents({"video_id": {"$in": video_ids}})
    doc["transcript_count"] = transcript_count

    return doc


@router.get(
    "/{channel_id}/videos",
    response_model=list[dict[str, Any]],
    summary="List channel videos",
    description="""
    List videos for a specific channel.

    Returns video metadata for all tracked videos from the channel,
    sorted by publication date (newest first).

    **Pagination:**
    - `limit`: Maximum number of results (default: 100, max: 1000)
    - `offset`: Number of results to skip (default: 0)

    **Filtering:**
    - `transcript_status`: Filter by transcript status (pending, completed, failed)
    """,
    operation_id="list_channel_videos",
    responses={
        200: {
            "description": "List of videos",
        },
        404: {
            "description": "Channel not found",
        },
    },
)
async def list_channel_videos(
    channel_id: str = Path(
        ...,
        description="YouTube channel ID",
        examples=["UCX6OQ3DkcsbYNE6H8uQQuVA"],
    ),
    limit: int = Query(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Maximum number of results to return",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of results to skip",
    ),
    transcript_status: str | None = Query(
        default=None,
        description="Filter by transcript status",
        examples=["pending", "completed", "failed"],
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> list[dict[str, Any]]:
    """List videos for a channel.

    Args:
        channel_id: YouTube channel identifier
        limit: Maximum results to return
        offset: Number of results to skip
        transcript_status: Optional filter by status
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        List of video metadata documents

    Raises:
        HTTPException: If channel not found (404)
    """
    # Check if channel exists
    channel = await db.channels.find_one({"channel_id": channel_id})
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )

    query: dict[str, Any] = {"channel_id": channel_id}
    if transcript_status:
        query["transcript_status"] = transcript_status

    cursor = db.video_metadata.find(query).sort("published_at", -1).skip(offset).limit(limit)

    results = []
    async for doc in cursor:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        results.append(doc)

    return results


@router.delete(
    "/{channel_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove channel",
    description="""
    Remove a channel from tracking.

    This removes the channel from the tracked channels list.
    Video metadata and transcripts are preserved.

    **Warning:** This action cannot be undone.
    """,
    operation_id="remove_channel",
    responses={
        200: {
            "description": "Channel removed successfully",
        },
        404: {
            "description": "Channel not found",
        },
    },
)
async def remove_channel(
    channel_id: str = Path(
        ...,
        description="YouTube channel ID",
        examples=["UCX6OQ3DkcsbYNE6H8uQQuVA"],
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> dict[str, Any]:
    """Remove a channel from tracking.

    Args:
        channel_id: YouTube channel identifier
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        Confirmation message

    Raises:
        HTTPException: If channel not found (404)
    """
    # Check if channel exists
    channel = await db.channels.find_one({"channel_id": channel_id})
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )

    # Delete the channel
    result = await db.channels.delete_one({"channel_id": channel_id})

    return {
        "success": result.deleted_count > 0,
        "channel_id": channel_id,
        "message": f"Channel {channel_id} removed from tracking",
    }


@router.post(
    "/{channel_id}/sync",
    status_code=status.HTTP_200_OK,
    summary="Sync channel videos",
    description="""
    Sync videos from a tracked channel.

    Fetches video metadata from YouTube and saves to the database.
    New videos are marked as "pending" for transcription.

    **Sync Modes:**
    - `recent`: Fetch ~15 most recent videos via RSS (fast)
    - `all`: Fetch all videos using yt-dlp (slower, thorough)
    """,
    operation_id="sync_channel",
    responses={
        200: {
            "description": "Sync completed",
        },
        404: {
            "description": "Channel not found",
        },
    },
)
async def sync_channel_endpoint(
    channel_id: str = Path(
        ...,
        description="YouTube channel ID",
        examples=["UCX6OQ3DkcsbYNE6H8uQQuVA"],
    ),
    mode: str = Query(
        default="recent",
        description="Sync mode: 'recent' or 'all'",
        examples=["recent", "all"],
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> dict[str, Any]:
    """Sync videos from a channel.

    Args:
        channel_id: YouTube channel identifier
        mode: Sync mode (recent or all)
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        Sync result with video counts

    Raises:
        HTTPException: If channel not found (404)
    """
    # Check if channel exists
    channel = await db.channels.find_one({"channel_id": channel_id})
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )

    try:
        # Get channel handle
        handle = channel.get("channel_handle", "")
        if not handle:
            # Extract handle from URL
            url = channel.get("channel_url", "")
            if "@" in url:
                handle = url.split("@")[-1].split("/")[0]

        if not handle:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not determine channel handle for sync",
            )

        # Perform sync
        result = sync_channel(handle=handle, mode=mode, db_manager=None)

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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {e}",
        )


@router.post(
    "/from-videos",
    status_code=status.HTTP_200_OK,
    response_model=AddChannelsFromVideosResponse,
    summary="Add channels from video URLs",
    description="""
    Add YouTube channels from video URLs.

    This endpoint extracts channel information from video URLs and adds
    the channels to tracking. Optionally syncs videos from each channel.

    **Features:**
    - Extracts channel ID and handle from video URLs
    - Skips duplicate URLs in the same batch
    - Skips channels already being tracked
    - Auto-syncs videos from new channels (configurable)
    - Returns detailed summary of added, skipped, and failed channels

    **Sync Modes:**
    - `recent`: Fetch ~15 most recent videos via RSS (fast)
    - `all`: Fetch all videos using yt-dlp (slower, thorough)
    """,
    operation_id="add_channels_from_videos",
    responses={
        200: {
            "description": "Channels added successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "added": [
                            {
                                "url": "https://youtu.be/abc123",
                                "channel_id": "UC...",
                                "channel_handle": "ChannelName",
                                "channel_title": "Channel Name",
                                "database_id": "507f1f77bcf86cd799439011",
                                "sync_videos_fetched": 15,
                                "sync_videos_new": 15,
                            }
                        ],
                        "skipped_duplicate": [],
                        "skipped_existing": [],
                        "failed": [],
                        "total_processed": 1,
                        "total_added": 1,
                        "total_skipped": 0,
                        "total_failed": 0,
                    }
                }
            },
        },
    },
)
async def add_channels_from_videos_endpoint(
    request: AddChannelsFromVideosRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> AddChannelsFromVideosResponse:
    """Add channels from YouTube video URLs.

    Args:
        request: Request with video URLs and sync options
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        AddChannelsFromVideosResponse with detailed results
    """
    import json
    import subprocess

    processed_channels: set[str] = set()
    results = {
        "added": [],
        "skipped_duplicate": [],
        "skipped_existing": [],
        "failed": [],
    }

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
        except Exception:
            return None

    for url in request.video_urls:
        video_id = extract_video_id(url)
        if not video_id:
            results["failed"].append({"url": url, "video_id": None, "error": "Invalid URL format"})
            continue

        channel_info = get_channel_from_video(video_id)
        if not channel_info:
            results["failed"].append(
                {"url": url, "video_id": video_id, "error": "Could not fetch channel info"}
            )
            continue

        channel_id = channel_info["channel_id"]
        channel_handle = channel_info["channel_handle"]

        # Check if already processed in this batch
        if channel_id in processed_channels:
            results["skipped_duplicate"].append(
                {
                    "url": url,
                    "channel_id": channel_id,
                    "channel_handle": channel_handle,
                }
            )
            continue

        # Check if channel already exists in database
        existing_channel = await db.channels.find_one({"channel_id": channel_id})
        if existing_channel:
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
            # Resolve channel handle to get proper channel URL
            resolved_handle = f"@{channel_handle}".replace(" ", "").replace("-", "")
            channel_id_resolved, channel_url = resolve_channel_handle(resolved_handle)

            # Use resolved channel_id
            channel_id = channel_id_resolved

            # Check again with resolved ID
            existing_channel = await db.channels.find_one({"channel_id": channel_id})
            if existing_channel:
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
            normalized_handle = channel_handle.replace(" ", "").replace("-", "")
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
                "channel_handle": normalized_handle,
                "channel_title": channel_doc.channel_title,
                "database_id": str(doc_id),
            }

            # Auto-sync if requested
            if request.auto_sync:
                try:
                    sync_result = sync_channel(
                        handle=f"@{normalized_handle}",
                        mode=request.sync_mode,
                        db_manager=None,
                    )
                    result_entry["sync_videos_fetched"] = sync_result.videos_fetched
                    result_entry["sync_videos_new"] = sync_result.videos_new
                except Exception as sync_error:
                    result_entry["sync_error"] = str(sync_error)

            results["added"].append(result_entry)
            processed_channels.add(channel_id)

        except Exception as e:
            results["failed"].append({"url": url, "video_id": video_id, "error": str(e)})

    return AddChannelsFromVideosResponse(
        success=True,
        added=results["added"],
        skipped_duplicate=results["skipped_duplicate"],
        skipped_existing=results["skipped_existing"],
        failed=results["failed"],
        total_processed=len(request.video_urls),
        total_added=len(results["added"]),
        total_skipped=len(results["skipped_duplicate"]) + len(results["skipped_existing"]),
        total_failed=len(results["failed"]),
    )
