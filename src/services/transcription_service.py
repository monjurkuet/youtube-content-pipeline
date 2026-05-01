"""Transcription service for managing jobs and background processing."""

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from src.api.middleware import (
    record_transcription_job_complete,
    record_transcription_job_start,
)
from src.core.constants import JobStatus, Priority
from src.core.exceptions import TranscriptionFailureError
from src.core.schemas import TranscriptionFailure
from src.database.manager import MongoDBManager
from src.database.redis import get_redis_manager
from src.pipeline.transcript import TranscriptPipeline
from src.transcription.failures import failure_from_exception
from src.transcription.handler import identify_source_type

logger = logging.getLogger(__name__)

MAX_ACQUISITION_ATTEMPTS = 3
ACQUISITION_RETRY_DELAYS_SECONDS = (5, 15)

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


def resolve_job_source_metadata(source: str) -> dict[str, str]:
    """Resolve best-effort source metadata without rejecting job submission."""
    from src.core.utils import extract_video_id

    fallback_video_id = extract_video_id(source) or hashlib.md5(source.encode()).hexdigest()[:12]

    try:
        source_type, source_identifier = identify_source_type(source)
    except Exception:
        source_type = "unknown"
        source_identifier = source

    video_id = source_identifier if source_type == "youtube" else fallback_video_id

    return {
        "video_id": video_id,
        "source_type": source_type,
        "source_identifier": source_identifier,
    }


def normalize_job_payload(job: dict[str, Any]) -> dict[str, Any]:
    """Normalize a job payload for API and webhook consumers."""
    normalized = dict(job)
    if "error_message" in normalized:
        error_message = normalized.get("error_message")
    else:
        error_message = normalized.get("error")

    normalized["error_message"] = error_message
    normalized["error"] = error_message
    normalized["error_category"] = normalized.get("error_category")
    normalized["retryable"] = bool(normalized.get("retryable", False))
    normalized["failed_stage"] = normalized.get("failed_stage")

    return normalized


def _deserialize_job_datetimes(job: dict[str, Any]) -> dict[str, Any]:
    """Convert serialized timestamps back into datetimes."""
    normalized = dict(job)
    for field in ["created_at", "started_at", "completed_at"]:
        value = normalized.get(field)
        if value and isinstance(value, str):
            try:
                normalized[field] = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
    return normalized


async def get_job(job_id: str) -> dict[str, Any] | None:
    """Get job from Redis or memory."""
    if _get_redis().is_available:
        job = await _get_redis().get_job(job_id)
        if job:
            return normalize_job_payload(_deserialize_job_datetimes(job))
        return job
    job = _jobs_memory.get(job_id)
    if job is None:
        return None
    return normalize_job_payload(_deserialize_job_datetimes(job))


