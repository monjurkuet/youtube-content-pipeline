"""Transcription service for managing jobs and background processing."""

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.config import get_settings
from src.core.constants import JobStatus, Priority
from src.database.manager import MongoDBManager
from src.database.redis import get_redis_manager
from src.pipeline import get_transcript
from src.api.middleware import (
    record_transcription_job_complete,
    record_transcription_job_start,
)

logger = logging.getLogger(__name__)

# Lazy accessor — avoids Redis connection at import time in test/CLI contexts
_redis_manager = None
_jobs_memory: dict[str, dict[str, Any]] = {}


def _get_redis():
    """Get the Redis manager, initializing on first use."""
    global _redis_manager
    if _redis_manager is None:
        _redis_manager = get_redis_manager()
    return _redis_manager



def generate_job_id(video_id: str) -> str:
    """Generate unique job ID."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"job_{video_id}_{timestamp}"


async def get_job(job_id: str) -> dict[str, Any] | None:
    """Get job from Redis or memory."""
    if _get_redis().is_available:
        job = await _get_redis().get_job(job_id)
        if job:
            # Convert ISO format strings back to datetime
            for field in ["created_at", "started_at", "completed_at"]:
                if field in job and job[field] and isinstance(job[field], str):
                    try:
                        job[field] = datetime.fromisoformat(job[field].replace("Z", "+00:00"))
                    except ValueError:
                        pass
        return job
    return _jobs_memory.get(job_id)


async def set_job(job_id: str, job_data: dict[str, Any]) -> bool:
    """Set job in Redis or memory."""
    if _get_redis().is_available:
        return await _get_redis().set_job(job_id, job_data)
    _jobs_memory[job_id] = job_data
    return True


async def update_job(job_id: str, updates: dict[str, Any]) -> bool:
    """Update job in Redis or memory."""
    job = await get_job(job_id)
    if not job:
        return False
    job.update(updates)
    return await set_job(job_id, job)


async def process_video_transcription(
    job_id: str,
    source: str,
    webhook_url: str | None = None,
    save_to_db: bool = True,
):
    """Background task to process video transcription."""
    start_time = time.perf_counter()
    logger.info("Background job %s started for %s", job_id, source)

    await update_job(
        job_id,
        {
            "status": JobStatus.PROCESSING,
            "started_at": datetime.now(timezone.utc),
            "current_step": "Initializing transcription",
            "progress_percent": 10.0,
        },
    )

    try:
        # Step 2: Transcribe
        await update_job(
            job_id,
            {"current_step": "Extracting audio and transcribing", "progress_percent": 30.0},
        )

        # This is a CPU-bound task, but get_transcript handles its own internal threading/locking
        # for OpenVINO/Whisper.
        try:
            result = await asyncio.to_thread(get_transcript, source, save_to_db=save_to_db)
        except Exception as e:
            logger.error("Transcription engine failed for %s: %s", job_id, e)
            raise

        # Step 3: Complete
        duration = time.perf_counter() - start_time
        logger.info("Background job %s completed successfully in %.2fs", job_id, duration)

        status_updates = {
            "status": JobStatus.COMPLETED if result.success else JobStatus.FAILED,
            "completed_at": datetime.now(timezone.utc),
            "duration_seconds": duration,
            "video_id": result.video_id,
            "language": result.language,
            "transcript_source": result.transcript_source,
            "current_step": "Completed" if result.success else "Failed",
            "progress_percent": 100.0,
        }

        if not result.success:
            status_updates["error"] = result.error

        await update_job(job_id, status_updates)

        # Metrics
        record_transcription_job_complete(
            source_type=result.source_type,
            duration_seconds=duration,
            status="success" if result.success else "failed",
        )

        # Webhook
        if webhook_url:
            await send_webhook(
                webhook_url,
                job_id,
                status_updates["status"],
                result.video_id,
                result.error if not result.success else None,
            )

    except Exception as e:
        logger.error("Background job %s failed: %s", job_id, e)
        duration = time.perf_counter() - start_time

        error_updates = {
            "status": JobStatus.FAILED,
            "error": str(e),
            "completed_at": datetime.now(timezone.utc),
            "duration_seconds": duration,
            "current_step": "Error",
            "progress_percent": 100.0,
        }
        await update_job(job_id, error_updates)

        # Metrics
        record_transcription_job_complete(
            source_type="unknown",
            duration_seconds=duration,
            status="failed",
        )

        # Webhook
        if webhook_url:
            await send_webhook(webhook_url, job_id, JobStatus.FAILED, None, str(e))


async def send_webhook(
    url: str,
    job_id: str,
    status: str,
    video_id: str | None = None,
    error: str | None = None,
):
    """Send webhook notification."""
    payload = {
        "job_id": job_id,
        "status": status,
        "video_id": video_id,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            logger.info("Webhook sent successfully for job %s to %s", job_id, url)
    except Exception as e:
        logger.error("Failed to send webhook for job %s to %s: %s", job_id, url, e)


async def submit_transcription_job(
    source: str,
    priority: Literal["low", "normal", "high"] = Priority.NORMAL,
    save_to_db: bool = True,
    webhook_url: str | None = None,
    auth_ctx=None,
    background_tasks=None,
) -> str:
    """Submit a transcription job."""
    from src.core.utils import extract_video_id
    video_id = extract_video_id(source) or hashlib.md5(source.encode()).hexdigest()[:12]
    job_id = generate_job_id(video_id)

    job_data = {
        "job_id": job_id,
        "video_id": video_id,
        "status": JobStatus.QUEUED,
        "progress_percent": 0.0,
        "current_step": "Queued for processing",
        "created_at": datetime.now(timezone.utc),
        "webhook_url": webhook_url,
        "save_to_db": save_to_db,
        "priority": priority,
    }

    if auth_ctx:
        job_data["api_key_hash"] = auth_ctx.key_hash

    await set_job(job_id, job_data)

    # Metrics
    record_transcription_job_start(source_type="youtube" if "youtube" in source else "other")

    # Background processing
    if background_tasks:
        background_tasks.add_task(
            process_video_transcription,
            job_id,
            source,
            webhook_url,
            save_to_db,
        )
    else:
        # Trigger background processing immediately (not recommended for sync endpoints)
        asyncio.create_task(
            process_video_transcription(job_id, source, webhook_url, save_to_db)
        )

    return job_id
