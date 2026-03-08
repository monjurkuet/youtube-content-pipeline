"""Main FastAPI application for Transcription Pipeline API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware.error_handler import setup_error_handler
from src.api.routers import (
    channels_router,
    health_router,
    stats_router,
    transcripts_router,
    videos_router,
)
from src.core.config import get_settings
from src.database import get_db_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    get_settings()  # Initialize settings
    db_manager = get_db_manager()

    # Initialize database indexes
    await db_manager.init_indexes()

    yield

    # Shutdown
    await db_manager.close()


app = FastAPI(
    title="YouTube Content Pipeline API",
    description="REST API for video transcription and transcript management",
    version="0.5.0",
    lifespan=lifespan,
)

# Setup error handler
setup_error_handler(app)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(videos_router, prefix="/api/v1")
app.include_router(transcripts_router, prefix="/api/v1")
app.include_router(channels_router, prefix="/api/v1")
app.include_router(stats_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")


@app.get(
    "/health",
    response_model=dict[str, str],
    summary="Health check",
    description="Check API health status.",
)
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status dictionary
    """
    return {"status": "healthy", "service": "transcription-pipeline-api"}


@app.get(
    "/",
    response_model=dict[str, str],
    summary="API info",
    description="Get basic API information.",
)
async def root() -> dict[str, str]:
    """Root endpoint.

    Returns:
        API information
    """
    return {
        "name": "Transcription Pipeline API",
        "version": "0.4.0",
        "docs": "/docs",
    }
