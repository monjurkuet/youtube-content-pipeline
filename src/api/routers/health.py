"""Health check endpoints for monitoring and observability.

This module provides comprehensive health endpoints:
- GET /health - Basic liveness probe
- GET /health/ready - Readiness probe (checks dependencies)
- GET /health/live - Liveness probe (always returns 200 if running)
- GET /health/detailed - Detailed status with component health

Usage:
    # Include in app.py
    from src.api.routers import health_router
    app.include_router(health_router)
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.database import get_db_manager
from src.database.redis import get_redis_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


def get_version_info() -> dict[str, str]:
    """Get application version information.

    Returns:
        Version info dictionary
    """
    from src.core.constants import APP_VERSION

    return {
        "version": APP_VERSION,
        "python_version": "3.12",
    }


async def check_database_health() -> dict[str, Any]:
    """Check MongoDB health.

    Returns:
        Health status dictionary
    """
    result = {
        "status": "unhealthy",
        "latency_ms": 0,
        "available": False,
    }

    db_manager = get_db_manager()

    try:
        start = time.perf_counter()

        # Check connection
        client = db_manager.client
        if client is None:
            result["status"] = "unhealthy"
            result["error"] = "No database client"
            return result

        # Ping database
        await client.admin.command("ping")

        latency = (time.perf_counter() - start) * 1000

        result["status"] = "healthy"
        result["latency_ms"] = round(latency, 2)
        result["available"] = True

    except Exception as e:
        result["status"] = "unhealthy"
        result["error"] = str(e)
        logger.warning("Database health check failed: %s", e)

    return result


async def check_redis_health() -> dict[str, Any]:
    """Check Redis health.

    Returns:
        Health status dictionary
    """
    redis_manager = get_redis_manager()
    return await redis_manager.health_check()


async def check_transcription_health() -> dict[str, Any]:
    """Check transcription service health.

    Returns:
        Health status dictionary
    """
    result = {
        "status": "healthy",
        "available": True,
    }

    # Check if transcription dependencies are available
    try:
        # Try to import transcription handler
        from src.transcription.handler import TranscriptionHandler

        # Basic check - just verify it can be instantiated
        handler = TranscriptionHandler()
        result["handler_available"] = True

    except Exception as e:
        result["status"] = "degraded"
        result["error"] = str(e)
        result["available"] = False
        logger.warning("Transcription health check warning: %s", e)

    return result


@router.get(
    "/health",
    response_model=dict[str, Any],
    summary="Basic health check",
    description="Quick health check for load balancers. Returns 200 if API is responding.",
    operation_id="health_check",
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "version": "0.5.0",
                        "timestamp": "2024-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
async def health_check() -> JSONResponse:
    """Basic health check endpoint.

    Returns 200 if the API is responding. Does not check dependencies.
    Suitable for load balancer health checks.

    Returns:
        JSONResponse with health status
    """
    version_info = get_version_info()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "version": version_info["version"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get(
    "/health/live",
    response_model=dict[str, Any],
    summary="Liveness probe",
    description="Kubernetes liveness probe. Returns 200 if process is running.",
    operation_id="liveness_probe",
    responses={
        200: {
            "description": "Process is alive",
        }
    },
)
async def liveness_probe() -> JSONResponse:
    """Liveness probe endpoint.

    Returns 200 if the process is running. Kubernetes uses this to determine
    if the container should be restarted.

    Returns:
        JSONResponse with alive status
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get(
    "/health/ready",
    response_model=dict[str, Any],
    summary="Readiness probe",
    description="Kubernetes readiness probe. Checks if service is ready to accept traffic.",
    operation_id="readiness_probe",
    responses={
        200: {
            "description": "Service is ready",
        },
        503: {
            "description": "Service is not ready",
        },
    },
)
async def readiness_probe() -> JSONResponse:
    """Readiness probe endpoint.

    Checks if all required dependencies are available. Kubernetes uses this
    to determine if the pod should receive traffic.

    Returns:
        JSONResponse with readiness status
    """
    settings = get_settings()
    version_info = get_version_info()

    # Check required components
    db_health = await check_database_health()

    components = {
        "api": {"status": "healthy", "latency_ms": 1},
        "database": db_health,
    }

    # Check Redis if enabled
    if settings.redis_enabled:
        redis_health = await check_redis_health()
        components["redis"] = redis_health

    # Determine overall status
    all_healthy = all(comp.get("status") == "healthy" for comp in components.values())

    any_available = any(comp.get("available", False) for comp in components.values())

    if all_healthy:
        overall_status = "healthy"
        status_code = status.HTTP_200_OK
    elif any_available:
        overall_status = "degraded"
        status_code = status.HTTP_200_OK  # Still accept traffic in degraded mode
    else:
        overall_status = "unhealthy"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "version": version_info["version"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": components,
        },
    )


@router.get(
    "/health/detailed",
    response_model=dict[str, Any],
    summary="Detailed health check",
    description="Comprehensive health check with all component details.",
    operation_id="detailed_health_check",
    responses={
        200: {
            "description": "Detailed health status",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "version": "0.5.0",
                        "timestamp": "2024-01-01T00:00:00Z",
                        "components": {
                            "api": {"status": "healthy", "latency_ms": 1},
                            "database": {"status": "healthy", "latency_ms": 5},
                            "redis": {"status": "healthy", "latency_ms": 2},
                            "transcription": {"status": "healthy"},
                        },
                        "uptime_seconds": 3600,
                    }
                }
            },
        }
    },
)
async def detailed_health_check() -> JSONResponse:
    """Detailed health check endpoint.

    Returns comprehensive health information including all components.
    Useful for monitoring dashboards and debugging.

    Returns:
        JSONResponse with detailed health status
    """
    settings = get_settings()
    version_info = get_version_info()

    # Check all components
    db_health = await check_database_health()
    transcription_health = await check_transcription_health()

    components: dict[str, Any] = {
        "api": {"status": "healthy", "latency_ms": 1},
        "database": db_health,
        "transcription": transcription_health,
    }

    # Check Redis if enabled
    if settings.redis_enabled:
        redis_health = await check_redis_health()
        components["redis"] = redis_health

    # Determine overall status
    statuses = [comp.get("status") for comp in components.values()]

    if all(s == "healthy" for s in statuses):
        overall_status = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"

    # Calculate uptime
    from src.core.constants import START_TIME

    uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": overall_status,
            "version": version_info["version"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": components,
            "uptime_seconds": round(uptime, 2),
            "environment": {
                "redis_enabled": settings.redis_enabled,
                "rate_limit_enabled": settings.rate_limit_enabled,
                "prometheus_enabled": settings.prometheus_enabled,
            },
        },
    )
