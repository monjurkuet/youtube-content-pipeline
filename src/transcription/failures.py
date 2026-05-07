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

ESCALABLE_FAILURE_CATEGORIES = frozenset(
    {
        "temporary_block",
        "timeout",
        "unknown",
    }
)

MAX_RETRIES_BEFORE_PERMANENT = 3

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


def classify_error_message(message: str) -> TranscriptionFailureCategory:
    """Classify an error message into a transcription failure category."""
    lowered = message.lower()

    if "could not identify source type" in lowered or "unsupported source type" in lowered:
        return "invalid_source"
    if "geo" in lowered or "country" in lowered or "not available in your region" in lowered:
        return "geo_restricted"
    if "members-only" in lowered or "join this channel" in lowered or "members only" in lowered:
        return "members_only"
    if "private" in lowered:
        return "private"
    if "unavailable" in lowered or "not available" in lowered:
        return "unavailable"
    if "age" in lowered and "restrict" in lowered:
        return "age_restricted"
    if "live event" in lowered or "upcoming" in lowered or "is_live" in lowered:
        return "live_stream"
    if "403" in lowered or "forbidden" in lowered or "sign in to confirm" in lowered:
        return "temporary_block"
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "http " in lowered or "too many requests" in lowered or "rate limit" in lowered or "429" in lowered:
        return "remote_service"
    return "unknown"


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
    category = classify_error_message(message)
    if category == "unknown":
        category = default_category

    return create_failure(
        message,
        category,
        stage,
        video_id=video_id,
        retryable=retryable,
    )
