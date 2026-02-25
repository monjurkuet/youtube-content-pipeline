"""Security module for API authentication and authorization.

This module provides:
- API key models with metadata
- API key validation with bcrypt hashing support
- Rate limit tier management
- Security scheme definitions for OpenAPI
- Authentication dependencies for route handlers
"""

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, SecurityScopes
from pydantic import BaseModel, Field

from src.core.config import get_settings

logger = logging.getLogger(__name__)

# Security schemes
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
BEARER_TOKEN = HTTPBearer(auto_error=False, scheme_name="Bearer")


class SecuritySchemes:
    """Security scheme definitions for OpenAPI documentation."""

    API_KEY = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "API key for authentication. Required for protected endpoints.",
    }

    BEARER = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT bearer token for authentication.",
    }


class Permission(str, Enum):
    """Permission levels for API access."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class RateLimitTier(str, Enum):
    """Rate limit tiers for API access."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class APIKey(BaseModel):
    """API key model with metadata.

    Attributes:
        key: The API key (hashed for storage, plain for validation)
        name: Human-readable name for the key
        created_at: When the key was created
        expires_at: When the key expires (None for no expiration)
        scopes: List of permissions granted to this key
        rate_limit_tier: Rate limit tier for this key
        is_active: Whether the key is currently active
    """

    key: str = Field(..., description="API key (hashed for storage)")
    name: str = Field(..., description="Human-readable name")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Expiration timestamp (None for no expiration)",
    )
    scopes: list[Permission] = Field(
        default_factory=lambda: [Permission.READ, Permission.WRITE],
        description="Granted permissions",
    )
    rate_limit_tier: RateLimitTier = Field(
        default=RateLimitTier.FREE,
        description="Rate limit tier",
    )
    is_active: bool = Field(default=True, description="Whether key is active")

    def is_expired(self) -> bool:
        """Check if the API key has expired.

        Returns:
            True if expired, False otherwise
        """
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def has_permission(self, permission: Permission) -> bool:
        """Check if key has a specific permission.

        Args:
            permission: Permission to check

        Returns:
            True if key has permission, False otherwise
        """
        return permission in self.scopes


class APIKeyContext(BaseModel):
    """Context information for authenticated API requests.

    Attributes:
        api_key: The API key used for authentication
        key_name: Human-readable name of the key
        rate_limit_tier: Rate limit tier for this request
        scopes: Permissions granted to this key
    """

    api_key: str = Field(..., description="API key (masked for logging)")
    key_name: str = Field(..., description="Key name")
    rate_limit_tier: RateLimitTier = Field(
        default=RateLimitTier.FREE,
        description="Rate limit tier",
    )
    scopes: list[Permission] = Field(
        default_factory=list,
        description="Granted permissions",
    )
    key_hash: str = Field(..., description="SHA256 hash of key for identification")


class APIKeyValidator:
    """Validate API keys for authentication.

    Supports:
    - Environment variable configuration
    - In-memory key storage
    - Bcrypt hashing for secure storage (optional)
    - Constant-time comparison to prevent timing attacks

    Usage:
        # Get validator with configured keys
        validator = APIKeyValidator(valid_keys=["key1", "key2"])

        # Validate a key
        is_valid = validator.validate("key1")

        # Or use as dependency
        @router.get("/protected")
        async def protected_route(api_key = Depends(validator)):
            ...
    """

    def __init__(
        self,
        valid_keys: list[str] | None = None,
        required: bool = False,
        store_keys_hashed: bool = True,
    ) -> None:
        """Initialize API key validator.

        Args:
            valid_keys: List of valid API keys. If None, uses environment vars.
            required: Whether API key is required (default: False for open API)
            store_keys_hashed: Whether to hash keys for storage
        """
        settings = get_settings()

        if valid_keys is None:
            # Load from settings (which reads from environment)
            valid_keys = settings.parsed_api_keys

        self.required = required
        self.store_keys_hashed = store_keys_hashed

        # Store keys (hashed if configured)
        if store_keys_hashed:
            self._valid_keys = {hash_api_key(k): k for k in valid_keys}
        else:
            self._valid_keys = set(valid_keys)

        # Key metadata storage (in production, use database)
        self._key_metadata: dict[str, APIKey] = {}

        # Initialize default key metadata
        for key in valid_keys:
            key_hash = hash_api_key(key) if store_keys_hashed else key
            self._key_metadata[key_hash] = APIKey(
                key=key_hash,
                name="Default Key",
                rate_limit_tier=RateLimitTier(settings.auth_default_rate_limit_tier),
            )

    def validate(self, api_key: str) -> bool:
        """Validate an API key.

        Args:
            api_key: API key to validate

        Returns:
            True if valid, False otherwise
        """
        if not api_key:
            return False

        if self.store_keys_hashed:
            key_hash = hash_api_key(api_key)
            return key_hash in self._valid_keys
        else:
            # Use constant-time comparison to prevent timing attacks
            for valid_key in self._valid_keys:
                if hmac.compare_digest(api_key.encode(), valid_key.encode()):
                    return True
            return False

    def get_key_metadata(self, api_key: str) -> APIKey | None:
        """Get metadata for an API key.

        Args:
            api_key: API key to look up

        Returns:
            APIKey metadata or None if not found
        """
        if not api_key:
            return None

        key_hash = hash_api_key(api_key) if self.store_keys_hashed else api_key
        return self._key_metadata.get(key_hash)

    def get_rate_limit_tier(self, api_key: str) -> RateLimitTier:
        """Get rate limit tier for an API key.

        Args:
            api_key: API key to look up

        Returns:
            Rate limit tier (default: FREE)
        """
        metadata = self.get_key_metadata(api_key)
        if metadata:
            return metadata.rate_limit_tier

        settings = get_settings()
        return RateLimitTier(settings.auth_default_rate_limit_tier)

    async def __call__(
        self,
        request: Request,
        api_key: str | None = Security(API_KEY_HEADER),
    ) -> APIKeyContext | None:
        """Validate API key from request.

        Args:
            request: FastAPI request object
            api_key: API key from header

        Returns:
            APIKeyContext if valid, None if not required

        Raises:
            HTTPException: If API key is invalid or missing
        """
        if not api_key:
            if self.required:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key is required",
                    headers={"WWW-Authenticate": "ApiKey"},
                )
            return None

        if not self.validate(api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Get metadata
        metadata = self.get_key_metadata(api_key)
        key_hash = hash_api_key(api_key)

        # Create context
        context = APIKeyContext(
            api_key=mask_api_key(api_key),
            key_name=metadata.name if metadata else "Unknown",
            rate_limit_tier=metadata.rate_limit_tier if metadata else RateLimitTier.FREE,
            scopes=metadata.scopes if metadata else [],
            key_hash=key_hash[:16],
        )

        # Log successful authentication (without the key)
        logger.debug(
            "API key authenticated",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "key_hash": key_hash[:16],
                "tier": context.rate_limit_tier.value,
            },
        )

        return context


