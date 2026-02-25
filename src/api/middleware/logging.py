"""Logging middleware for request/response tracking.

This middleware adds request IDs to all requests and logs:
- Request details (method, path, headers, client IP)
- Response details (status code, response time)
- Performance metrics
"""

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Context variable for request ID (thread-safe)
REQUEST_ID_HEADER = "X-Request-ID"


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured request/response logging.

    Features:
    - Adds unique request ID to each request
    - Logs request details at INFO level
    - Logs response status and timing
    - Supports correlation IDs from upstream services

    Usage:
        app = FastAPI()
        app.add_middleware(LoggingMiddleware)
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and log details.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            HTTP response with request ID header
        """
        # Get or generate request ID
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())

        # Store request ID in state for access in route handlers
        request.state.request_id = request_id

        # Extract request details
        method = request.method
        path = request.url.path
        query = str(request.url.query) if request.url.query else ""
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Log request
        start_time = time.perf_counter()
        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "query": query,
                "client_ip": client_ip,
                "user_agent": user_agent,
            },
        )

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Add request ID to response headers
            response.headers[REQUEST_ID_HEADER] = request_id

            # Log response
            log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
            logger.log(
                log_level,
                "Request completed",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "client_ip": client_ip,
                },
            )

            return response

        except Exception as exc:
            # Calculate duration even for errors
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "Request failed",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "duration_ms": round(duration_ms, 2),
                    "client_ip": client_ip,
                    "error_type": type(exc).__name__,
                },
            )
            raise


def setup_logging_middleware(app: FastAPI) -> None:
    """Set up logging middleware for the application.

    Args:
        app: FastAPI application instance

    Example:
        from fastapi import FastAPI
        from src.api.middleware import setup_logging_middleware

        app = FastAPI()
        setup_logging_middleware(app)
    """
    app.add_middleware(LoggingMiddleware)
    logger.info("Logging middleware initialized")


def get_request_id(request: Request) -> str:
    """Get request ID from request state or headers.

    Args:
        request: FastAPI request object

    Returns:
        Request ID string
    """
    return getattr(request.state, "request_id", None) or request.headers.get(
        REQUEST_ID_HEADER,
        str(uuid.uuid4()),
    )
