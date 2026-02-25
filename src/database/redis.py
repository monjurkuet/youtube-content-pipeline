"""Redis integration for job storage and caching.

This module provides:
- Redis connection management with connection pooling
- Async operations for job storage
- Key prefixing for namespacing
- TTL management for auto-expiration
- Health check capabilities

Usage:
    # Get Redis manager
    redis_manager = get_redis_manager()

    # Store job
    await redis_manager.set_job("job_123", {"status": "processing"})

    # Retrieve job
    job = await redis_manager.get_job("job_123")

    # Update job
    await redis_manager.update_job("job_123", {"status": "completed"})
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Redis connection and operation manager.

    Provides async Redis operations with connection pooling and graceful
    degradation when Redis is unavailable.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        redis_db: int = 0,
        key_prefix: str = "transcription",
        default_ttl: int = 3600,
        health_check_timeout: float = 5.0,
    ) -> None:
        """Initialize Redis manager.

        Args:
            redis_url: Redis connection URL (redis://localhost:6379)
            redis_db: Redis database number
            key_prefix: Prefix for all keys (e.g., "transcription:job:...")
            default_ttl: Default TTL for keys in seconds
            health_check_timeout: Timeout for health checks in seconds
        """
        settings = get_settings()

        self.redis_url = redis_url or settings.redis_url
        self.redis_db = redis_db or settings.redis_db
        self.key_prefix = key_prefix or settings.redis_key_prefix
        self.default_ttl = default_ttl
        self.health_check_timeout = health_check_timeout

        self._pool: ConnectionPool | None = None
        self._client: redis.Redis | None = None
        self._available = False

    async def connect(self) -> bool:
        """Establish Redis connection with connection pooling.

        Returns:
            True if connection successful, False otherwise
        """
        if self._client is not None:
            return self._available

        try:
            # Create connection pool
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                db=self.redis_db,
                decode_responses=True,
                max_connections=50,
                socket_timeout=self.health_check_timeout,
                socket_connect_timeout=self.health_check_timeout,
            )

            # Create Redis client
            self._client = redis.Redis(connection_pool=self._pool)

            # Test connection
            await self._client.ping()
            self._available = True

            logger.info(
                "Redis connection established",
                extra={"url": self._redis_url_safe()},
            )
            return True

        except Exception as e:
            logger.warning(
                "Redis connection failed, operating in degraded mode: %s",
                e,
            )
            self._available = False
            self._client = None
            self._pool = None
            return False

    async def disconnect(self) -> None:
        """Close Redis connection and pool."""
        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning("Error closing Redis client: %s", e)
            finally:
                self._client = None
                self._available = False

        if self._pool:
            try:
                await self._pool.disconnect()
            except Exception as e:
                logger.warning("Error disconnecting Redis pool: %s", e)
            finally:
                self._pool = None

        logger.info("Redis connection closed")

    def _redis_url_safe(self) -> str:
        """Return sanitized Redis URL for logging (no password)."""
        if "://" not in self.redis_url:
            return self.redis_url
        scheme, rest = self.redis_url.split("://", 1)
        if "@" in rest:
            userinfo, host = rest.split("@", 1)
            if ":" in userinfo:
                username, _ = userinfo.split(":", 1)
                return f"{scheme}://{username}:***@{host}"
            return f"{scheme}://***@{host}"
        return self.redis_url

    def _make_key(self, key_type: str, identifier: str) -> str:
        """Create prefixed Redis key.

        Args:
            key_type: Type of key (e.g., "job", "cache")
            identifier: Unique identifier

        Returns:
            Prefixed key string
        """
        return f"{self.key_prefix}:{key_type}:{identifier}"

    async def _ensure_connected(self) -> bool:
        """Ensure Redis is connected, attempt connection if not.

        Returns:
            True if connected, False otherwise
        """
        if self._client is None:
            return await self.connect()
        return self._available

    # Job Operations

    async def set_job(
        self,
        job_id: str,
        job_data: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Store job data in Redis.

        Args:
            job_id: Unique job identifier
            job_data: Job data dictionary
            ttl: Time-to-live in seconds (default: 3600)

        Returns:
            True if successful, False otherwise
        """
        if not await self._ensure_connected():
            return False

        try:
            key = self._make_key("job", job_id)
            # Serialize job data, handling datetime objects
            serialized = json.dumps(job_data, default=self._json_serializer)
            await self._client.set(key, serialized, ex=ttl or self.default_ttl)
            logger.debug("Job stored in Redis: %s", job_id)
            return True
        except Exception as e:
            logger.error("Failed to store job in Redis: %s", e)
            return False

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve job data from Redis.

        Args:
            job_id: Unique job identifier

        Returns:
            Job data dictionary or None if not found
        """
        if not await self._ensure_connected():
            return None

        try:
            key = self._make_key("job", job_id)
            data = await self._client.get(key)
            if data is None:
                return None
            return json.loads(data)
        except Exception as e:
            logger.error("Failed to get job from Redis: %s", e)
            return None

    async def update_job(
        self,
        job_id: str,
        updates: dict[str, Any],
        extend_ttl: bool = True,
    ) -> bool:
        """Update specific fields of a job.

        Args:
            job_id: Unique job identifier
            updates: Dictionary of fields to update
            extend_ttl: Whether to extend TTL on update

        Returns:
            True if successful, False otherwise
        """
        if not await self._ensure_connected():
            return False

        try:
            key = self._make_key("job", job_id)
            existing = await self._client.get(key)

            if existing is None:
                logger.warning("Cannot update non-existent job: %s", job_id)
                return False

            job_data = json.loads(existing)
            job_data.update(updates)

            serialized = json.dumps(job_data, default=self._json_serializer)

            if extend_ttl:
                await self._client.set(key, serialized, ex=self.default_ttl)
            else:
                await self._client.set(key, serialized)

            logger.debug("Job updated in Redis: %s", job_id)
            return True

        except Exception as e:
            logger.error("Failed to update job in Redis: %s", e)
            return False

    async def delete_job(self, job_id: str) -> bool:
        """Delete job from Redis.

        Args:
            job_id: Unique job identifier

        Returns:
            True if deleted, False otherwise
        """
        if not await self._ensure_connected():
            return False

        try:
            key = self._make_key("job", job_id)
            result = await self._client.delete(key)
            logger.debug("Job deleted from Redis: %s (existed: %s)", job_id, result > 0)
            return result > 0
        except Exception as e:
            logger.error("Failed to delete job from Redis: %s", e)
            return False

    async def list_jobs(
        self,
        limit: int = 100,
        offset: int = 0,
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """List jobs from Redis.

        Note: This is an O(N) operation. For production with many jobs,
        consider using Redis sorted sets or a separate index.

        Args:
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip
            status_filter: Optional filter by status

        Returns:
            List of job dictionaries
        """
        if not await self._ensure_connected():
            return []

        try:
            pattern = self._make_key("job", "*")
            keys = []

            async for key in self._client.scan_iter(match=pattern, count=100):
                keys.append(key)

            # Sort keys for consistent ordering (newest first)
            keys.sort(reverse=True)

            # Apply offset and limit
            keys = keys[offset : offset + limit]

            jobs = []
            for key in keys:
                data = await self._client.get(key)
                if data:
                    job = json.loads(data)
                    if status_filter is None or job.get("status") == status_filter:
                        jobs.append(job)

            return jobs

        except Exception as e:
            logger.error("Failed to list jobs from Redis: %s", e)
            return []

    async def list_job_keys(self, limit: int = 1000) -> list[str]:
        """List all job keys (for debugging/maintenance).

        Args:
            limit: Maximum number of keys to return

        Returns:
            List of job keys
        """
        if not await self._ensure_connected():
            return []

        try:
            pattern = self._make_key("job", "*")
            keys = []

            async for key in self._client.scan_iter(match=pattern, count=100):
                keys.append(key)
                if len(keys) >= limit:
                    break

            return keys

        except Exception as e:
            logger.error("Failed to list job keys: %s", e)
            return []

    # Rate Limiting Operations

    async def incr_rate_limit(
        self,
        key: str,
        window_seconds: int = 60,
    ) -> int:
        """Increment rate limit counter.

        Args:
            key: Rate limit key (e.g., "ratelimit:api_key:xxx")
            window_seconds: Time window in seconds

        Returns:
            Current count after increment
        """
        if not await self._ensure_connected():
            return 0

        try:
            full_key = self._make_key("ratelimit", key)
            pipe = self._client.pipeline()
            pipe.incr(full_key)
            pipe.expire(full_key, window_seconds)
            results = await pipe.execute()
            return results[0]
        except Exception as e:
            logger.error("Failed to increment rate limit: %s", e)
            return 0

    async def get_rate_limit_count(self, key: str) -> int:
        """Get current rate limit count.

        Args:
            key: Rate limit key

        Returns:
            Current count or 0
        """
        if not await self._ensure_connected():
            return 0

        try:
            full_key = self._make_key("ratelimit", key)
            count = await self._client.get(full_key)
            return int(count) if count else 0
        except Exception as e:
            logger.error("Failed to get rate limit count: %s", e)
            return 0

    # Metrics Operations

    async def incr_metric(
        self,
        metric_name: str,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Increment a metric counter.

        Args:
            metric_name: Name of the metric
            labels: Optional labels for the metric
        """
        if not await self._ensure_connected():
            return

        try:
            key_parts = [self.key_prefix, "metric", metric_name]
            if labels:
                label_str = ":".join(f"{k}={v}" for k, v in sorted(labels.items()))
                key_parts.append(label_str)

            key = ":".join(key_parts)
            await self._client.incr(key)
        except Exception as e:
            logger.error("Failed to increment metric: %s", e)

    # Health Check

    async def health_check(self) -> dict[str, Any]:
        """Perform Redis health check.

        Returns:
            Health status dictionary
        """
        result = {
            "status": "unhealthy",
            "latency_ms": 0,
            "available": False,
        }

        if not await self._ensure_connected():
            return result

        try:
            start = datetime.now(timezone.utc)
            await self._client.ping()
            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            result["status"] = "healthy"
            result["latency_ms"] = round(latency, 2)
            result["available"] = True

        except Exception as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)
            self._available = False

        return result

    @property
    def is_available(self) -> bool:
        """Check if Redis is available."""
        return self._available

    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """Custom JSON serializer for datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# Global Redis manager instance
_redis_manager: RedisManager | None = None


def get_redis_manager() -> RedisManager:
    """Get or create the global Redis manager.

    Returns:
        RedisManager instance
    """
    global _redis_manager
    if _redis_manager is None:
        _redis_manager = RedisManager()
    return _redis_manager


async def init_redis() -> RedisManager:
    """Initialize Redis connection.

    Returns:
        RedisManager instance
    """
    manager = get_redis_manager()
    await manager.connect()
    return manager


async def close_redis() -> None:
    """Close Redis connection."""
    manager = get_redis_manager()
    await manager.disconnect()