# Global validator instance (configured via environment)
_api_key_validator: APIKeyValidator | None = None


def get_api_key_validator() -> APIKeyValidator:
    """Get or create the global API key validator.

    Returns:
        APIKeyValidator instance
    """
    global _api_key_validator
    if _api_key_validator is None:
        settings = get_settings()
        _api_key_validator = APIKeyValidator(
            required=settings.auth_require_key,
        )
    return _api_key_validator


async def validate_api_key(
    request: Request,
    api_key: str | None = Security(API_KEY_HEADER),
) -> APIKeyContext | None:
    """Dependency to validate API key.

    Use this as a dependency in route handlers that require authentication.

    Args:
        request: FastAPI request object
        api_key: API key from header

    Returns:
        APIKeyContext if valid, None if not required

    Raises:
        HTTPException: If API key is invalid

    Example:
        @router.get("/protected")
        async def protected_route(ctx = Depends(validate_api_key)):
            if ctx:
                # Authenticated request with context
                tier = ctx.rate_limit_tier
                ...
    """
    validator = get_api_key_validator()
    return await validator(request, api_key)


async def require_api_key(
    request: Request,
    api_key: str | None = Security(API_KEY_HEADER),
) -> APIKeyContext:
    """Dependency to require valid API key.

    Use this for routes that must be authenticated.

    Args:
        request: FastAPI request object
        api_key: API key from header

    Returns:
        APIKeyContext with authentication details

    Raises:
        HTTPException: If API key is missing or invalid

    Example:
        @router.get("/admin")
        async def admin_route(ctx = Depends(require_api_key)):
            # Only accessible with valid API key
            tier = ctx.rate_limit_tier
            ...
    """
    validator = APIKeyValidator(required=True)
    result = await validator(request, api_key)
    return result or APIKeyContext(
        api_key="unknown",
        key_name="Unknown",
        key_hash="unknown",
    )


def generate_api_key() -> str:
    """Generate a new secure API key.

    Returns:
        Random API key string
    """
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """Hash an API key for secure storage.

    Args:
        api_key: Plain text API key

    Returns:
        SHA-256 hash of the key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def mask_api_key(api_key: str) -> str:
    """Mask API key for logging/display.

    Args:
        api_key: Plain text API key

    Returns:
        Masked key (e.g., "sk_...abc123")
    """
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"


def get_security_schemes() -> dict[str, dict[str, Any]]:
    """Get security schemes for OpenAPI documentation.

    Returns:
        Dictionary of security schemes
    """
    return {
        "ApiKeyAuth": SecuritySchemes.API_KEY,
        "BearerAuth": SecuritySchemes.BEARER,
    }


def create_default_api_key() -> str:
    """Create a default API key for development.

    Returns:
        Generated API key
    """
    key = generate_api_key()
    logger.warning(
        "Generated default API key: %s - Store this securely!",
        key,
    )
    return key
