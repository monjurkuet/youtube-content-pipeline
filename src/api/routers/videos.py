"""Video transcription endpoints.

This module provides endpoints for:
- Submitting videos for transcription
- Checking transcription job status

Uses Redis for job storage when available, with in-memory fallback.
"""

import asyncio
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from slowapi import Limiter

from src.api.dependencies import get_db
from src.api.middleware import (
    record_transcription_job_complete,
    record_transcription_job_start,
)
from src.api.models.errors import ErrorCodes
from src.api.models.requests import (
    JobStatusResponse,
    TranscriptionJobResponse,
    TranscriptionRequest,
)
from src.api.security import validate_api_key
from src.core.constants import JobStatus, Priority
from src.core.config import get_settings
from src.database.redis import get_redis_manager
from src.pipeline import get_transcript

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["videos"])

# Get Redis manager for job storage
redis_manager = get_redis_manager()

# In-memory fallback (used when Redis is unavailable)
_jobs_memory: dict[str, dict[str, Any]] = {}


def _generate_job_id(video_id: str) -> str:
    """Generate unique job ID from video ID and timestamp.

    Args:
        video_id: YouTube video ID

    Returns:
        Unique job identifier
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"job_{video_id}_{timestamp}"


def _extract_video_id(source: str) -> str:
    """Extract video ID from source URL or path.

    Args:
        source: YouTube URL, video URL, or local file path

    Returns:
        Extracted or generated video ID
    """
    if "youtube.com" in source or "youtu.be" in source:
        # Extract from YouTube URL
        if "v=" in source:
            return source.split("v=")[1].split("&")[0]
        elif "youtu.be/" in source:
            return source.split("youtu.be/")[1].split("?")[0]
    # Use source as-is for local files or other URLs
    return hashlib.md5(source.encode()).hexdigest()[:12]


async def _get_job(job_id: str) -> dict[str, Any] | None:
    """Get job from Redis or memory.

    Args:
        job_id: Job identifier

    Returns:
        Job data or None
    """
    if redis_manager.is_available:
        job = await redis_manager.get_job(job_id)
        if job:
            # Convert ISO format strings back to datetime
            for field in ["created_at", "started_at", "completed_at"]:
                if field in job and job[field]:
                    try:
                        job[field] = datetime.fromisoformat(job[field].replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
            return job

    return _jobs_memory.get(job_id)


async def _set_job(job_id: str, job_data: dict[str, Any]) -> bool:
    """Set job in Redis or memory.

    Args:
        job_id: Job identifier
        job_data: Job data

    Returns:
        True if successful
    """
    # Convert datetime to ISO format for JSON serialization
    serialized_data = job_data.copy()
    for field in ["created_at", "started_at", "completed_at"]:
        if field in serialized_data and serialized_data[field]:
            if isinstance(serialized_data[field], datetime):
                serialized_data[field] = serialized_data[field].isoformat()

    if redis_manager.is_available:
        return await redis_manager.set_job(job_id, serialized_data)

    _jobs_memory[job_id] = serialized_data
    return True


async def _update_job(job_id: str, updates: dict[str, Any]) -> bool:
    """Update job in Redis or memory.

    Args:
        job_id: Job identifier
        updates: Fields to update

    Returns:
        True if successful
    """
    # Convert datetime to ISO format
    serialized_updates = updates.copy()
    for field in ["created_at", "started_at", "completed_at"]:
        if field in serialized_updates and serialized_updates[field]:
            if isinstance(serialized_updates[field], datetime):
                serialized_updates[field] = serialized_updates[field].isoformat()

    if redis_manager.is_available:
        return await redis_manager.update_job(job_id, serialized_updates)

    if job_id in _jobs_memory:
        _jobs_memory[job_id].update(serialized_updates)
        return True
    return False


async def _process_video_transcription(
    job_id: str,
    source: str,
    webhook_url: str | None,
    save_to_db: bool,
) -> None:
    """Background task to process video transcription.

    Args:
        job_id: Unique job identifier
        source: Video source (URL or path)
        webhook_url: Optional webhook to notify on completion
        save_to_db: Whether to save transcript to database
    """
    start_time = datetime.now(timezone.utc)

    try:
        await _update_job(
            job_id,
            {
                "status": JobStatus.PROCESSING,
                "started_at": datetime.now(timezone.utc),
                "current_step": "Initializing transcription",
            },
        )

        # Update progress
        await _update_job(
            job_id,
            {
                "progress_percent": 10.0,
                "current_step": "Getting transcript",
            },
        )

        # Run transcription (this is synchronous, runs in thread)
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool,
                lambda: get_transcript(source, None, save_to_db),
            )

        await _update_job(
            job_id,
            {
                "progress_percent": 90.0,
                "current_step": "Saving results",
            },
        )

        # Store result reference
        await _update_job(
            job_id,
            {
                "video_id": result.video_id,
                "transcript_source": result.transcript_source,
                "segment_count": result.segment_count,
                "duration_seconds": result.duration_seconds,
                "status": JobStatus.COMPLETED,
                "progress_percent": 100.0,
                "completed_at": datetime.now(timezone.utc),
                "result_url": f"/api/v1/transcripts/{result.video_id}",
            },
        )

        # Record metrics
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        record_transcription_job_complete(
            source_type="youtube",
            duration_seconds=duration,
            status="success",
        )

        # Send webhook if provided
        if webhook_url:
            await _send_webhook(webhook_url, job_id, "completed", result.video_id)

    except Exception as e:
        logger.exception("Transcription failed for job %s", job_id)

        await _update_job(
            job_id,
            {
                "status": JobStatus.FAILED,
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc),
            },
        )

        # Record metrics
        record_transcription_job_complete(
            source_type="youtube",
            duration_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
            status="failed",
        )

        if webhook_url:
            await _send_webhook(webhook_url, job_id, "failed", error=str(e))


async def _send_webhook(
    url: str,
    job_id: str,
    status: str,
    video_id: str | None = None,
    error: str | None = None,
) -> None:
    """Send webhook notification.

    Args:
        url: Webhook URL
        job_id: Job identifier
        status: Job status
        video_id: Video ID (if successful)
        error: Error message (if failed)
    """
    payload = {
        "job_id": job_id,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if video_id:
        payload["video_id"] = video_id
    if error:
        payload["error"] = error

    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, timeout=30.0)
    except Exception as e:
        logger.warning("Webhook failed for job %s: %s", job_id, e)
        # Log webhook failure but don't fail the job


@router.post(
    "/transcribe",
    response_model=TranscriptionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit video for transcription",
    description="""
    Submit a video for asynchronous transcription. Returns immediately with a job ID.

    The transcription process runs in the background. Use the job ID to check status
    via the `/videos/jobs/{job_id}` endpoint.

    **Priority Levels:**
    - `low`: Processed when resources are available
    - `normal`: Standard processing queue
    - `high`: Prioritized processing

    **Webhook Notification:**
    Optionally provide a webhook URL to receive notifications when transcription completes.
    """,
    operation_id="submit_video_transcription",
    responses={
        202: {
            "description": "Job accepted for processing",
        },
        401: {
            "description": "Invalid or missing API key",
        },
        429: {
            "description": "Rate limit exceeded",
        },
    },
)
async def transcribe_video_endpoint(
    request: TranscriptionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> TranscriptionJobResponse:
    """Submit video for transcription.

    Returns immediately with job_id. Processing happens asynchronously.

    Args:
        request: Transcription request with video source and options
        background_tasks: FastAPI background tasks
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        TranscriptionJobResponse with job details

    Raises:
        HTTPException: If request validation fails
    """
    video_id = _extract_video_id(request.source)
    job_id = _generate_job_id(video_id)

    # Initialize job record
    job_data = {
        "job_id": job_id,
        "video_id": video_id,
        "status": JobStatus.QUEUED,
        "progress_percent": 0.0,
        "current_step": "Queued for processing",
        "created_at": datetime.now(timezone.utc),
        "webhook_url": request.webhook_url,
        "save_to_db": request.save_to_db,
        "priority": request.priority,
    }

    if auth_ctx:
        job_data["api_key_hash"] = auth_ctx.key_hash

    await _set_job(job_id, job_data)

    # Record metrics
    record_transcription_job_start(source_type="youtube")

    # Trigger background processing
    background_tasks.add_task(
        _process_video_transcription,
        job_id,
        request.source,
        request.webhook_url,
        request.save_to_db,
    )

    # Estimate completion (rough estimate: 1-3 minutes based on priority)
    base_duration = 180  # 3 minutes
    if request.priority == Priority.HIGH:
        base_duration = 60  # 1 minute
    elif request.priority == Priority.LOW:
        base_duration = 300  # 5 minutes

    return TranscriptionJobResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        video_id=video_id,
        message=f"Transcription job queued with {request.priority} priority",
        created_at=job_data["created_at"],
        estimated_completion=datetime.now(timezone.utc) + timedelta(seconds=base_duration),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get transcription job status",
    description="""
    Check the status of a submitted transcription job.

    **Job Statuses:**
    - `queued`: Job is waiting to be processed
    - `processing`: Job is currently being processed
    - `completed`: Job completed successfully
    - `failed`: Job failed with an error

    **Progress Information:**
    When processing, the response includes:
    - `progress_percent`: Completion percentage (0-100)
    - `current_step`: Description of current processing step
    """,
    operation_id="get_transcription_job_status",
    responses={
        200: {
            "description": "Job status retrieved successfully",
        },
        404: {
            "description": "Job not found",
        },
        401: {
            "description": "Invalid or missing API key",
        },
    },
)
async def get_job_status(
    job_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> JobStatusResponse:
    """Check transcription job status.

    Args:
        job_id: Job identifier
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        JobStatusResponse with current status

    Raises:
        HTTPException: If job not found (404)
    """
    job = await _get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        video_id=job.get("video_id", ""),
        progress_percent=job.get("progress_percent", 0.0),
        current_step=job.get("current_step", ""),
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        error_message=job.get("error_message"),
        result_url=job.get("result_url"),
    )


@router.get(
    "/jobs",
    response_model=list[JobStatusResponse],
    summary="List transcription jobs",
    description="List all transcription jobs with optional status filtering.",
    operation_id="list_transcription_jobs",
    responses={
        200: {
            "description": "List of jobs",
        },
        401: {
            "description": "Invalid or missing API key",
        },
    },
)
async def list_jobs(
    limit: int = 100,
    offset: int = 0,
    status_filter: str | None = None,
    auth_ctx=Depends(validate_api_key),
) -> list[JobStatusResponse]:
    """List transcription jobs.

    Args:
        limit: Maximum number of jobs to return
        offset: Number of jobs to skip
        status_filter: Optional filter by status
        auth_ctx: Authentication context (optional)

    Returns:
        List of JobStatusResponse
    """
    if redis_manager.is_available:
        jobs = await redis_manager.list_jobs(
            limit=limit,
            offset=offset,
            status_filter=status_filter,
        )
    else:
        # In-memory fallback
        jobs = list(_jobs_memory.values())
        if status_filter:
            jobs = [j for j in jobs if j.get("status") == status_filter]
        jobs = jobs[offset : offset + limit]

    return [
        JobStatusResponse(
            job_id=job["job_id"],
            status=job["status"],
            video_id=job.get("video_id", ""),
            progress_percent=job.get("progress_percent", 0.0),
            current_step=job.get("current_step", ""),
            started_at=job.get("started_at"),
            completed_at=job.get("completed_at"),
            error_message=job.get("error_message"),
            result_url=job.get("result_url"),
        )
        for job in jobs
    ]


# =============================================================================
# Batch Transcription
# =============================================================================


class BatchTranscriptionRequest(BaseModel):
    """Request model for batch transcription."""

    sources: list[str] = Field(
        ...,
        description="List of video sources (YouTube URLs/IDs, local paths, or remote URLs)",
        min_length=1,
        max_length=100,
        examples=[["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"]],
    )
    priority: Literal["low", "normal", "high"] = Field(
        default="normal",
        description="Processing priority for all jobs",
    )
    save_to_db: bool = Field(
        default=True,
        description="Whether to save transcripts to database",
    )


class BatchTranscriptionResponse(BaseModel):
    """Response model for batch transcription."""

    total_submitted: int = Field(..., description="Total number of jobs submitted")
    jobs: list[dict[str, Any]] = Field(..., description="List of job results")
    message: str = Field(..., description="Summary message")


@router.post(
    "/batch-transcribe",
    response_model=BatchTranscriptionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Batch transcribe videos",
    description="""
    Submit multiple videos for transcription in a single request.

    Accepts up to 100 video sources at once. Each source can be:
    - YouTube URL (e.g., https://www.youtube.com/watch?v=VIDEO_ID)
    - YouTube video ID (11-character ID)
    - Local file path
    - Remote video URL

    Returns immediately with job IDs for all submitted videos.
    Use the `/videos/jobs/{job_id}` endpoint to check individual job status.
    """,
    operation_id="batch_transcribe_videos",
    responses={
        202: {
            "description": "Jobs accepted for processing",
        },
        400: {
            "description": "Invalid request (too many sources, empty list, etc.)",
        },
    },
)
async def batch_transcribe(
    request: BatchTranscriptionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> BatchTranscriptionResponse:
    """Submit multiple videos for transcription.

    Args:
        request: Batch transcription request with sources list
        background_tasks: FastAPI background tasks
        db: Database dependency
        auth_ctx: Authentication context (optional)

    Returns:
        BatchTranscriptionResponse with job details
    """
    jobs = []

    for source in request.sources:
        try:
            video_id = _extract_video_id(source)
            job_id = _generate_job_id(video_id)

            # Initialize job record
            job_data = {
                "job_id": job_id,
                "video_id": video_id,
                "status": JobStatus.QUEUED,
                "progress_percent": 0.0,
                "current_step": "Queued for processing",
                "created_at": datetime.now(timezone.utc),
                "save_to_db": request.save_to_db,
                "priority": request.priority,
            }

            await _set_job(job_id, job_data)

            # Record metrics
            record_transcription_job_start(source_type="youtube")

            # Trigger background processing
            background_tasks.add_task(
                _process_video_transcription,
                job_id,
                source,
                None,  # No webhook for batch
                request.save_to_db,
            )

            jobs.append({
                "source": source,
                "video_id": video_id,
                "job_id": job_id,
                "status": "queued",
            })

        except Exception as e:
            jobs.append({
                "source": source,
                "error": str(e),
                "status": "failed",
            })

    successful = sum(1 for j in jobs if j.get("status") == "queued")
    failed = len(jobs) - successful

    return BatchTranscriptionResponse(
        total_submitted=successful,
        jobs=jobs,
        message=f"Submitted {successful} jobs ({failed} failed)",
    )
