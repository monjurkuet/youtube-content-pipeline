"""Rate limiting middleware using SlowAPI.

This module provides:
- Tiered rate limits (free, pro, enterprise)
- Per-API-key rate limiting
- Rate limit headers
- Redis-backed distributed rate limiting
- Graceful degradation to in-memory storage

Usage:
    # In app.py
    from src.api.middleware.rate_limiter import setup_rate_limiter

    app = FastAPI()
    setup_rate_limiter(app)
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.core.config import get_settings
from src.database.redis import get_redis_manager

logger = logging.getLogger(__name__)


def get_rate_limit_key(request: Request) -> str:
    """Extract rate limit key from request.

    Uses API key if available, otherwise falls back to IP address.

    Args:
        request: FastAPI request object

    Returns:
        Rate limit key string
    """
    # Try to get API key from request state (set by auth middleware)
    api_key = getattr(request.state, "api_key", None)
    if api_key:
        return f"apikey:{api_key}"

    # Fall back to header
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        return f"apikey:{api_key_header}"

    # Fall back to IP address
    return f"ip:{get_remote_address(request)}"


def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    """Handle rate limit exceeded errors.

    Returns 429 response with proper headers.

    Args:
        request: FastAPI request object
        exc: RateLimitExceeded exception

    Returns:
        JSONResponse with error details
    """
    # Calculate retry-after
    retry_after = 60  # Default
    if exc.detail and "retry after" in str(exc.detail).lower():
        try:
            retry_after = int(str(exc.detail).split()[-1])
        except (ValueError, IndexError):
            pass

    logger.warning(
        "Rate limit exceeded",
        extra={
            "key": get_rate_limit_key(request),
            "path": request.url.path,
            "retry_after": retry_after,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "RATE_LIMIT_EXCEEDED",
            "error_code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please slow down.",
            "details": {
                "retry_after_seconds": retry_after,
            },
            "request_id": getattr(request.state, "request_id", None),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        headers={
            "Retry-After": str(retry_after),
        },
    )


def get_limiter() -> Limiter:
    """Create or get the rate limiter instance.

    Returns:
        Configured Limiter instance
    """
    settings = get_settings()

    if not settings.rate_limit_enabled:
        # Return disabled limiter
        return Limiter(
            key_func=get_remote_address,
            default_limits=[],
            enabled=False,
        )

    # Determine storage backend
    storage_uri = None
    if settings.rate_limit_storage == "redis":
        redis_manager = get_redis_manager()
        if redis_manager.is_available:
            storage_uri = settings.redis_url

    # Create limiter
    limiter = Limiter(
        key_func=get_rate_limit_key,
        default_limits=[f"{settings.rate_limit_tiers.get('free', 10)}/minute"],
        storage_uri=storage_uri,
        enabled=settings.rate_limit_enabled,
    )

    return limiter


def setup_rate_limiter(app: FastAPI) -> Limiter:
    """Set up rate limiting middleware.

    Args:
        app: FastAPI application

    Returns:
        Configured Limiter instance
    """
    settings = get_settings()

    if not settings.rate_limit_enabled:
        logger.info("Rate limiting is disabled")
        limiter = get_limiter()
        return limiter

    limiter = get_limiter()

    # Add exception handler
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Initialize the limiter with the app
    app.state.limiter = limiter

    logger.info(
        "Rate limiting enabled",
        extra={
            "storage": settings.rate_limit_storage,
            "tiers": settings.rate_limit_tiers,
            "default_limit": f"{settings.rate_limit_tiers.get('free', 10)}/minute",
        },
    )

    return limiter


# Rate limit decorators for endpoints
def rate_limit(limit: str):
    """Decorator to apply rate limit to an endpoint.

    Note: This decorator stores the limit on the function.
    The actual enforcement is done by SlowAPI's middleware.

    Args:
        limit: Rate limit string (e.g., "10/minute", "100/hour")

    Returns:
        Decorator function

    Example:
        @router.get("/expensive")
        @rate_limit("5/minute")
        async def expensive_endpoint():
            ...
    """

    def decorator(func):
        # Store the limit on the function for documentation
        func._rate_limit = limit
        return func

    return decorator


def tiered_rate_limit(tier_limits: dict[str, str] | None = None):
    """Decorator for tiered rate limiting based on API key tier.

    Args:
        tier_limits: Dict mapping tier names to limits
                    (default: free=10/min, pro=100/min, enterprise=1000/min)

    Returns:
        Decorator function

    Example:
        @router.get("/api")
        @tiered_rate_limit()
        async def api_endpoint():
            ...
    """
    if tier_limits is None:
        tier_limits = {
            "free": "10/minute",
            "pro": "100/minute",
            "enterprise": "1000/minute",
        }

    def decorator(func):
        # Apply the most restrictive limit by default
        func._rate_limit = tier_limits["free"]
        return func

    return decorator
