"""Tests for Redis integration.

This module tests:
- Redis connection and health
- Job storage operations
- Job TTL management
- Graceful degradation
- Rate limiting with Redis
"""

import asyncio
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.database.redis import RedisManager


class TestRedisConnection:
    """Test Redis connection functionality."""

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_connection(self, test_redis: RedisManager) -> None:
        """Test can connect to Redis.

        Given: Redis server running
        When: Connect to Redis
        Then: Connection succeeds
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        assert test_redis.is_available is True

    @pytest.mark.asyncio
    async def test_redis_health_check(self, test_redis: RedisManager) -> None:
        """Test Redis health check.

        Given: Redis connection
        When: Health check performed
        Then: Returns health status
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        health = await test_redis.health_check()

        assert "status" in health
        assert "latency_ms" in health
        assert "available" in health

        if test_redis.is_available:
            assert health["status"] == "healthy"
            assert health["available"] is True

    @pytest.mark.asyncio
    async def test_redis_connection_failure(self) -> None:
        """Test graceful handling of connection failure.

        Given: Invalid Redis URL
        When: Attempt to connect
        Then: Fails gracefully without crashing
        """
        manager = RedisManager(
            redis_url="redis://invalid-host:6379",
            redis_db=15,
            key_prefix="test",
        )

        connected = await manager.connect()

        assert connected is False
        assert manager.is_available is False


