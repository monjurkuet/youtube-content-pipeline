"""Main FastAPI application with enhanced OpenAPI schema.

This module creates the FastAPI application with:
- Custom OpenAPI schema with security schemes
- Comprehensive API documentation
- Middleware for error handling and logging
- Health check and info endpoints
- Redis integration
- Rate limiting
- Prometheus metrics
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.middleware import (
    setup_error_handler,
    setup_logging_middleware,
    setup_prometheus,
    setup_rate_limiter,
)
from src.api.routers import channels_router, health_router, stats_router, transcripts_router, videos_router
from src.core.config import get_settings
from src.core.constants import (
    API_TAGS,
    APP_DESCRIPTION,
    APP_NAME,
    APP_VERSION,
    CONTACT_INFO,
    EXTERNAL_DOCS,
    LICENSE_INFO,
    OPENAPI_TITLE,
    OPENAPI_VERSION,
)
from src.database import get_db_manager
from src.database.redis import close_redis, init_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events including:
    - Settings initialization
    - Database connection and index creation
    - Redis connection
    - Cleanup on shutdown

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Startup
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)

    settings = get_settings()
    db_manager = get_db_manager(force_reload=True)
    redis_manager = None

    # Initialize database (graceful degradation on failure)
    try:
        await db_manager.init_indexes()
        logger.info("Database indexes initialized")
    except Exception as e:
        logger.warning("Database initialization failed (degraded mode): %s", e)

    # Initialize Redis (optional, graceful degradation)
    try:
        if settings.redis_enabled:
            redis_manager = await init_redis(force_reload=True)
            if redis_manager.is_available:
                logger.info("Redis connection established")
            else:
                error_msg = (
                    "Redis unavailable. Job storage will use in-memory fallback. "
                    "Set REDIS_STRICT_MODE=true to fail startup if Redis is required."
                )
                if settings.redis_strict_mode:
                    logger.error(
                        "Redis strict mode enabled but Redis is unavailable. "
                        "Cannot start application."
                    )
                    raise RuntimeError(
                        "Redis is required but unavailable. "
                        "Either start Redis or set REDIS_STRICT_MODE=false."
                    )
                logger.warning(error_msg)
        else:
            logger.info("Redis disabled in configuration")
    except Exception as e:
        if settings.redis_strict_mode:
            logger.error("Redis initialization failed in strict mode: %s", e)
            raise RuntimeError(f"Redis initialization failed: {e}") from e
        logger.warning("Redis initialization failed (degraded mode): %s", e)

    try:
        yield

    finally:
        # Shutdown
        logger.info("Shutting down %s", APP_NAME)

        # Close Redis
        if settings.redis_enabled:
            try:
                await close_redis()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.warning("Error closing Redis: %s", e)

        # Close database
        try:
            await db_manager.close()
            logger.info("Database connection closed")
        except Exception as e:
            logger.warning("Error closing database: %s", e)


def create_openapi_schema(
    app_instance: FastAPI | None = None,
    original_openapi: Any = None,
) -> dict[str, Any]:
    """Create custom OpenAPI schema with enhanced documentation.

    Args:
        app_instance: Optional FastAPI instance to get paths from
        original_openapi: The original FastAPI openapi method to avoid recursion

    Returns:
        OpenAPI schema dictionary
    """
    schema = {
        "openapi": "3.1.0",
        "info": {
            "title": OPENAPI_TITLE,
            "description": APP_DESCRIPTION,
            "version": OPENAPI_VERSION,
            "contact": CONTACT_INFO,
            "license": LICENSE_INFO,
        },
        "servers": [
            {
                "url": "/",
                "description": "API v1 - Current stable version",
            },
            {
                "url": "http://localhost:8000",
                "description": "Local development server",
            },
        ],
        "tags": API_TAGS,
        "externalDocs": EXTERNAL_DOCS,
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "API key for authentication. Required for protected endpoints.",
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "JWT bearer token for authentication.",
                },
            },
            "schemas": {
                "ErrorResponse": {
                    "type": "object",
                    "required": ["error", "error_code", "message", "request_id", "timestamp"],
                    "properties": {
                        "error": {
                            "type": "string",
                            "description": "Error type identifier",
                            "example": "VALIDATION_ERROR",
                        },
                        "error_code": {
                            "type": "string",
                            "description": "Machine-readable error code",
                            "example": "INVALID_VIDEO_ID",
                        },
                        "message": {
                            "type": "string",
                            "description": "Human-readable error message",
                            "example": "The provided video ID is invalid",
                        },
                        "details": {
                            "type": "object",
                            "description": "Additional error details",
                            "nullable": True,
                        },
                        "request_id": {
                            "type": "string",
                            "description": "Unique request identifier for tracing",
                            "example": "req_abc123def456",
                        },
                        "timestamp": {
                            "type": "string",
                            "format": "date-time",
                            "description": "ISO 8601 timestamp of error",
                        },
                    },
                },
                "ValidationError": {
                    "allOf": [
                        {"$ref": "#/components/schemas/ErrorResponse"},
                        {
                            "type": "object",
                            "properties": {
                                "error": {"const": "VALIDATION_ERROR"},
                                "details": {
                                    "type": "object",
                                    "properties": {
                                        "errors": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "field": {"type": "string"},
                                                    "message": {"type": "string"},
                                                    "type": {"type": "string"},
                                                },
                                            },
                                        }
                                    },
                                },
                            },
                        },
                    ],
                },
            },
            "responses": {
                "422ValidationError": {
                    "description": "Validation Error",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ValidationError"},
                        }
                    },
                },
                "500InternalServerError": {
                    "description": "Internal Server Error",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                        }
                    },
                },
            },
        },
        "security": [{"ApiKeyAuth": []}],
    }

    # Add paths from app instance if provided
    if app_instance is not None and original_openapi is not None:
        # Get the auto-generated paths from FastAPI's original openapi method
        schema["paths"] = original_openapi().get("paths", {})

    return schema


def create_app(force_reload: bool = False) -> FastAPI:
    """Create and configure the FastAPI application.

    This factory function creates a new FastAPI application with:
    - Custom OpenAPI schema
    - CORS middleware (all origins allowed for development)
    - Error handling middleware
    - Logging middleware
    - Rate limiting middleware
    - Prometheus metrics
    - All routers

    Args:
        force_reload: Whether to force reloading settings and middleware

    Returns:
        Configured FastAPI application
    """
    settings = get_settings(force_reload=force_reload)
    
    # Reset Redis manager if needed (to avoid loop conflicts in tests)
    from src.database.redis import get_redis_manager
    get_redis_manager(force_reload=force_reload)

    # Reset API key validator if needed
    from src.api.security import get_api_key_validator
    get_api_key_validator(force_reload=force_reload)

    app = FastAPI(
        title=APP_NAME,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Custom OpenAPI schema (with paths from routers)
    # Save original openapi method before overwriting to avoid recursion
    _original_openapi = app.openapi
    app.openapi = lambda: create_openapi_schema(app, _original_openapi)  # type: ignore[method-assign]

    # Add CORS middleware (all origins for development)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add logging middleware
    setup_logging_middleware(app)

    # Add error handler middleware
    setup_error_handler(app)

    # Add rate limiting middleware
    setup_rate_limiter(app, force_reload=force_reload)

    # Add Prometheus metrics
    setup_prometheus(app)

    # Include routers
    from src.api.security import validate_api_key
    from fastapi import Depends

    app.include_router(
        videos_router, 
        prefix="/api/v1",
        dependencies=[Depends(validate_api_key)]
    )
    app.include_router(
        transcripts_router, 
        prefix="/api/v1",
        dependencies=[Depends(validate_api_key)]
    )
    app.include_router(
        channels_router, 
        prefix="/api/v1",
        dependencies=[Depends(validate_api_key)]
    )
    app.include_router(
        stats_router, 
        prefix="/api/v1",
        dependencies=[Depends(validate_api_key)]
    )
    # Health endpoints are usually public, but tests expect them to be protected 
    # if AUTH_REQUIRE_KEY is true. validate_api_key handles this check internally.
    app.include_router(
        health_router,
        dependencies=[Depends(validate_api_key)]
    )

    logger.info("Application created successfully")
    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
