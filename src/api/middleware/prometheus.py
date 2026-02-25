"""Prometheus metrics middleware and instrumentation.

This module provides:
- Custom metrics for transcription jobs
- API request metrics
- Database operation metrics
- Redis operation metrics
- /metrics endpoint for Prometheus scraping

Usage:
    # In app.py
    from src.api.middleware.prometheus import setup_prometheus

    app = FastAPI()
    setup_prometheus(app)
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
    start_http_server,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from src.core.config import get_settings

logger = logging.getLogger(__name__)


# Custom Metrics

# Transcription job metrics
transcription_jobs_total = Counter(
    "transcription_jobs_total",
    "Total number of transcription jobs submitted",
    ["status", "source_type"],
)

transcription_jobs_in_progress = Gauge(
    "transcription_jobs_in_progress",
    "Number of transcription jobs currently in progress",
)

transcription_duration_seconds = Histogram(
    "transcription_duration_seconds",
    "Time spent on transcription jobs",
    ["status", "source_type"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, float("inf")),
)

transcription_errors_total = Counter(
    "transcription_errors_total",
    "Total number of transcription errors",
    ["error_type", "source_type"],
)

# API request metrics
api_requests_total = Counter(
    "api_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status"],
)

api_request_duration_seconds = Histogram(
    "api_request_duration_seconds",
    "API request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, float("inf")),
)

# Database operation metrics
mongodb_operations_total = Counter(
    "mongodb_operations_total",
    "Total number of MongoDB operations",
    ["operation", "collection", "status"],
)

mongodb_operation_duration_seconds = Histogram(
    "mongodb_operation_duration_seconds",
    "MongoDB operation latency in seconds",
    ["operation", "collection"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, float("inf")),
)

# Redis operation metrics
redis_operations_total = Counter(
    "redis_operations_total",
    "Total number of Redis operations",
    ["operation", "status"],
)

redis_operation_duration_seconds = Histogram(
    "redis_operation_duration_seconds",
    "Redis operation latency in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, float("inf")),
)

# System metrics
app_info = Gauge(
    "app_info",
    "Application information",
    ["version", "environment"],
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics for API requests."""

    def __init__(self, app: Any, app_name: str = "transcription-pipeline") -> None:
        """Initialize middleware.

        Args:
            app: FastAPI application
            app_name: Application name for metrics
        """
        super().__init__(app)
        self.app_name = app_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request and collect metrics.

        Args:
            request: FastAPI request object
            call_next: Next middleware/handler

        Returns:
            Response with metrics collected
        """
        # Skip metrics endpoint
        if request.url.path == "/metrics":
            return await call_next(request)

        # Record start time
        start_time = time.perf_counter()

        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise
        finally:
            # Calculate duration
            duration = time.perf_counter() - start_time

            # Normalize endpoint path (remove IDs)
            endpoint = self._normalize_endpoint(request.url.path)
            method = request.method

            # Record metrics
            api_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status=status_code,
            ).inc()

            api_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

        return response

    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for metrics (remove IDs).

        Args:
            path: Request path

        Returns:
            Normalized path
        """
        import re

        # Replace UUIDs
        path = re.sub(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "/{uuid}",
            path,
        )

        # Replace numeric IDs
        path = re.sub(r"/\d+", "/{id}", path)

        # Replace YouTube video IDs (11 chars)
        path = re.sub(r"/[a-zA-Z0-9_-]{11}(?=/|$)", "/{video_id}", path)

        return path


def setup_prometheus(app: FastAPI) -> None:
    """Set up Prometheus metrics and endpoint.

    Args:
        app: FastAPI application
    """
    settings = get_settings()

    if not settings.prometheus_enabled:
        logger.info("Prometheus metrics disabled")
        return

    # Set app info
    from src.core.constants import APP_VERSION

    app_info.labels(version=APP_VERSION, environment="production").set(1)

    # Add middleware
    app.add_middleware(PrometheusMiddleware, app_name=app.title)

    # Add metrics endpoint
    @app.get(settings.prometheus_path)
    async def metrics_endpoint() -> Response:
        """Prometheus metrics endpoint.

        Returns:
            Prometheus metrics in text format
        """
        from prometheus_client import REGISTRY
        from starlette.responses import Response as StarletteResponse

        # Generate metrics from default registry
        metrics = generate_latest(REGISTRY)

        return StarletteResponse(
            content=metrics,
            status_code=200,
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info(
        "Prometheus metrics enabled",
        extra={"path": settings.prometheus_path},
    )


# Helper functions for recording metrics


def record_transcription_job_start(source_type: str) -> None:
    """Record start of a transcription job.

    Args:
        source_type: Type of source (youtube, file, etc.)
    """
    transcription_jobs_total.labels(status="started", source_type=source_type).inc()
    transcription_jobs_in_progress.inc()


def record_transcription_job_complete(
    source_type: str,
    duration_seconds: float,
    status: str = "success",
) -> None:
    """Record completion of a transcription job.

    Args:
        source_type: Type of source
        duration_seconds: Job duration
        status: Job status (success, failed)
    """
    transcription_jobs_in_progress.dec()

    transcription_duration_seconds.labels(
        status=status,
        source_type=source_type,
    ).observe(duration_seconds)

    if status != "success":
        transcription_errors_total.labels(
            error_type=status,
            source_type=source_type,
        ).inc()


def record_transcription_error(error_type: str, source_type: str) -> None:
    """Record a transcription error.

    Args:
        error_type: Type of error
        source_type: Type of source
    """
    transcription_errors_total.labels(
        error_type=error_type,
        source_type=source_type,
    ).inc()
    transcription_jobs_in_progress.dec()


def record_mongodb_operation(
    operation: str,
    collection: str,
    duration_seconds: float,
    status: str = "success",
) -> None:
    """Record a MongoDB operation.

    Args:
        operation: Operation type (find, insert, update, delete)
        collection: Collection name
        duration_seconds: Operation duration
        status: Operation status
    """
    mongodb_operations_total.labels(
        operation=operation,
        collection=collection,
        status=status,
    ).inc()

    mongodb_operation_duration_seconds.labels(
        operation=operation,
        collection=collection,
    ).observe(duration_seconds)


def record_redis_operation(
    operation: str,
    duration_seconds: float,
    status: str = "success",
) -> None:
    """Record a Redis operation.

    Args:
        operation: Operation type (get, set, delete, etc.)
        duration_seconds: Operation duration
        status: Operation status
    """
    redis_operations_total.labels(
        operation=operation,
        status=status,
    ).inc()

    redis_operation_duration_seconds.labels(
        operation=operation,
    ).observe(duration_seconds)


# Import os at module level for metrics endpoint
import os

__all__ = [
    "setup_prometheus",
    "PrometheusMiddleware",
    "record_transcription_job_start",
    "record_transcription_job_complete",
    "record_transcription_error",
    "record_mongodb_operation",
    "record_redis_operation",
    # Export metrics for external use
    "transcription_jobs_total",
    "transcription_jobs_in_progress",
    "transcription_duration_seconds",
    "transcription_errors_total",
    "api_requests_total",
    "api_request_duration_seconds",
    "mongodb_operations_total",
    "mongodb_operation_duration_seconds",
    "redis_operations_total",
    "redis_operation_duration_seconds",
    "app_info",
]