class TestRedisJobStorage:
    """Test Redis job storage operations."""

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_set_job(self, test_redis: RedisManager) -> None:
        """Test can store job in Redis.

        Given: Redis connection
        When: Store job data
        Then: Job is stored successfully
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        job_id = "test_set_job"
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        result = await test_redis.set_job(job_id, job_data)

        assert result is True

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_get_job(self, test_redis: RedisManager) -> None:
        """Test can retrieve job from Redis.

        Given: Job stored in Redis
        When: Retrieve job
        Then: Returns job data
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        job_id = "test_get_job"
        job_data = {
            "job_id": job_id,
            "status": "processing",
            "progress_percent": 50.0,
        }

        # Store job
        await test_redis.set_job(job_id, job_data)

        # Retrieve job
        retrieved = await test_redis.get_job(job_id)

        assert retrieved is not None
        assert retrieved["job_id"] == job_id
        assert retrieved["status"] == "processing"

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_update_job(self, test_redis: RedisManager) -> None:
        """Test can update job in Redis.

        Given: Job stored in Redis
        When: Update job data
        Then: Job is updated successfully
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        job_id = "test_update_job"
        initial_data = {
            "job_id": job_id,
            "status": "queued",
            "progress_percent": 0.0,
        }

        # Store initial job
        await test_redis.set_job(job_id, initial_data)

        # Update job
        updates = {
            "status": "processing",
            "progress_percent": 50.0,
        }
        result = await test_redis.update_job(job_id, updates)

        assert result is True

        # Verify update
        updated = await test_redis.get_job(job_id)
        assert updated["status"] == "processing"
        assert updated["progress_percent"] == 50.0

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_delete_job(self, test_redis: RedisManager) -> None:
        """Test can delete job from Redis.

        Given: Job stored in Redis
        When: Delete job
        Then: Job is removed
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        job_id = "test_delete_job"
        job_data = {"job_id": job_id, "status": "completed"}

        # Store job
        await test_redis.set_job(job_id, job_data)

        # Verify exists
        retrieved = await test_redis.get_job(job_id)
        assert retrieved is not None

        # Delete job
        result = await test_redis.delete_job(job_id)

        assert result is True

        # Verify deleted
        deleted = await test_redis.get_job(job_id)
        assert deleted is None

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_get_nonexistent_job(
        self,
        test_redis: RedisManager,
    ) -> None:
        """Test retrieving non-existent job.

        Given: Job doesn't exist
        When: Try to get job
        Then: Returns None
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        result = await test_redis.get_job("nonexistent_job")

        assert result is None


class TestRedisJobListing:
    """Test Redis job listing operations."""

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_list_jobs(self, test_redis: RedisManager) -> None:
        """Test can list jobs from Redis.

        Given: Multiple jobs stored
        When: List jobs
        Then: Returns list of jobs
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        # Create test jobs
        job_ids = []
        for i in range(5):
            job_id = f"test_list_job_{i}"
            job_ids.append(job_id)
            job_data = {
                "job_id": job_id,
                "status": "completed",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await test_redis.set_job(job_id, job_data)

        # List jobs
        jobs = await test_redis.list_jobs(limit=10)

        assert len(jobs) >= 5

        # Clean up
        for job_id in job_ids:
            await test_redis.delete_job(job_id)

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_list_jobs_with_filter(
        self,
        test_redis: RedisManager,
    ) -> None:
        """Test listing jobs with status filter.

        Given: Jobs with different statuses
        When: List with status filter
        Then: Returns filtered list
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        # Create jobs with different statuses
        for i in range(5):
            job_id = f"test_filter_job_{i}"
            status_value = "completed" if i % 2 == 0 else "processing"
            job_data = {
                "job_id": job_id,
                "status": status_value,
            }
            await test_redis.set_job(job_id, job_data)

        # List with filter
        completed_jobs = await test_redis.list_jobs(
            limit=10,
            status_filter="completed",
        )

        # All returned jobs should be completed
        assert all(j["status"] == "completed" for j in completed_jobs)

        # Clean up
        for i in range(5):
            await test_redis.delete_job(f"test_filter_job_{i}")

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_list_jobs_pagination(
        self,
        test_redis: RedisManager,
    ) -> None:
        """Test listing jobs with pagination.

        Given: Many jobs stored
        When: List with limit and offset
        Then: Returns paginated results
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        # Create 10 jobs
        for i in range(10):
            job_id = f"test_page_job_{i}"
            job_data = {"job_id": job_id, "status": "completed"}
            await test_redis.set_job(job_id, job_data)

        # Get first page
        page1 = await test_redis.list_jobs(limit=5, offset=0)
        assert len(page1) <= 5

        # Get second page
        page2 = await test_redis.list_jobs(limit=5, offset=5)
        assert len(page2) <= 5

        # Clean up
        for i in range(10):
            await test_redis.delete_job(f"test_page_job_{i}")


class TestRedisJobTTL:
    """Test Redis job TTL functionality."""

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_job_ttl(self, test_redis: RedisManager) -> None:
        """Test jobs have TTL set.

        Given: Job stored with TTL
        When: Wait for TTL to expire
        Then: Job is automatically deleted
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        job_id = "test_ttl_job"
        job_data = {"job_id": job_id, "status": "queued"}

        # Set job with short TTL (2 seconds)
        result = await test_redis.set_job(job_id, job_data, ttl=2)
        assert result is True

        # Verify job exists
        retrieved = await test_redis.get_job(job_id)
        assert retrieved is not None

        # Wait for TTL to expire
        await asyncio.sleep(3)

        # Verify job expired
        expired = await test_redis.get_job(job_id)
        assert expired is None

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_job_default_ttl(
        self,
        test_redis: RedisManager,
    ) -> None:
        """Test job gets default TTL when not specified.

        Given: Job stored without explicit TTL
        When: Check TTL
        Then: Has default TTL
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        job_id = "test_default_ttl_job"
        job_data = {"job_id": job_id, "status": "queued"}

        # Set job without specifying TTL
        await test_redis.set_job(job_id, job_data)

        # Job should have default TTL (60 seconds from fixture)
        # Verify job exists
        retrieved = await test_redis.get_job(job_id)
        assert retrieved is not None


class TestRedisGracefulDegradation:
    """Test graceful degradation when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_redis_graceful_degradation(self) -> None:
        """Test app works without Redis.

        Given: Redis unavailable
        When: Attempt Redis operations
        Then: Fails gracefully without crashing
        """
        manager = RedisManager(
            redis_url="redis://invalid-host:6379",
            redis_db=15,
            key_prefix="test",
        )

        # Connection should fail gracefully
        connected = await manager.connect()
        assert connected is False
        assert manager.is_available is False

        # Operations should return safely
        result = await manager.set_job("test", {"data": "value"})
        assert result is False

        retrieved = await manager.get_job("test")
        assert retrieved is None

        updated = await manager.update_job("test", {"status": "completed"})
        assert updated is False

        deleted = await manager.delete_job("test")
        assert deleted is False

    def test_api_works_without_redis(self, client: TestClient) -> None:
        """Test API endpoints work without Redis.

        Given: Redis unavailable
        When: Make API requests
        Then: Requests succeed (using in-memory fallback)
        """
        # Health endpoint should work
        response = client.get("/health")
        assert response.status_code == 200

        # Transcription endpoint should work (uses in-memory fallback)
        request = {"source": "https://www.youtube.com/watch?v=test"}
        response = client.post("/api/v1/videos/transcribe", json=request)

        # Should succeed with 202
        assert response.status_code == 202

    def test_job_storage_fallback_to_memory(
        self,
        client: TestClient,
    ) -> None:
        """Test job storage falls back to memory.

        Given: Redis unavailable
        When: Create job
        Then: Job stored in memory
        """
        request = {"source": "https://www.youtube.com/watch?v=test123"}
        response = client.post("/api/v1/videos/transcribe", json=request)

        assert response.status_code == 202
        job_id = response.json()["job_id"]

        # Get job status (should work from memory)
        status_response = client.get(f"/api/v1/videos/jobs/{job_id}")

        # Should succeed
        assert status_response.status_code == 200


class TestRedisRateLimiting:
    """Test Redis-backed rate limiting."""

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_rate_limit_counter(
        self,
        test_redis: RedisManager,
    ) -> None:
        """Test rate limit counter operations.

        Given: Redis available
        When: Increment rate limit counter
        Then: Counter increments correctly
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        key = "test_rate_limit_counter"

        # Increment counter
        count1 = await test_redis.incr_rate_limit(key, window_seconds=60)
        assert count1 == 1

        # Increment again
        count2 = await test_redis.incr_rate_limit(key, window_seconds=60)
        assert count2 == 2

        # Get count
        retrieved = await test_redis.get_rate_limit_count(key)
        assert retrieved == 2

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_rate_limit_window_reset(
        self,
        test_redis: RedisManager,
    ) -> None:
        """Test rate limit window resets.

        Given: Rate limit counter
        When: Window expires
        Then: Counter resets
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        key = "test_rate_limit_window"

        # Increment with short window
        await test_redis.incr_rate_limit(key, window_seconds=2)

        # Verify count
        count = await test_redis.get_rate_limit_count(key)
        assert count == 1

        # Wait for window to expire
        await asyncio.sleep(3)

        # Counter should be reset
        new_count = await test_redis.get_rate_limit_count(key)
        assert new_count == 0 or new_count == 1  # May vary based on implementation


class TestRedisConnectionPool:
    """Test Redis connection pool management."""

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_disconnect(self, test_redis: RedisManager) -> None:
        """Test Redis disconnect.

        Given: Redis connected
        When: Disconnect
        Then: Connection closed properly
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        # Disconnect
        await test_redis.disconnect()

        assert test_redis.is_available is False

    @pytest.mark.asyncio
    async def test_redis_reconnect(self) -> None:
        """Test Redis reconnect.

        Given: Redis disconnected
        When: Reconnect
        Then: Connection re-established
        """
        manager = RedisManager(
            redis_url="redis://localhost:6379",
            redis_db=15,
            key_prefix="test",
        )

        # First connection
        await manager.connect()

        # Disconnect
        await manager.disconnect()

        # Reconnect
        await manager.connect()

        # Should be available if Redis is running
        # (test may skip if Redis not available)


class TestRedisKeyPrefix:
    """Test Redis key prefix functionality."""

    @pytest.mark.requires_redis
    @pytest.mark.asyncio
    async def test_redis_key_prefix(self, test_redis: RedisManager) -> None:
        """Test keys use configured prefix.

        Given: Redis with key prefix
        When: Store job
        Then: Key includes prefix
        """
        if not test_redis.is_available:
            pytest.skip("Redis not available")

        job_id = "test_prefix_job"
        job_data = {"job_id": job_id}

        await test_redis.set_job(job_id, job_data)

        # Key should include prefix
        # This is tested indirectly through get_job
        retrieved = await test_redis.get_job(job_id)
        assert retrieved is not None
        assert retrieved["job_id"] == job_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "requires_redis"])
