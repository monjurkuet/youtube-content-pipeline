"""MCP tools for transcript retrieval.

Provides tools for:
- Getting individual transcripts
- Listing all transcripts
- Checking job status
"""

from typing import Any

from src.database.manager import MongoDBManager


async def get_transcript(video_id: str) -> dict[str, Any]:
    """Retrieve a transcript by video ID.

    This tool fetches a complete transcript document from the database,
    including all segments with timestamps.

    Args:
        video_id: YouTube video ID (11-character string)

    Returns:
        dict with keys:
            - found: Boolean indicating if transcript was found
            - video_id: The video ID
            - transcript: Transcript document if found (optional)
            - error: Error message if not found (optional)

    Example:
        result = await get_transcript("dQw4w9WgXcQ")
        # Returns: {"found": True, "video_id": "dQw4w9WgXcQ", "transcript": {...}}

        result = await get_transcript("nonexistent")
        # Returns: {"found": False, "video_id": "nonexistent", "error": "..."}
    """
    try:
        async with MongoDBManager() as db:
            transcript = await db.get_transcript(video_id)

        if transcript is None:
            return {
                "found": False,
                "video_id": video_id,
                "error": f"No transcript found for video ID: {video_id}",
            }

        return {
            "found": True,
            "video_id": video_id,
            "transcript": transcript,
        }

    except Exception as e:
        return {
            "found": False,
            "video_id": video_id,
            "error": f"Failed to retrieve transcript: {e}",
        }


async def list_transcripts(
    limit: int = 100,
    offset: int = 0,
    transcript_source: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """List all transcripts with optional filtering.

    This tool retrieves a paginated list of transcripts from the database.
    Results are sorted by creation date (newest first).

    Args:
        limit: Maximum number of transcripts to return (default: 100)
        offset: Number of transcripts to skip (default: 0)
        transcript_source: Filter by source ("youtube_api" or "whisper")
        language: Filter by language code (e.g., "en", "es")

    Returns:
        dict with keys:
            - transcripts: List of transcript metadata
            - total: Total count of matching transcripts
            - limit: Applied limit
            - offset: Applied offset
            - error: Error message if failed (optional)

    Example:
        result = await list_transcripts(limit=10)
        # Returns: {"transcripts": [...], "total": 150, "limit": 10, "offset": 0}

        result = await list_transcripts(transcript_source="whisper", language="en")
        # Returns: English transcripts created by Whisper
    """
    try:
        async with MongoDBManager() as db:
            transcripts = await db.list_transcripts(
                limit=limit,
                offset=offset,
                transcript_source=transcript_source,
                language=language,
            )
            total = await db.get_transcript_count(
                transcript_source=transcript_source,
                language=language,
            )

        # Return metadata only (not full segments) for list view
        transcript_summaries = []
        for t in transcripts:
            summary = {
                "video_id": t.get("video_id"),
                "title": t.get("title", "Unknown"),
                "channel_name": t.get("channel_name", "Unknown"),
                "language": t.get("language"),
                "transcript_source": t.get("transcript_source"),
                "duration_seconds": t.get("duration_seconds"),
                "segment_count": len(t.get("segments", [])),
                "created_at": t.get("created_at"),
            }
            transcript_summaries.append(summary)

        return {
            "transcripts": transcript_summaries,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        return {
            "transcripts": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "error": f"Failed to list transcripts: {e}",
        }


async def get_job_status(job_id: str) -> dict[str, Any]:
    """Check the status of a transcription job.

    This tool queries the Redis job store for the current status
    of a transcription job.

    Args:
        job_id: Job identifier (UUID format)

    Returns:
        dict with keys:
            - job_id: The job ID
            - status: Job status ("queued", "processing", "completed", "failed", "unknown")
            - progress: Progress percentage (0-100)
            - result_url: URL to retrieve results if completed (optional)
            - error: Error message if failed (optional)

    Example:
        result = await get_job_status("job_abc123_20240307120000")
        # Returns: {"job_id": "...", "status": "completed", "progress": 100, ...}
    """
    from src.database.redis import get_redis_manager

    redis_manager = get_redis_manager()

    try:
        job = await redis_manager.get_job(job_id)

        if job is None:
            return {
                "job_id": job_id,
                "status": "unknown",
                "message": f"Job {job_id} not found",
            }

        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "progress": job.get("progress_percent", 0),
            "current_step": job.get("current_step", ""),
            "video_id": job.get("video_id", ""),
            "result_url": job.get("result_url"),
            "error": job.get("error_message"),
        }

    except Exception as e:
        return {
            "job_id": job_id,
            "status": "unknown",
            "error": f"Failed to retrieve job status: {e}",
        }
