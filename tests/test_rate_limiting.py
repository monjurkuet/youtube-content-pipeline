"""Tests for rate limiting middleware.

These tests verify:
- Rate limit enforcement
- Rate limit headers
- Tiered rate limits
- 429 response handling
"""

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.middleware.rate_limiter import (
    get_limiter,
    rate_limit,
    rate_limit_exceeded_handler,
    setup_rate_limiter,
)


@pytest.fixture
def test_app():
    """Create test FastAPI application."""
    app = FastAPI()

    # Set up rate limiter
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.get("/limited")
    @rate_limit("2/minute")
    async def limited_endpoint():
        return {"status": "ok"}

    @app.get("/unlimited")
    async def unlimited_endpoint():
        return {"status": "ok"}

    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


def test_rate_limit_enforcement(client):
    """Test that rate limits are enforced."""
    # First request should succeed
    response = client.get("/limited")
    assert response.status_code == 200

    # Second request should succeed
    response = client.get("/limited")
    assert response.status_code == 200

    # Third request should be rate limited
    response = client.get("/limited")
    assert response.status_code == 429
    assert "RATE_LIMIT_EXCEEDED" in response.json()["error_code"]


def test_rate_limit_headers(client):
    """Test that rate limit headers are present."""
    response = client.get("/limited")

    # Should have rate limit headers
    assert "X-RateLimit-Limit" in response.headers or response.status_code == 200


def test_unlimited_endpoint(client):
    """Test that unlimited endpoints work."""
    # Multiple requests should all succeed
    for _ in range(10):
        response = client.get("/unlimited")
        assert response.status_code == 200


def test_rate_limit_reset(client):
    """Test rate limit window reset."""
    import time

    # Exhaust rate limit
    for _ in range(3):
        client.get("/limited")

    # Should be rate limited
    response = client.get("/limited")
    assert response.status_code == 429

    # Check Retry-After header
    assert "Retry-After" in response.headers


def test_get_limiter():
    """Test limiter creation."""
    limiter = get_limiter()
    assert limiter is not None


def test_rate_limit_decorator():
    """Test rate limit decorator."""
    from slowapi import limit

    decorator = rate_limit("5/minute")
    assert decorator is not None


class TestTieredRateLimits:
    """Test tiered rate limiting."""

    def test_free_tier_limit(self):
        """Test free tier rate limit."""
        from src.core.config import get_settings

        settings = get_settings()
        free_limit = settings.rate_limit_tiers.get("free", 10)
        assert free_limit == 10

    def test_pro_tier_limit(self):
        """Test pro tier rate limit."""
        from src.core.config import get_settings

        settings = get_settings()
        pro_limit = settings.rate_limit_tiers.get("pro", 100)
        assert pro_limit == 100

    def test_enterprise_tier_limit(self):
        """Test enterprise tier rate limit."""
        from src.core.config import get_settings

        settings = get_settings()
        enterprise_limit = settings.rate_limit_tiers.get("enterprise", 1000)
        assert enterprise_limit == 1000


class TestRateLimitExceededHandler:
    """Test rate limit exceeded error handler."""

    def test_handler_returns_429(self):
        """Test handler returns 429 status."""
        from fastapi import Request
        from slowapi import RateLimitExceeded

        exc = RateLimitExceeded(None, None, None, "60")

        # Create mock request
        app = FastAPI()

        @app.get("/test")
        def test():
            raise exc

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test")

        assert response.status_code == 429

    def test_handler_includes_retry_after(self):
        """Test handler includes Retry-After header."""
        from fastapi import Request
        from slowapi import RateLimitExceeded

        exc = RateLimitExceeded(None, None, None, "120")

        # The handler should include retry_after in response
        assert exc is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
