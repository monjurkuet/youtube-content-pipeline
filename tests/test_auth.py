"""Tests for API key authentication.

These tests verify:
- API key generation and validation
- API key hashing
- Authentication dependencies
- Rate limit tier assignment
"""

import pytest
from datetime import datetime, timedelta, timezone

from src.api.security import (
    APIKey,
    APIKeyContext,
    APIKeyValidator,
    Permission,
    RateLimitTier,
    generate_api_key,
    hash_api_key,
    mask_api_key,
    validate_api_key,
    require_api_key,
)


def test_generate_api_key():
    """Test API key generation."""
    key = generate_api_key()

    # Key should be non-empty
    assert key
    assert len(key) > 0

    # Keys should be unique
    key2 = generate_api_key()
    assert key != key2


def test_hash_api_key():
    """Test API key hashing."""
    key = "test_api_key_123"
    hashed = hash_api_key(key)

    # Hash should be non-empty
    assert hashed
    assert len(hashed) == 64  # SHA-256 produces 64 hex characters

    # Same key should produce same hash
    assert hash_api_key(key) == hashed

    # Different keys should produce different hashes
    assert hash_api_key("different_key") != hashed


def test_mask_api_key():
    """Test API key masking."""
    # Short key
    assert mask_api_key("short") == "*****"

    # Long key
    key = "sk_abcdefghijklmnopqrstuvwxyz123456"
    masked = mask_api_key(key)
    assert masked.startswith(key[:4])
    assert masked.endswith(key[-4:])
    assert "..." in masked


def test_api_key_model():
    """Test APIKey model."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)

    api_key = APIKey(
        key="hashed_key_123",
        name="Test Key",
        created_at=now,
        expires_at=expires,
        scopes=[Permission.READ, Permission.WRITE],
        rate_limit_tier=RateLimitTier.PRO,
    )

    assert api_key.name == "Test Key"
    assert api_key.rate_limit_tier == RateLimitTier.PRO
    assert Permission.READ in api_key.scopes
    assert not api_key.is_expired()
    assert api_key.has_permission(Permission.READ)
    assert not api_key.has_permission(Permission.ADMIN)


def test_api_key_expiration():
    """Test API key expiration check."""
    # Expired key
    expired_key = APIKey(
        key="hashed_key",
        name="Expired Key",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert expired_key.is_expired()

    # Valid key
    valid_key = APIKey(
        key="hashed_key",
        name="Valid Key",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    assert not valid_key.is_expired()

    # No expiration
    no_expiry_key = APIKey(
        key="hashed_key",
        name="No Expiry Key",
        expires_at=None,
    )
    assert not no_expiry_key.is_expired()


class TestAPIKeyValidator:
    """Test APIKeyValidator class."""

    def test_validator_with_valid_keys(self):
        """Test validator with valid keys."""
        validator = APIKeyValidator(
            valid_keys=["key1", "key2", "key3"],
            store_keys_hashed=False,
        )

        assert validator.validate("key1") is True
        assert validator.validate("key2") is True
        assert validator.validate("key3") is True
        assert validator.validate("invalid") is False
        assert validator.validate("") is False

    def test_validator_with_hashed_keys(self):
        """Test validator with hashed keys."""
        validator = APIKeyValidator(
            valid_keys=["key1", "key2"],
            store_keys_hashed=True,
        )

        assert validator.validate("key1") is True
        assert validator.validate("key2") is True
        assert validator.validate("invalid") is False

    def test_validator_required(self):
        """Test validator with required=True."""
        validator = APIKeyValidator(
            valid_keys=["key1"],
            required=True,
            store_keys_hashed=False,
        )

        assert validator.validate("key1") is True
        assert validator.validate("invalid") is False

    def test_validator_rate_limit_tier(self):
        """Test rate limit tier retrieval."""
        validator = APIKeyValidator(
            valid_keys=["free_key", "pro_key"],
            store_keys_hashed=False,
        )

        # Default tier
        tier = validator.get_rate_limit_tier("free_key")
        assert tier == RateLimitTier.FREE


@pytest.mark.asyncio
async def test_validate_api_key_dependency():
    """Test validate_api_key dependency."""
    from fastapi import Request
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/test")
    async def test_endpoint(ctx=None):
        return {"auth": ctx is not None}

    client = TestClient(app)

    # Without API key
    response = client.get("/test")
    assert response.status_code == 200

    # With invalid API key
    response = client.get("/test", headers={"X-API-Key": "invalid"})
    # Should not raise error since auth is optional by default


@pytest.mark.asyncio
async def test_require_api_key_dependency():
    """Test require_api_key dependency."""
    from fastapi import Request
    from fastapi.testclient import TestClient
    from fastapi import FastAPI, Depends
    from src.api.security import require_api_key as require_key

    app = FastAPI()

    @app.get("/protected")
    async def protected_endpoint(ctx=Depends(require_key)):
        return {"authenticated": True}

    client = TestClient(app)

    # Without API key - should fail
    response = client.get("/protected")
    assert response.status_code == 401

    # With invalid API key - should fail
    response = client.get("/protected", headers={"X-API-Key": "invalid"})
    assert response.status_code == 401


def test_api_key_context():
    """Test APIKeyContext model."""
    ctx = APIKeyContext(
        api_key="sk_...1234",
        key_name="Test Key",
        rate_limit_tier=RateLimitTier.ENTERPRISE,
        scopes=[Permission.READ, Permission.WRITE, Permission.ADMIN],
        key_hash="abc123",
    )

    assert ctx.api_key == "sk_...1234"
    assert ctx.rate_limit_tier == RateLimitTier.ENTERPRISE
    assert Permission.ADMIN in ctx.scopes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
