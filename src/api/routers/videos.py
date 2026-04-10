"""Video transcription endpoints."""

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from src.api.dependencies import get_db, get_db_manager_dep
from src.api.models.requests import (
    JobStatusResponse,
    TranscriptionJobResponse,
    TranscriptionRequest,
)
from src.api.security import validate_api_key
from src.core.constants import JobStatus, Priority
from src.core.config import get_settings
from src.database.manager import MongoDBManager
from src.database.redis import get_redis_manager
from src.services.transcription_service import (
    get_job,
    submit_transcription_job,
    _jobs_memory,
)

# Use the same lazy accessor as transcription_service
redis_manager = get_redis_manager()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post(
    "/transcribe",
    response_model=TranscriptionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit video for transcription",
    operation_id="transcribe_video",
)
async def transcribe_video_endpoint(
    background_tasks: BackgroundTasks,
    request: TranscriptionRequest = Body(
        ...,
        openapi_examples={
            "standard": {
                "summary": "Standard request",
                "value": {
                    "source": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "priority": "normal",
                    "save_to_db": True,
                },
            }
        },
    ),
    auth_ctx=Depends(validate_api_key),
) -> TranscriptionJobResponse:
    """Submit a video for transcription."""
    # Identify video ID for response
    from src.core.utils import extract_video_id
    video_id = extract_video_id(request.source) or "unknown"

    job_id = await submit_transcription_job(
        source=request.source,
        priority=request.priority,
        save_to_db=request.save_to_db,
        webhook_url=request.webhook_url,
        auth_ctx=auth_ctx,
        background_tasks=background_tasks,
    )

    return TranscriptionJobResponse(
        job_id=job_id,
        status="queued",
        video_id=video_id,
        message="Transcription job submitted successfully",
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Check job status",
    operation_id="get_job_status",
    responses={
        200: {"description": "Job status retrieved successfully"},
        404: {"description": "Job not found"},
    },
)
async def get_job_status(
    job_id: str,
    auth_ctx=Depends(validate_api_key),
) -> JobStatusResponse:
    """Check transcription job status."""
    job = await get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Convert to response model
    return JobStatusResponse(**job)


@router.get(
    "/jobs",
    response_model=list[JobStatusResponse],
    summary="List transcription jobs",
    operation_id="list_jobs",
)
async def list_jobs(
    limit: int = 100,
    offset: int = 0,
    status_filter: str | None = None,
    auth_ctx=Depends(validate_api_key),
) -> list[JobStatusResponse]:
    """List transcription jobs."""
    jobs = []
    # Always call list_jobs - it handles auto-connect internally
    try:
        jobs = await redis_manager.list_jobs(
            limit=limit,
            offset=offset,
            status_filter=status_filter,
        )
    except Exception:
        # Fallback to memory if Redis fails
        all_jobs = list(_jobs_memory.values())
        if status_filter:
            all_jobs = [j for j in all_jobs if j.get("status") == status_filter]
        jobs = all_jobs[offset : offset + limit]

    return [JobStatusResponse(**j) for j in jobs]


# Batch Transcription models
class BatchTranscriptionRequest(BaseModel):
    """Request model for batch transcription."""
    sources: list[str] = Field(..., min_length=1)
    priority: Literal["low", "normal", "high"] = Field(default=Priority.NORMAL)
    save_to_db: bool = Field(default=True)


class BatchTranscriptionResponse(BaseModel):
    """Response model for batch transcription."""
    total_submitted: int
    jobs: list[dict[str, Any]]
    message: str


@router.post(
    "/batch-transcribe",
    response_model=BatchTranscriptionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit multiple videos for transcription",
    operation_id="batch_transcribe",
)
async def batch_transcribe(
    background_tasks: BackgroundTasks,
    request: BatchTranscriptionRequest = Body(
        ...,
        openapi_examples={
            "standard": {
                "summary": "Standard batch request",
                "value": {
                    "sources": [
                        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
                    ],
                    "priority": "normal",
                    "save_to_db": True,
                },
            }
        },
    ),
    auth_ctx=Depends(validate_api_key),
) -> BatchTranscriptionResponse:
    """Submit multiple videos for transcription."""
    jobs = []
    for source in request.sources:
        try:
            job_id = await submit_transcription_job(
                source=source,
                priority=request.priority,
                save_to_db=request.save_to_db,
                auth_ctx=auth_ctx,
                background_tasks=background_tasks,
            )
            jobs.append({"source": source, "job_id": job_id, "status": "queued"})
        except Exception as e:
            jobs.append({"source": source, "error": str(e), "status": "failed"})

    submitted = sum(1 for j in jobs if j.get("status") == "queued")
    return BatchTranscriptionResponse(
        total_submitted=submitted,
        jobs=jobs,
        message=f"Submitted {submitted} jobs",
    )


# Channel Pending Transcription models
class ChannelTranscribePendingRequest(BaseModel):
    channel_id: str
    batch_size: int = Field(default=5, ge=1, le=100)
    priority: Literal["low", "normal", "high"] = Field(default=Priority.NORMAL)


class ChannelTranscribePendingResponse(BaseModel):
    success: bool
    channel_id: str
    total_pending: int
    submitted: int
    jobs: list[dict[str, Any]]
    message: str


@router.post(
    "/channel-transcribe-pending",
    response_model=ChannelTranscribePendingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Transcribe pending videos from channel",
    operation_id="transcribe_channel_pending",
)
async def transcribe_channel_pending_endpoint(
    background_tasks: BackgroundTasks,
    request: ChannelTranscribePendingRequest = Body(
        ...,
        openapi_examples={
            "standard": {
                "summary": "Standard channel pending request",
                "value": {
                    "channel_id": "UCX6OQ3DkcsbYNE6H8uQQuVA",
                    "batch_size": 5,
                    "priority": "normal",
                },
            }
        },
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
    auth_ctx=Depends(validate_api_key),
) -> ChannelTranscribePendingResponse:
    """Transcribe pending videos from a channel."""
    channel = await db.channels.find_one({"channel_id": request.channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel {request.channel_id} not found")

    settings = get_settings()
    video_metadata = db.client[settings.mongodb_database]["video_metadata"]
    pending_videos = await video_metadata.find(
        {"channel_id": request.channel_id, "transcript_status": {"$ne": "completed"}}
    ).to_list(length=1000)

    if not pending_videos:
        return ChannelTranscribePendingResponse(
            success=True,
            channel_id=request.channel_id,
            total_pending=0,
            submitted=0,
            jobs=[],
            message="No pending videos",
        )

    jobs = []
    for video in pending_videos[:request.batch_size]:
        video_id = video.get("video_id")
        if not video_id: continue
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        try:
            job_id = await submit_transcription_job(
                source=video_url,
                priority=request.priority,
                save_to_db=True,
                auth_ctx=auth_ctx,
                background_tasks=background_tasks,
            )
            jobs.append({"video_id": video_id, "job_id": job_id, "status": "queued"})
        except Exception as e:
            jobs.append({"video_id": video_id, "error": str(e), "status": "failed"})

    submitted = sum(1 for j in jobs if j.get("status") == "queued")
    return ChannelTranscribePendingResponse(
        success=True,
        channel_id=request.channel_id,
        total_pending=len(pending_videos),
        submitted=submitted,
        jobs=jobs,
        message=f"Submitted {submitted} jobs",
    )
