"""Error response models for the API.

This module defines standardized error response formats following REST best practices.
All errors include a request_id for tracing and debugging.
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response model.

    All API errors return this format to ensure consistent client error handling.

    Attributes:
        error: Error type identifier (e.g., "VALIDATION_ERROR", "NOT_FOUND")
        error_code: Machine-readable error code for programmatic handling
        message: Human-readable error message
        details: Additional error context (validation errors, stack traces, etc.)
        request_id: Unique request identifier for tracing
        timestamp: ISO 8601 timestamp of when the error occurred
    """

    error: str = Field(
        ...,
        description="Error type identifier",
        examples=["VALIDATION_ERROR"],
    )
    error_code: str = Field(
        ...,
        description="Machine-readable error code",
        examples=["INVALID_VIDEO_ID"],
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["The provided video ID is invalid or not found"],
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Additional error details and context",
        examples=[{"field": "video_id", "reason": "invalid format"}],
    )
    request_id: str = Field(
        ...,
        description="Unique request identifier for tracing",
        examples=["req_abc123def456"],
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of error occurrence",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "NOT_FOUND",
                "error_code": "TRANSCRIPT_NOT_FOUND",
                "message": "The requested transcript was not found",
                "details": {"video_id": "dQw4w9WgXcQ"},
                "request_id": "req_abc123def456",
                "timestamp": "2024-01-15T10:30:00Z",
            }
        }
    }


class ValidationErrorResponse(ErrorResponse):
    """Validation error response for request validation failures.

    Used when request body, query parameters, or path parameters fail validation.
    """

    error: str = Field(default="VALIDATION_ERROR", frozen=True)
    details: dict[str, Any] = Field(  # type: ignore[assignment]
        default_factory=dict,
        description="Validation errors by field",
        examples=[{"field": "video_id", "errors": ["must be a valid YouTube video ID"]}],
    )


class NotFoundErrorResponse(ErrorResponse):
    """Not found error response for missing resources.

    Used when a requested resource (video, transcript, job) does not exist.
    """

    error: str = Field(default="NOT_FOUND", frozen=True)
    error_code: str = Field(
        ...,
        description="Specific not found error code",
        examples=["TRANSCRIPT_NOT_FOUND", "VIDEO_NOT_FOUND", "JOB_NOT_FOUND"],
    )


class AuthenticationErrorResponse(ErrorResponse):
    """Authentication error response for auth failures.

    Used when API key is missing, invalid, or expired.
    """

    error: str = Field(default="AUTHENTICATION_ERROR", frozen=True)
    error_code: str = Field(
        default="INVALID_API_KEY",
        description="Authentication failure reason",
    )


class RateLimitErrorResponse(ErrorResponse):
    """Rate limit error response for throttled requests.

    Used when client has exceeded rate limits.
    """

    error: str = Field(default="RATE_LIMIT_EXCEEDED", frozen=True)
    error_code: str = Field(default="RATE_LIMIT_EXCEEDED", frozen=True)
    details: dict[str, Any] = Field(  # type: ignore[assignment]
        default_factory=lambda: {
            "retry_after": 60,
            "limit": 100,
            "remaining": 0,
            "reset_at": "2024-01-15T10:31:00Z",
        },
        description="Rate limit information",
    )


class InternalServerErrorResponse(ErrorResponse):
    """Internal server error response for unexpected failures.

    Used for unhandled exceptions and system errors.
    """

    error: str = Field(default="INTERNAL_SERVER_ERROR", frozen=True)
    error_code: str = Field(default="INTERNAL_ERROR", frozen=True)
    message: str = Field(
        default="An unexpected error occurred. Please try again later.",
        description="Generic error message to avoid leaking internal details",
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Error details (only in non-production environments)",
    )


# Error code constants for consistent usage across the codebase
class ErrorCodes:
    """Standardized error codes for the API."""

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_VIDEO_ID = "INVALID_VIDEO_ID"
    INVALID_CHANNEL_ID = "INVALID_CHANNEL_ID"
    INVALID_JOB_ID = "INVALID_JOB_ID"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_PARAMETER = "INVALID_PARAMETER"

    # Not found errors
    NOT_FOUND = "NOT_FOUND"
    TRANSCRIPT_NOT_FOUND = "TRANSCRIPT_NOT_FOUND"
    VIDEO_NOT_FOUND = "VIDEO_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    CHANNEL_NOT_FOUND = "CHANNEL_NOT_FOUND"

    # Authentication errors
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    INVALID_API_KEY = "INVALID_API_KEY"
    MISSING_API_KEY = "MISSING_API_KEY"
    EXPIRED_API_KEY = "EXPIRED_API_KEY"

    # Rate limiting
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Server errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    TRANSCRIPTION_ERROR = "TRANSCRIPTION_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
