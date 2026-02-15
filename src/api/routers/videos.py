"""Video transcription endpoints."""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.api.dependencies import get_db
from src.api.models.requests import (
    JobStatusResponse,
    TranscriptionJobResponse,
    TranscriptionRequest,
)
from src.pipeline import get_transcript

router = APIRouter(prefix="/videos", tags=["videos"])

# In-memory job store (replace with Redis in production)
_jobs: dict[str, dict[str, Any]] = {}


def _generate_job_id(video_id: str) -> str:
    """Generate unique job ID from video ID and timestamp."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"job_{video_id}_{timestamp}"


def _extract_video_id(source: str) -> str:
    """Extract video ID from source URL or path."""
    if "youtube.com" in source or "youtu.be" in source:
        # Extract from YouTube URL
        if "v=" in source:
            return source.split("v=")[1].split("&")[0]
        elif "youtu.be/" in source:
            return source.split("youtu.be/")[1].split("?")[0]
    # Use source as-is for local files or other URLs
    import hashlib

    return hashlib.md5(source.encode()).hexdigest()[:12]


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
    try:
        _jobs[job_id]["status"] = "processing"
        _jobs[job_id]["started_at"] = datetime.utcnow()
        _jobs[job_id]["current_step"] = "Initializing transcription"

        # Update progress
        _jobs[job_id]["progress_percent"] = 10.0
        _jobs[job_id]["current_step"] = "Getting transcript"

        # Run transcription (this is synchronous, runs in thread)
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(pool, get_transcript, source, None, save_to_db)

        _jobs[job_id]["progress_percent"] = 90.0
        _jobs[job_id]["current_step"] = "Saving results"

        # Store result reference
        _jobs[job_id]["video_id"] = result.video_id
        _jobs[job_id]["transcript_source"] = result.transcript_source
        _jobs[job_id]["segment_count"] = result.segment_count
        _jobs[job_id]["duration_seconds"] = result.duration_seconds
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["progress_percent"] = 100.0
        _jobs[job_id]["completed_at"] = datetime.utcnow()
        _jobs[job_id]["result_url"] = f"/api/v1/transcripts/{result.video_id}"

        # Send webhook if provided
        if webhook_url:
            await _send_webhook(webhook_url, job_id, "completed", result.video_id)

    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error_message"] = str(e)
        _jobs[job_id]["completed_at"] = datetime.utcnow()

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
    import httpx

    payload = {
        "job_id": job_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if video_id:
        payload["video_id"] = video_id
    if error:
        payload["error"] = error

    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, timeout=30.0)
    except Exception:
        # Log webhook failure but don't fail the job
        pass


@router.post(
    "/transcribe",
    response_model=TranscriptionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit video for transcription",
    description="Submit a video for asynchronous transcription. Returns immediately with a job ID.",
)
async def transcribe_video_endpoint(
    request: TranscriptionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> TranscriptionJobResponse:
    """Submit video for transcription.

    Returns immediately with job_id.
    Processing happens asynchronously.

    Args:
        request: Transcription request
        background_tasks: FastAPI background tasks
        db: Database dependency

    Returns:
        TranscriptionJobResponse with job details
    """
    video_id = _extract_video_id(request.source)
    job_id = _generate_job_id(video_id)

    # Initialize job record
    _jobs[job_id] = {
        "job_id": job_id,
        "video_id": video_id,
        "status": "queued",
        "progress_percent": 0.0,
        "current_step": "Queued for processing",
        "created_at": datetime.utcnow(),
        "webhook_url": request.webhook_url,
        "save_to_db": request.save_to_db,
    }

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
    if request.priority == "high":
        base_duration = 60  # 1 minute
    elif request.priority == "low":
        base_duration = 300  # 5 minutes

    return TranscriptionJobResponse(
        job_id=job_id,
        status="queued",
        video_id=video_id,
        message=f"Transcription job queued with {request.priority} priority",
        created_at=_jobs[job_id]["created_at"],
        estimated_completion=datetime.utcnow() + timedelta(seconds=base_duration),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get transcription job status",
    description="Check the status of a submitted transcription job.",
)
async def get_job_status(
    job_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> JobStatusResponse:
    """Check transcription job status.

    Args:
        job_id: Job identifier
        db: Database dependency

    Returns:
        JobStatusResponse with current status

    Raises:
        HTTPException: If job not found
    """
    if job_id not in _jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    job = _jobs[job_id]
    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        video_id=job["video_id"],
        progress_percent=job.get("progress_percent", 0.0),
        current_step=job.get("current_step", ""),
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        error_message=job.get("error_message"),
        result_url=job.get("result_url"),
    )