async def list_jobs_data(
    limit: int = 100,
    offset: int = 0,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    """List normalized job payloads from Redis or in-memory storage."""
    jobs: list[dict[str, Any]]

    if _get_redis().is_available:
        jobs = await _get_redis().list_jobs(
            limit=limit,
            offset=offset,
            status_filter=status_filter,
        )
    else:
        jobs = list(_jobs_memory.values())
        if status_filter:
            jobs = [job for job in jobs if job.get("status") == status_filter]
        jobs = jobs[offset : offset + limit]

    return [normalize_job_payload(_deserialize_job_datetimes(job)) for job in jobs]


async def set_job(job_id: str, job_data: dict[str, Any]) -> bool:
    """Set job in Redis or memory."""
    normalized = normalize_job_payload(job_data)
    if _get_redis().is_available:
        return await _get_redis().set_job(job_id, normalized)
    _jobs_memory[job_id] = normalized
    return True


async def update_job(job_id: str, updates: dict[str, Any]) -> bool:
    """Update job in Redis or memory."""
    job = await get_job(job_id)
    if not job:
        return False
    job.update(updates)
    return await set_job(job_id, job)


async def _mark_youtube_job_failed(video_id: str, failure: TranscriptionFailure) -> None:
    """Persist a terminal YouTube failure onto video metadata when possible."""
    try:
        async with MongoDBManager() as db:
            await db.mark_transcript_failed(
                video_id,
                failure.message,
                failure.category,
            )
    except Exception as exc:
        logger.warning(
            "Failed to persist terminal job failure for %s: %s",
            video_id,
            exc,
        )


async def _acquire_transcript_with_retries(
    pipeline: TranscriptPipeline,
    job_id: str,
    source_type: str,
    source_identifier: str,
    video_id: str,
) -> Any:
    """Acquire a transcript with bounded retries for transient failures."""
    failure: TranscriptionFailure | None = None

    for attempt in range(1, MAX_ACQUISITION_ATTEMPTS + 1):
        await update_job(
            job_id,
            {
                "current_step": (
                    "Extracting audio and transcribing"
                    if attempt == 1
                    else f"Retrying transcript acquisition ({attempt}/{MAX_ACQUISITION_ATTEMPTS})"
                ),
                "progress_percent": 30.0,
            },
        )

        try:
            return await asyncio.to_thread(
                pipeline.acquire_transcript,
                source_identifier,
                source_type,
            )
        except Exception as exc:
            failure = failure_from_exception(
                exc,
                stage="pipeline",
                video_id=video_id,
                default_category="unknown",
                retryable=False,
            )
            logger.warning(
                "Transcript acquisition failed for %s on attempt %s/%s: %s",
                job_id,
                attempt,
                MAX_ACQUISITION_ATTEMPTS,
                failure.message,
            )

            if not failure.retryable or attempt >= MAX_ACQUISITION_ATTEMPTS:
                raise TranscriptionFailureError(failure) from exc

            await update_job(
                job_id,
                {
                    "current_step": (
                        f"Retrying after {failure.category} "
                        f"({attempt + 1}/{MAX_ACQUISITION_ATTEMPTS})"
                    ),
                    "error_message": failure.message,
                    "error_category": failure.category,
                    "retryable": True,
                    "failed_stage": failure.stage,
                },
            )
            await asyncio.sleep(ACQUISITION_RETRY_DELAYS_SECONDS[attempt - 1])

    if failure is None:
        failure = failure_from_exception(
            RuntimeError("Transcript acquisition ended without a result"),
            stage="pipeline",
            video_id=video_id,
            default_category="unknown",
            retryable=False,
        )
    raise TranscriptionFailureError(failure)


async def process_video_transcription(
    job_id: str,
    source: str,
    video_id: str,
    source_type: str,
    source_identifier: str,
    webhook_url: str | None = None,
    save_to_db: bool = True,
) -> None:
    """Background task to process video transcription."""
    start_time = time.perf_counter()
    logger.info("Background job %s started for %s", job_id, source)
    pipeline = TranscriptPipeline()
    resolved_source_type = source_type
    resolved_source_identifier = source_identifier

    await update_job(
        job_id,
        {
            "status": JobStatus.PROCESSING,
            "started_at": datetime.now(timezone.utc),
            "current_step": "Initializing transcription",
            "progress_percent": 10.0,
            "source_type": source_type,
            "source_identifier": source_identifier,
        },
    )

    try:
        if resolved_source_type == "unknown":
            resolved_source_type, resolved_source_identifier = pipeline.identify_source(source)
            if resolved_source_type == "youtube":
                video_id = resolved_source_identifier
            await update_job(
                job_id,
                {
                    "video_id": video_id,
                    "source_type": resolved_source_type,
                    "source_identifier": resolved_source_identifier,
                },
            )

        raw_transcript = await _acquire_transcript_with_retries(
            pipeline,
            job_id,
            resolved_source_type,
            resolved_source_identifier,
            video_id,
        )

        await update_job(
            job_id,
            {
                "current_step": "Finalizing transcript",
                "progress_percent": 80.0,
                "error_message": None,
                "error_category": None,
                "retryable": False,
                "failed_stage": None,
            },
        )

        transcript_id = None
        if save_to_db:
            transcript_id = await asyncio.to_thread(
                pipeline.persist_transcript,
                raw_transcript,
                resolved_source_type,
                source,
            )

        duration = time.perf_counter() - start_time
        logger.info("Background job %s completed successfully in %.2fs", job_id, duration)

        status_updates = {
            "status": JobStatus.COMPLETED,
            "completed_at": datetime.now(timezone.utc),
            "duration_seconds": duration,
            "video_id": raw_transcript.video_id or video_id,
            "language": raw_transcript.language,
            "transcript_source": raw_transcript.source,
            "current_step": "Completed",
            "progress_percent": 100.0,
            "error_message": None,
            "error_category": None,
            "retryable": False,
            "failed_stage": None,
            "source_type": resolved_source_type,
        }
        if transcript_id:
            status_updates["result_url"] = f"/api/v1/transcripts/{raw_transcript.video_id or video_id}"

        await update_job(job_id, status_updates)
        job_payload = await get_job(job_id)
        if job_payload is None:
            job_payload = normalize_job_payload({"job_id": job_id, **status_updates})

        # Metrics
        record_transcription_job_complete(
            source_type=resolved_source_type,
            duration_seconds=duration,
            status="success",
        )

        # Webhook
        if webhook_url:
            await send_webhook(webhook_url, job_payload)

    except Exception as e:
        failure = failure_from_exception(
            e,
            stage="pipeline",
            video_id=video_id,
            default_category="unknown",
            retryable=False,
        )
        logger.error("Background job %s failed: %s", job_id, failure.message)
        duration = time.perf_counter() - start_time

        error_updates = {
            "status": JobStatus.FAILED,
            "error_message": failure.message,
            "error_category": failure.category,
            "retryable": failure.retryable,
            "failed_stage": failure.stage,
            "completed_at": datetime.now(timezone.utc),
            "duration_seconds": duration,
            "current_step": "Failed",
            "progress_percent": 100.0,
            "source_type": resolved_source_type,
        }
        await update_job(job_id, error_updates)
        job_payload = await get_job(job_id)
        if job_payload is None:
            job_payload = normalize_job_payload({"job_id": job_id, **error_updates, "video_id": video_id})

        if save_to_db and resolved_source_type == "youtube":
            await _mark_youtube_job_failed(video_id, failure)

        # Metrics
        record_transcription_job_complete(
            source_type=resolved_source_type if resolved_source_type != "unknown" else "other",
            duration_seconds=duration,
            status="failed",
        )

        # Webhook
        if webhook_url:
            await send_webhook(webhook_url, job_payload)


async def send_webhook(
    url: str,
    job_payload: dict[str, Any],
) -> None:
    """Send webhook notification."""
    payload = {
        "job_id": job_payload.get("job_id"),
        "status": job_payload.get("status"),
        "video_id": job_payload.get("video_id"),
        "error_message": job_payload.get("error_message"),
        "error_category": job_payload.get("error_category"),
        "retryable": job_payload.get("retryable", False),
        "failed_stage": job_payload.get("failed_stage"),
        "error": job_payload.get("error"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            logger.info("Webhook sent successfully for job %s to %s", job_payload.get("job_id"), url)
    except Exception as e:
        logger.error("Failed to send webhook for job %s to %s: %s", job_payload.get("job_id"), url, e)


async def submit_transcription_job(
    source: str,
    priority: Literal["low", "normal", "high"] = Priority.NORMAL,
    save_to_db: bool = True,
    webhook_url: str | None = None,
    auth_ctx=None,
    background_tasks=None,
) -> str:
    """Submit a transcription job."""
    source_metadata = resolve_job_source_metadata(source)
    video_id = source_metadata["video_id"]
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
        "source_type": source_metadata["source_type"],
        "source_identifier": source_metadata["source_identifier"],
    }

    if auth_ctx:
        job_data["api_key_hash"] = auth_ctx.key_hash

    await set_job(job_id, job_data)

    # Metrics
    record_transcription_job_start(
        source_type=source_metadata["source_type"] if source_metadata["source_type"] != "unknown" else "other"
    )

    # Background processing
    if background_tasks:
        background_tasks.add_task(
            process_video_transcription,
            job_id,
            source,
            source_metadata["video_id"],
            source_metadata["source_type"],
            source_metadata["source_identifier"],
            webhook_url,
            save_to_db,
        )
    else:
        # Trigger background processing immediately (not recommended for sync endpoints)
        asyncio.create_task(
            process_video_transcription(
                job_id,
                source,
                source_metadata["video_id"],
                source_metadata["source_type"],
                source_metadata["source_identifier"],
                webhook_url,
                save_to_db,
            )
        )

    return job_id
