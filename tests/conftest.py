"""Pytest fixtures and configuration for integration tests.

This module provides:
- Test client for FastAPI
- Test database connection
- Test Redis connection
- API key fixtures
- Sample data fixtures
- Mock utilities
"""

import asyncio
import os
import pytest
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.api.app import create_app
from src.api.security import generate_api_key, hash_api_key
from src.database.manager import MongoDBManager
from src.database.redis import RedisManager


# =============================================================================
# Test Configuration
# =============================================================================

TEST_DB_NAME = "test_youtube_transcription"
TEST_REDIS_DB = 15
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379")
TEST_MONGODB_URL = os.getenv("TEST_MONGODB_URL", "mongodb://localhost:27017")


# =============================================================================
# Application Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests.

    Yields:
        asyncio event loop
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def app() -> FastAPI:
    """Create FastAPI application for testing.

    Returns:
        FastAPI application instance
    """
    # Override settings for testing
    with patch.dict(
        os.environ,
        {
            "MONGODB_DATABASE": TEST_DB_NAME,
            "REDIS_DB": str(TEST_REDIS_DB),
            "AUTH_REQUIRE_KEY": "false",  # Auth optional by default for tests
            "RATE_LIMIT_ENABLED": "false",  # Disable rate limiting for most tests
            "PROMETHEUS_ENABLED": "false",  # Disable Prometheus for tests
        },
        clear=False,
    ):
        test_app = create_app()
        yield test_app


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    """Create test client for FastAPI application.

    Args:
        app: FastAPI application

    Yields:
        TestClient instance
    """
    with TestClient(app, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def client_with_auth(app: FastAPI) -> Generator[TestClient, None, None]:
    """Create test client with authentication enabled.

    Args:
        app: FastAPI application

    Yields:
        TestClient instance with auth enabled
    """
    with patch.dict(
        os.environ,
        {
            "AUTH_REQUIRE_KEY": "true",
            "API_KEYS": "test-api-key-123,another-test-key",
        },
        clear=False,
    ):
        # Recreate app with auth enabled
        auth_app = create_app()
        with TestClient(auth_app, base_url="http://test") as test_client:
            yield test_client


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest.fixture
async def test_db() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """Create test MongoDB database connection.

    Yields:
        AsyncIOMotorDatabase instance
    """
    client = AsyncIOMotorClient(TEST_MONGODB_URL)
    db = client[TEST_DB_NAME]

    try:
        yield db
    finally:
        # Clean up test database
        await client.drop_database(TEST_DB_NAME)
        client.close()


@pytest.fixture
async def db_manager() -> AsyncGenerator[MongoDBManager, None]:
    """Create MongoDB manager for testing.

    Yields:
        MongoDBManager instance
    """
    manager = MongoDBManager()

    # Override MongoDB URL for testing
    with patch.dict(os.environ, {"MONGODB_URL": TEST_MONGODB_URL}, clear=False):
        try:
            await manager.initialize()
            await manager.init_indexes()
            yield manager
        finally:
            # Clean up
            if manager.client:
                await manager.client.drop_database(TEST_DB_NAME)
                await manager.close()


# =============================================================================
# Redis Fixtures
# =============================================================================


@pytest.fixture
async def test_redis() -> AsyncGenerator[RedisManager, None]:
    """Create test Redis connection.

    Yields:
        RedisManager instance
    """
    manager = RedisManager(
        redis_url=TEST_REDIS_URL,
        redis_db=TEST_REDIS_DB,
        key_prefix="test",
        default_ttl=60,
    )

    try:
        await manager.connect()
        if manager.is_available:
            # Clear test database
            await manager._redis.flushdb()
        yield manager
    finally:
        if manager.is_available:
            await manager._redis.flushdb()
        await manager.disconnect()


@pytest.fixture
async def redis_available(test_redis: RedisManager) -> bool:
    """Check if Redis is available for tests.

    Args:
        test_redis: RedisManager instance

    Returns:
        True if Redis is available
    """
    if not test_redis.is_available:
        pytest.skip("Redis not available")
    return True


# =============================================================================
# API Key Fixtures
# =============================================================================


@pytest.fixture
def valid_api_key() -> str:
    """Generate a valid API key for testing.

    Returns:
        Valid API key string
    """
    return generate_api_key()


@pytest.fixture
def invalid_api_key() -> str:
    """Generate an invalid API key for testing.

    Returns:
        Invalid API key string
    """
    return "invalid_key_" + generate_api_key()[:20]


@pytest.fixture
def api_key_headers(valid_api_key: str) -> dict[str, str]:
    """Create headers with valid API key.

    Args:
        valid_api_key: Valid API key

    Returns:
        Headers dictionary
    """
    return {"X-API-Key": valid_api_key}


@pytest.fixture
def invalid_api_key_headers(invalid_api_key: str) -> dict[str, str]:
    """Create headers with invalid API key.

    Args:
        invalid_api_key: Invalid API key

    Returns:
        Headers dictionary
    """
    return {"X-API-Key": invalid_api_key}


@pytest.fixture
def bearer_token_headers(valid_api_key: str) -> dict[str, str]:
    """Create Authorization header with bearer token.

    Args:
        valid_api_key: API key to use as bearer token

    Returns:
        Headers dictionary
    """
    return {"Authorization": f"Bearer {valid_api_key}"}


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_transcript() -> dict[str, Any]:
    """Create sample transcript data for testing.

    Returns:
        Sample transcript dictionary
    """
    return {
        "video_id": "test_video_123",
        "title": "Test Video Title",
        "channel_id": "UC_test_channel",
        "channel_name": "Test Channel",
        "duration_seconds": 120.5,
        "language": "en",
        "transcript_source": "youtube_auto",
        "segments": [
            {"start": 0.0, "end": 5.0, "text": "Hello, this is a test."},
            {"start": 5.0, "end": 10.0, "text": "This is the second segment."},
            {"start": 10.0, "end": 15.0, "text": "And this is the third segment."},
        ],
        "full_text": "Hello, this is a test. This is the second segment. And this is the third segment.",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_job() -> dict[str, Any]:
    """Create sample job data for testing.

    Returns:
        Sample job dictionary
    """
    return {
        "job_id": "test_job_123",
        "video_id": "test_video_123",
        "status": "queued",
        "progress_percent": 0.0,
        "current_step": "Queued for processing",
        "created_at": datetime.now(timezone.utc),
        "webhook_url": None,
        "save_to_db": True,
        "priority": "normal",
    }


@pytest.fixture
def sample_video_url() -> str:
    """Create sample YouTube video URL.

    Returns:
        Sample YouTube URL
    """
    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture
def sample_transcription_request() -> dict[str, Any]:
    """Create sample transcription request.

    Returns:
        Transcription request dictionary
    """
    return {
        "source": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "webhook_url": "https://example.com/webhook",
        "priority": "normal",
        "save_to_db": True,
    }


# =============================================================================
# Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_transcription_pipeline() -> MagicMock:
    """Mock the transcription pipeline.

    Returns:
        Mocked pipeline function
    """
    mock_result = MagicMock()
    mock_result.video_id = "mock_video_123"
    mock_result.transcript_source = "youtube_auto"
    mock_result.segment_count = 10
    mock_result.duration_seconds = 120.5

    with patch("src.api.routers.videos.get_transcript", return_value=mock_result) as mock:
        yield mock


@pytest.fixture
async def mock_db_manager() -> AsyncMock:
    """Mock database manager for testing.

    Returns:
        AsyncMock database manager
    """
    mock = AsyncMock(spec=MongoDBManager)
    mock.client = AsyncMock()
    mock.db = AsyncMock(spec=AsyncIOMotorDatabase)
    mock.transcripts = AsyncMock()
    mock.channels = AsyncMock()
    mock.video_metadata = AsyncMock()

    # Mock find_one to return None by default
    mock.transcripts.find_one = AsyncMock(return_value=None)
    mock.transcripts.find = MagicMock(return_value=AsyncMock())
    mock.transcripts.find.return_value.sort = MagicMock(return_value=AsyncMock())
    mock.transcripts.find.return_value.sort.return_value.skip = MagicMock(return_value=AsyncMock())
    mock.transcripts.find.return_value.sort.return_value.skip.return_value.limit = MagicMock(
        return_value=AsyncMock()
    )
    mock.transcripts.find.return_value.sort.return_value.skip.return_value.limit.return_value.__aiter__ = AsyncMock(
        return_value=iter([])
    )

    return mock


@pytest.fixture
def mock_redis_manager() -> AsyncMock:
    """Mock Redis manager for testing.

    Returns:
        AsyncMock Redis manager
    """
    mock = AsyncMock(spec=RedisManager)
    mock.is_available = True
    mock.get_job = AsyncMock(return_value=None)
    mock.set_job = AsyncMock(return_value=True)
    mock.update_job = AsyncMock(return_value=True)
    mock.delete_job = AsyncMock(return_value=True)
    mock.list_jobs = AsyncMock(return_value=[])
    mock.health_check = AsyncMock(
        return_value={"status": "healthy", "latency_ms": 1, "available": True}
    )
    return mock


# =============================================================================
# Utility Fixtures
# =============================================================================


@pytest.fixture
def clean_environment() -> Generator[None, None, None]:
    """Clean environment variables before and after test.

    Yields:
        None
    """
    # Store original environment
    original_env = os.environ.copy()

    try:
        yield
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


@pytest.fixture
def test_request_id() -> str:
    """Generate a test request ID.

    Returns:
        Test request ID string
    """
    return "test_req_123456"


# =============================================================================
# Test Markers and Skips
# =============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest markers.

    Args:
        config: Pytest configuration
    """
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "requires_redis: requires Redis to be running")
    config.addinivalue_line("markers", "requires_mongodb: requires MongoDB to be running")


# Note: Individual test files should handle their own dependency checks
# This allows tests to run with mocks when dependencies are unavailable
