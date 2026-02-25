"""Error handler middleware for standardized error responses.

This middleware catches all unhandled exceptions and converts them to
standardized ErrorResponse format with proper HTTP status codes.
"""

import logging
import traceback
import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.api.models.errors import (
    ErrorCodes,
    ErrorResponse,
    InternalServerErrorResponse,
    NotFoundErrorResponse,
    ValidationErrorResponse,
)

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware:
    """Global error handler for the FastAPI application.

    This middleware:
    - Catches all unhandled exceptions
    - Converts them to standardized ErrorResponse format
    - Logs errors with request context
    - Returns appropriate HTTP status codes

    Usage:
        app = FastAPI()
        setup_error_handler(app)
    """

    def __init__(self, app: FastAPI) -> None:
        """Initialize error handler middleware.

        Args:
            app: FastAPI application instance
        """
        self.app = app
        self._register_exception_handlers()

    def _register_exception_handlers(self) -> None:
        """Register exception handlers for different exception types."""
        # HTTP exceptions (including 404, 400, etc.)
        self.app.add_exception_handler(Exception, self._handle_generic_exception)
        self.app.add_exception_handler(RequestValidationError, self._handle_validation_error)
        self.app.add_exception_handler(ValidationError, self._handle_validation_error)
        self.app.add_exception_handler(
            status.HTTP_404_NOT_FOUND,  # type: ignore[arg-type]
            self._handle_http_exception,
        )

    async def _handle_generic_exception(
        self,
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle generic unhandled exceptions.

        Args:
            request: FastAPI request object
            exc: The exception that was raised

        Returns:
            JSONResponse with standardized error format
        """
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Log the full traceback for debugging
        logger.exception(
            "Unhandled exception",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else "unknown",
            },
        )

        # In production, don't leak internal error details
        error_response = InternalServerErrorResponse(
            request_id=request_id,
            details={"error_type": type(exc).__name__} if __debug__ else None,
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.model_dump(),
        )

    async def _handle_validation_error(
        self,
        request: Request,
        exc: RequestValidationError | ValidationError,
    ) -> JSONResponse:
        """Handle validation errors from request parsing.

        Args:
            request: FastAPI request object
            exc: Validation exception

        Returns:
            JSONResponse with validation error details
        """
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Extract validation errors
        errors: list[dict[str, Any]] = []
        if isinstance(exc, RequestValidationError):
            for error in exc.errors():
                errors.append(
                    {
                        "field": ".".join(str(loc) for loc in error["loc"]),
                        "message": error["msg"],
                        "type": error["type"],
                    }
                )
        elif isinstance(exc, ValidationError):
            for error in exc.errors():
                errors.append(
                    {
                        "field": ".".join(str(loc) for loc in error["loc"]),
                        "message": error["msg"],
                        "type": error["type"],
                    }
                )

        error_response = ValidationErrorResponse(
            error_code=ErrorCodes.VALIDATION_ERROR,
            message="Request validation failed",
            details={"errors": errors},
            request_id=request_id,
        )

        logger.info(
            "Validation error",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "validation_errors": errors,
            },
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response.model_dump(),
        )

    async def _handle_http_exception(
        self,
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle HTTP exceptions (404, 400, etc.).

        Args:
            request: FastAPI request object
            exc: HTTP exception

        Returns:
            JSONResponse with appropriate error format
        """
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Get status code from exception if available
        status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
        detail = getattr(exc, "detail", str(exc))

        # Map status codes to error codes
        if status_code == status.HTTP_404_NOT_FOUND:
            error_code = ErrorCodes.NOT_FOUND
            error_type = "NOT_FOUND"
            error_response = NotFoundErrorResponse(
                error_code=error_code,
                message=detail,
                request_id=request_id,
            )
        elif status_code == status.HTTP_400_BAD_REQUEST:
            error_code = ErrorCodes.INVALID_PARAMETER
            error_type = "BAD_REQUEST"
            error_response = ErrorResponse(
                error=error_type,
                error_code=error_code,
                message=detail,
                request_id=request_id,
            )
        elif status_code == status.HTTP_401_UNAUTHORIZED:
            error_code = ErrorCodes.AUTHENTICATION_ERROR
            error_type = "UNAUTHORIZED"
            error_response = ErrorResponse(
                error=error_type,
                error_code=error_code,
                message=detail,
                request_id=request_id,
            )
        elif status_code == status.HTTP_403_FORBIDDEN:
            error_code = ErrorCodes.AUTHENTICATION_ERROR
            error_type = "FORBIDDEN"
            error_response = ErrorResponse(
                error=error_type,
                error_code=error_code,
                message=detail,
                request_id=request_id,
            )
        elif status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            error_code = ErrorCodes.RATE_LIMIT_EXCEEDED
            error_type = "RATE_LIMIT_EXCEEDED"
            error_response = ErrorResponse(
                error=error_type,
                error_code=error_code,
                message=detail,
                request_id=request_id,
            )
        else:
            error_type = "HTTP_ERROR"
            error_response = ErrorResponse(
                error=error_type,
                error_code=f"HTTP_{status_code}",
                message=detail,
                request_id=request_id,
            )

        logger.info(
            f"HTTP {status_code} error",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
            },
        )

        return JSONResponse(
            status_code=status_code,
            content=error_response.model_dump(),
        )


def setup_error_handler(app: FastAPI) -> None:
    """Set up error handler middleware for the application.

    This function registers global exception handlers that convert
    all exceptions to standardized ErrorResponse format.

    Args:
        app: FastAPI application instance

    Example:
        from fastapi import FastAPI
        from src.api.middleware import setup_error_handler

        app = FastAPI()
        setup_error_handler(app)
    """
    ErrorHandlerMiddleware(app)
    logger.info("Error handler middleware initialized")
