"""Tests for Redis integration.

These tests verify:
- Redis connection and health checks
- Job storage operations
- Graceful degradation when Redis is unavailable
"""

import asyncio
import pytest
from datetime import datetime, timezone

from src.database.redis import RedisManager, get_redis_manager


@pytest.fixture
def redis_manager():
    """Create a Redis manager instance for testing."""
    return RedisManager(
        redis_url="redis://localhost:6379",
        redis_db=15,  # Use DB 15 for tests
        key_prefix="test",
        default_ttl=60,
    )


@pytest.mark.asyncio
async def test_redis_connection(redis_manager):
    """Test Redis connection."""
    # Try to connect
    connected = await redis_manager.connect()

    # Connection may fail if Redis is not running
    # Test should pass either way (graceful degradation)
    if connected:
        assert redis_manager.is_available
        await redis_manager.disconnect()
    else:
        assert not redis_manager.is_available


@pytest.mark.asyncio
async def test_redis_health_check(redis_manager):
    """Test Redis health check."""
    await redis_manager.connect()
    health = await redis_manager.health_check()

    # Health check should always return a valid response
    assert "status" in health
    assert "latency_ms" in health
    assert "available" in health

    if redis_manager.is_available:
        assert health["status"] == "healthy"
        assert health["available"] is True
        assert health["latency_ms"] >= 0
    else:
        assert health["status"] in ["unhealthy", "degraded"]
        assert health["available"] is False

    await redis_manager.disconnect()


@pytest.mark.asyncio
async def test_job_storage(redis_manager):
    """Test job storage operations."""
    await redis_manager.connect()

    if not redis_manager.is_available:
        pytest.skip("Redis not available")

    try:
        job_id = "test_job_123"
        job_data = {
            "job_id": job_id,
            "status": "processing",
            "progress_percent": 50.0,
            "created_at": datetime.now(timezone.utc),
        }

        # Set job
        result = await redis_manager.set_job(job_id, job_data)
        assert result is True

        # Get job
        retrieved = await redis_manager.get_job(job_id)
        assert retrieved is not None
        assert retrieved["job_id"] == job_id
        assert retrieved["status"] == "processing"

        # Update job
        update_result = await redis_manager.update_job(
            job_id,
            {"status": "completed", "progress_percent": 100.0},
        )
        assert update_result is True

        # Verify update
        updated = await redis_manager.get_job(job_id)
        assert updated["status"] == "completed"
        assert updated["progress_percent"] == 100.0

        # Delete job
        delete_result = await redis_manager.delete_job(job_id)
        assert delete_result is True

        # Verify deletion
        deleted = await redis_manager.get_job(job_id)
        assert deleted is None

    finally:
        await redis_manager.disconnect()


@pytest.mark.asyncio
async def test_job_ttl(redis_manager):
    """Test job TTL (time-to-live)."""
    await redis_manager.connect()

    if not redis_manager.is_available:
        pytest.skip("Redis not available")

    try:
        job_id = "test_job_ttl"
        job_data = {"job_id": job_id, "status": "queued"}

        # Set job with short TTL
        result = await redis_manager.set_job(job_id, job_data, ttl=2)
        assert result is True

        # Verify job exists
        retrieved = await redis_manager.get_job(job_id)
        assert retrieved is not None

        # Wait for TTL to expire
        await asyncio.sleep(3)

        # Verify job expired
        expired = await redis_manager.get_job(job_id)
        assert expired is None

    finally:
        await redis_manager.disconnect()


@pytest.mark.asyncio
async def test_list_jobs(redis_manager):
    """Test listing jobs."""
    await redis_manager.connect()

    if not redis_manager.is_available:
        pytest.skip("Redis not available")

    try:
        # Create test jobs
        for i in range(5):
            job_id = f"test_job_list_{i}"
            job_data = {
                "job_id": job_id,
                "status": "completed" if i % 2 == 0 else "processing",
                "created_at": datetime.now(timezone.utc),
            }
            await redis_manager.set_job(job_id, job_data)

        # List all jobs
        jobs = await redis_manager.list_jobs(limit=10)
        assert len(jobs) >= 5

        # List with status filter
        completed_jobs = await redis_manager.list_jobs(
            limit=10,
            status_filter="completed",
        )
        assert all(j["status"] == "completed" for j in completed_jobs)

        # Clean up
        for i in range(5):
            await redis_manager.delete_job(f"test_job_list_{i}")

    finally:
        await redis_manager.disconnect()


@pytest.mark.asyncio
async def test_graceful_degradation():
    """Test graceful degradation when Redis is unavailable."""
    # Create manager with invalid Redis URL
    manager = RedisManager(
        redis_url="redis://invalid-host:6379",
        key_prefix="test",
    )

    # Connection should fail gracefully
    connected = await manager.connect()
    assert connected is False
    assert not manager.is_available

    # Operations should return safely
    result = await manager.set_job("test", {"data": "value"})
    assert result is False

    retrieved = await manager.get_job("test")
    assert retrieved is None


@pytest.mark.asyncio
async def test_rate_limit_operations(redis_manager):
    """Test rate limit counter operations."""
    await redis_manager.connect()

    if not redis_manager.is_available:
        pytest.skip("Redis not available")

    try:
        key = "test_rate_limit"

        # Increment counter
        count = await redis_manager.incr_rate_limit(key, window_seconds=60)
        assert count == 1

        # Increment again
        count = await redis_manager.incr_rate_limit(key, window_seconds=60)
        assert count == 2

        # Get count
        retrieved = await redis_manager.get_rate_limit_count(key)
        assert retrieved == 2

    finally:
        await redis_manager.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
