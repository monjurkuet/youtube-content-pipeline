"""Helpers for structured transcription failures."""

from src.core.exceptions import TranscriptionFailureError
from src.core.schemas import (
    TranscriptionFailure,
    TranscriptionFailureCategory,
    TranscriptionFailureStage,
)

RETRYABLE_FAILURE_CATEGORIES = frozenset(
    {
        "temporary_block",
        "timeout",
        "remote_service",
    }
)

PERMANENT_FAILURE_CATEGORIES = frozenset(
    {
        "members_only",
        "geo_restricted",
        "age_restricted",
        "private",
        "unavailable",
        "invalid_source",
    }
)


def is_retryable_failure_category(category: TranscriptionFailureCategory) -> bool:
    """Return whether the category should be retried automatically."""
    return category in RETRYABLE_FAILURE_CATEGORIES


def is_permanent_failure_category(category: TranscriptionFailureCategory) -> bool:
    """Return whether the category represents a permanent, non-retryable failure."""
    return category in PERMANENT_FAILURE_CATEGORIES


def create_failure(
    message: str,
    category: TranscriptionFailureCategory,
    stage: TranscriptionFailureStage,
    *,
    video_id: str | None = None,
    retryable: bool | None = None,
) -> TranscriptionFailure:
    """Create a structured transcription failure."""
    return TranscriptionFailure(
        message=message,
        category=category,
        retryable=is_retryable_failure_category(category) if retryable is None else retryable,
        stage=stage,
        video_id=video_id,
    )


def failure_from_exception(
    exc: Exception,
    *,
    stage: TranscriptionFailureStage,
    video_id: str | None = None,
    default_category: TranscriptionFailureCategory = "unknown",
    retryable: bool | None = None,
) -> TranscriptionFailure:
    """Normalize an exception into a structured transcription failure."""
    if isinstance(exc, TranscriptionFailureError):
        failure = exc.failure
        if video_id is None or failure.video_id == video_id:
            return failure
        return failure.model_copy(update={"video_id": video_id})

    message = str(exc).strip() or "Unexpected transcription failure"
    lowered = message.lower()
    category = default_category

    if "could not identify source type" in lowered or "unsupported source type" in lowered:
        category = "invalid_source"
    elif "timeout" in lowered or "timed out" in lowered:
        category = "timeout"
    elif "http " in lowered or "too many requests" in lowered or "rate limit" in lowered:
        category = "remote_service"

    return create_failure(
        message,
        category,
        stage,
        video_id=video_id,
        retryable=retryable,
    )
