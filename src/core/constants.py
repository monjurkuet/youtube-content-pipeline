"""Application constants and metadata.

This module centralizes all application-wide constants for:
- Application metadata
- API versioning
- Error codes
- Configuration defaults
"""

from datetime import datetime, timezone

# Application start time (for uptime calculation)
START_TIME = datetime.now(timezone.utc)

# =============================================================================
# Application Metadata
# =============================================================================

APP_NAME = "YouTube Content Pipeline API"
APP_DESCRIPTION = """
Production-grade API for YouTube video transcription and transcript management.

## Features

- **Video Transcription**: Submit YouTube videos for asynchronous transcription
- **Transcript Management**: Retrieve, list, and manage transcripts
- **Channel Tracking**: Track YouTube channels for new content
- **Batch Processing**: Process multiple videos efficiently

## Authentication

Most endpoints require an API key passed via the `X-API-Key` header.
Contact the API administrator to obtain an API key.

## Rate Limiting

API requests are rate-limited to ensure fair usage. Rate limit headers
are included in all responses.
"""
APP_VERSION = "0.5.0"  # Updated for Phase 1 restructuring

# =============================================================================
# API Configuration
# =============================================================================

API_V1_PREFIX = "/api/v1"
API_V2_PREFIX = "/api/v2"  # Reserved for future use

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
DEFAULT_OFFSET = 0

# =============================================================================
# OpenAPI Configuration
# =============================================================================

OPENAPI_TITLE = "YouTube Content Pipeline API"
OPENAPI_VERSION = APP_VERSION
OPENAPI_DESCRIPTION = APP_DESCRIPTION

CONTACT_INFO = {
    "name": "API Support",
    "url": "https://github.com/youtube-content-pipeline",
    "email": "support@example.com",
}

LICENSE_INFO = {
    "name": "MIT",
    "url": "https://opensource.org/licenses/MIT",
}

EXTERNAL_DOCS = {
    "description": "Full documentation",
    "url": "https://youtube-content-pipeline.readthedocs.io",
}

# =============================================================================
# API Tags and Descriptions
# =============================================================================

API_TAGS = [
    {
        "name": "videos",
        "description": "Video transcription endpoints. Submit videos for transcription and check job status.",
    },
    {
        "name": "transcripts",
        "description": "Transcript management endpoints. Retrieve and list stored transcripts.",
    },
    {
        "name": "channels",
        "description": "Channel tracking endpoints. Manage tracked YouTube channels.",
    },
    {
        "name": "health",
        "description": "Health check and monitoring endpoints.",
    },
]

# =============================================================================
# Error Code Constants
# =============================================================================


class ErrorCodes:
    """Standardized error codes for consistent error handling."""

    # Validation errors (400-422)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_VIDEO_ID = "INVALID_VIDEO_ID"
    INVALID_CHANNEL_ID = "INVALID_CHANNEL_ID"
    INVALID_JOB_ID = "INVALID_JOB_ID"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_REQUEST_BODY = "INVALID_REQUEST_BODY"

    # Not found errors (404)
    NOT_FOUND = "NOT_FOUND"
    TRANSCRIPT_NOT_FOUND = "TRANSCRIPT_NOT_FOUND"
    VIDEO_NOT_FOUND = "VIDEO_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    CHANNEL_NOT_FOUND = "CHANNEL_NOT_FOUND"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"

    # Authentication errors (401-403)
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    INVALID_API_KEY = "INVALID_API_KEY"
    MISSING_API_KEY = "MISSING_API_KEY"
    EXPIRED_API_KEY = "EXPIRED_API_KEY"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"

    # Rate limiting (429)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Server errors (500-503)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    TRANSCRIPTION_ERROR = "TRANSCRIPTION_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

    # Processing errors
    PROCESSING_FAILED = "PROCESSING_FAILED"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"


# =============================================================================
# HTTP Status Code Mappings
# =============================================================================

ERROR_CODE_TO_STATUS = {
    ErrorCodes.VALIDATION_ERROR: 422,
    ErrorCodes.INVALID_VIDEO_ID: 400,
    ErrorCodes.INVALID_CHANNEL_ID: 400,
    ErrorCodes.INVALID_JOB_ID: 404,
    ErrorCodes.INVALID_PARAMETER: 400,
    ErrorCodes.MISSING_REQUIRED_FIELD: 400,
    ErrorCodes.INVALID_REQUEST_BODY: 400,
    ErrorCodes.NOT_FOUND: 404,
    ErrorCodes.TRANSCRIPT_NOT_FOUND: 404,
    ErrorCodes.VIDEO_NOT_FOUND: 404,
    ErrorCodes.JOB_NOT_FOUND: 404,
    ErrorCodes.CHANNEL_NOT_FOUND: 404,
    ErrorCodes.RESOURCE_NOT_FOUND: 404,
    ErrorCodes.AUTHENTICATION_ERROR: 401,
    ErrorCodes.INVALID_API_KEY: 401,
    ErrorCodes.MISSING_API_KEY: 401,
    ErrorCodes.EXPIRED_API_KEY: 401,
    ErrorCodes.INSUFFICIENT_PERMISSIONS: 403,
    ErrorCodes.RATE_LIMIT_EXCEEDED: 429,
    ErrorCodes.INTERNAL_ERROR: 500,
    ErrorCodes.DATABASE_ERROR: 500,
    ErrorCodes.TRANSCRIPTION_ERROR: 500,
    ErrorCodes.EXTERNAL_SERVICE_ERROR: 502,
    ErrorCodes.SERVICE_UNAVAILABLE: 503,
    ErrorCodes.PROCESSING_FAILED: 500,
    ErrorCodes.TIMEOUT_ERROR: 504,
    ErrorCodes.DUPLICATE_REQUEST: 409,
}

# =============================================================================
# Time Constants
# =============================================================================

SECOND = 1
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

# =============================================================================
# Transcription Constants
# =============================================================================

SUPPORTED_LANGUAGES = ["en", "en-US", "en-GB", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh"]
DEFAULT_LANGUAGE = "en"

TRANSCRIPT_SOURCES = ["youtube_auto", "youtube_manual", "whisper_openvino", "whisper_local"]

# =============================================================================
# Job Status Constants
# =============================================================================


class JobStatus:
    """Job status constants for transcription jobs."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


JOB_STATUSES = [
    JobStatus.QUEUED,
    JobStatus.PROCESSING,
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
]

# =============================================================================
# Priority Constants
# =============================================================================


class Priority:
    """Priority levels for job processing."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


PRIORITIES = [Priority.LOW, Priority.NORMAL, Priority.HIGH]
