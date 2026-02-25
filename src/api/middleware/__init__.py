"""Middleware module for the API.

This module provides middleware components for:
- Error handling and standardization
- Request/response logging
- Request ID tracking
- Performance monitoring
- Rate limiting
- Prometheus metrics
"""

from src.api.middleware.error_handler import ErrorHandlerMiddleware, setup_error_handler
from src.api.middleware.logging import LoggingMiddleware, setup_logging_middleware
from src.api.middleware.prometheus import (
    PrometheusMiddleware,
    setup_prometheus,
    record_mongodb_operation,
    record_redis_operation,
    record_transcription_error,
    record_transcription_job_complete,
    record_transcription_job_start,
)
from src.api.middleware.rate_limiter import (
    get_limiter,
    rate_limit,
    setup_rate_limiter,
    tiered_rate_limit,
)

__all__ = [
    "ErrorHandlerMiddleware",
    "setup_error_handler",
    "LoggingMiddleware",
    "setup_logging_middleware",
    "PrometheusMiddleware",
    "setup_prometheus",
    "setup_rate_limiter",
    "get_limiter",
    "rate_limit",
    "tiered_rate_limit",
    # Metrics helpers
    "record_mongodb_operation",
    "record_redis_operation",
    "record_transcription_error",
    "record_transcription_job_complete",
    "record_transcription_job_start",
]
