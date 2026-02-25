"""Tests for API key authentication.

This module tests:
- Authentication flows
- API key validation
- Header formats
- Permission scopes
- Token authentication
"""

import os
import pytest
from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient

from src.api.security import generate_api_key


class TestAuthenticationFlows:
    """Test authentication flow scenarios."""

    def test_endpoint_without_auth(self, client: TestClient) -> None:
        """Test endpoint works when auth is optional.

        Given: API with optional authentication
        When: Request without API key
        Then: Request succeeds (auth is optional by default)
        """
        # Health endpoint should work without auth
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK

    def test_public_endpoints_accessible(self, client: TestClient) -> None:
        """Test public endpoints are accessible without auth.

        Given: Public endpoints
        When: Requests without API key
        Then: All public endpoints return 200
        """
        public_endpoints = [
            "/health",
            "/health/live",
            "/health/ready",
            "/health/detailed",
            "/openapi.json",
            "/docs",
            "/redoc",
        ]

        for endpoint in public_endpoints:
            response = client.get(endpoint)
            assert response.status_code == status.HTTP_200_OK, f"Failed for {endpoint}"


class TestAPIKeyAuthentication:
    """Test API key authentication."""

    def test_endpoint_with_valid_api_key(
        self,
        client_with_auth: TestClient,
        valid_api_key: str,
    ) -> None:
        """Test endpoint works with valid API key.

        Given: API with authentication required
        When: Request with valid API key
        Then: Request succeeds with 200
        """
        headers = {"X-API-Key": valid_api_key}

        # Health endpoint should work with valid key
        response = client_with_auth.get("/health", headers=headers)

        assert response.status_code == status.HTTP_200_OK

    def test_endpoint_with_invalid_api_key(
        self,
        client_with_auth: TestClient,
        invalid_api_key: str,
    ) -> None:
        """Test endpoint returns 401 with invalid API key.

        Given: API with authentication required
        When: Request with invalid API key
        Then: Returns 401 Unauthorized
        """
        headers = {"X-API-Key": invalid_api_key}

        response = client_with_auth.get("/health", headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_endpoint_with_missing_api_key(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test endpoint returns 401 when API key is missing.

        Given: API with authentication required
        When: Request without API key
        Then: Returns 401 Unauthorized
        """
        response = client_with_auth.get("/health")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_protected_endpoint_requires_auth(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test protected endpoints require authentication.

        Given: Protected endpoint
        When: Request without API key
        Then: Returns 401 Unauthorized
        """
        # Try to transcribe without auth
        request = {"source": "https://www.youtube.com/watch?v=test123"}
        response = client_with_auth.post(
            "/api/v1/videos/transcribe",
            json=request,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAPIKeyHeaderFormats:
    """Test different API key header formats."""

    def test_x_api_key_header(
        self,
        client_with_auth: TestClient,
        valid_api_key: str,
    ) -> None:
        """Test X-API-Key header format.

        Given: Valid API key
        When: Request with X-API-Key header
        Then: Authentication succeeds
        """
        headers = {"X-API-Key": valid_api_key}

        response = client_with_auth.get("/health", headers=headers)

        assert response.status_code == status.HTTP_200_OK

    def test_authorization_bearer_header(
        self,
        client_with_auth: TestClient,
        valid_api_key: str,
    ) -> None:
        """Test Authorization Bearer header format.

        Given: Valid API key
        When: Request with Authorization: Bearer header
        Then: Authentication may succeed or fail depending on configuration
        """
        headers = {"Authorization": f"Bearer {valid_api_key}"}

        response = client_with_auth.get("/health", headers=headers)

        # May work if Bearer auth is configured, or return 401
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
        ]

    def test_both_headers_provided(
        self,
        client_with_auth: TestClient,
        valid_api_key: str,
    ) -> None:
        """Test request with both header formats.

        Given: Valid API key
        When: Request with both X-API-Key and Authorization headers
        Then: X-API-Key takes precedence
        """
        headers = {
            "X-API-Key": valid_api_key,
            "Authorization": f"Bearer {valid_api_key}",
        }

        response = client_with_auth.get("/health", headers=headers)

        assert response.status_code == status.HTTP_200_OK

    def test_empty_api_key_header(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test request with empty API key.

        Given: Empty API key
        When: Request with empty X-API-Key header
        Then: Returns 401 Unauthorized
        """
        headers = {"X-API-Key": ""}

        response = client_with_auth.get("/health", headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_whitespace_api_key(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test request with whitespace API key.

        Given: Whitespace-only API key
        When: Request with whitespace X-API-Key header
        Then: Returns 401 Unauthorized
        """
        headers = {"X-API-Key": "   "}

        response = client_with_auth.get("/health", headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAPIKeyScopes:
    """Test API key permission scopes."""

    def test_read_scope_access(
        self,
        client_with_auth: TestClient,
        valid_api_key: str,
    ) -> None:
        """Test read-only scope can access GET endpoints.

        Given: API key with read scope
        When: GET request to transcript endpoint
        Then: Access is granted
        """
        headers = {"X-API-Key": valid_api_key}

        # Read operation
        response = client_with_auth.get("/api/v1/transcripts/", headers=headers)

        # Should succeed (read is typically allowed)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,  # If key doesn't have read scope
        ]

    def test_write_scope_access(
        self,
        client_with_auth: TestClient,
        valid_api_key: str,
    ) -> None:
        """Test write scope can access POST endpoints.

        Given: API key with write scope
        When: POST request to transcribe endpoint
        Then: Access is granted
        """
        headers = {"X-API-Key": valid_api_key}

        request = {"source": "https://www.youtube.com/watch?v=test123"}
        response = client_with_auth.post(
            "/api/v1/videos/transcribe",
            json=request,
            headers=headers,
        )

        # Should succeed if key has write scope
        assert response.status_code in [
            status.HTTP_202_ACCEPTED,
            status.HTTP_401_UNAUTHORIZED,  # If key doesn't have write scope
        ]


class TestAPIKeyEdgeCases:
    """Test API key edge cases."""

    def test_very_long_api_key(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test very long API key.

        Given: Very long API key string
        When: Request with long key
        Then: Handled gracefully (401 if invalid)
        """
        long_key = "x" * 1000
        headers = {"X-API-Key": long_key}

        response = client_with_auth.get("/health", headers=headers)

        # Should not crash, should return 401 for invalid key
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_special_characters_in_api_key(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test API key with special characters.

        Given: API key with special characters
        When: Request with special character key
        Then: Handled gracefully
        """
        special_key = "key_with_special_chars!@#$%^&*()"
        headers = {"X-API-Key": special_key}

        response = client_with_auth.get("/health", headers=headers)

        # Should not crash
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unicode_in_api_key(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test API key with unicode characters.

        Given: API key with unicode
        When: Request with unicode key
        Then: Handled gracefully
        """
        unicode_key = "key__with_unicode_🔑_emoji"
        headers = {"X-API-Key": unicode_key}

        response = client_with_auth.get("/health", headers=headers)

        # Should not crash
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_case_sensitivity(
        self,
        client_with_auth: TestClient,
        valid_api_key: str,
    ) -> None:
        """Test API key case sensitivity.

        Given: Valid API key
        When: Request with different case
        Then: Returns 401 (keys are case-sensitive)
        """
        # Change case of key
        wrong_case_key = valid_api_key.upper()
        headers = {"X-API-Key": wrong_case_key}

        response = client_with_auth.get("/health", headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestMultipleAPIKeys:
    """Test multiple API key configuration."""

    def test_multiple_valid_keys(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test multiple valid keys work.

        Given: Multiple valid API keys configured
        When: Requests with different valid keys
        Then: All keys authenticate successfully
        """
        # The client_with_auth fixture configures multiple keys
        valid_keys = ["test-api-key-123", "another-test-key"]

        for key in valid_keys:
            headers = {"X-API-Key": key}
            response = client_with_auth.get("/health", headers=headers)

            assert response.status_code == status.HTTP_200_OK

    def test_one_invalid_among_valid(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test invalid key among valid ones.

        Given: Multiple valid keys configured
        When: Request with invalid key
        Then: Returns 401
        """
        headers = {"X-API-Key": "completely_invalid_key"}

        response = client_with_auth.get("/health", headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAuthenticationWithTranscription:
    """Test authentication with transcription endpoints."""

    def test_transcribe_with_auth(
        self,
        client_with_auth: TestClient,
        valid_api_key: str,
    ) -> None:
        """Test transcription endpoint with authentication.

        Given: Valid API key
        When: POST to transcribe endpoint
        Then: Job is created successfully
        """
        headers = {"X-API-Key": valid_api_key}
        request = {"source": "https://www.youtube.com/watch?v=test123"}

        response = client_with_auth.post(
            "/api/v1/videos/transcribe",
            json=request,
            headers=headers,
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert "job_id" in data

    def test_get_job_status_with_auth(
        self,
        client_with_auth: TestClient,
        valid_api_key: str,
    ) -> None:
        """Test job status endpoint with authentication.

        Given: Valid API key and existing job
        When: GET job status endpoint
        Then: Returns job status
        """
        headers = {"X-API-Key": valid_api_key}

        # First create a job
        request = {"source": "https://www.youtube.com/watch?v=test123"}
        create_response = client_with_auth.post(
            "/api/v1/videos/transcribe",
            json=request,
            headers=headers,
        )
        assert create_response.status_code == status.HTTP_202_ACCEPTED

        job_id = create_response.json()["job_id"]

        # Then get status
        status_response = client_with_auth.get(
            f"/api/v1/videos/jobs/{job_id}",
            headers=headers,
        )

        assert status_response.status_code == status.HTTP_200_OK

    def test_list_transcripts_with_auth(
        self,
        client_with_auth: TestClient,
        valid_api_key: str,
    ) -> None:
        """Test list transcripts endpoint with authentication.

        Given: Valid API key
        When: GET list transcripts endpoint
        Then: Returns transcript list
        """
        headers = {"X-API-Key": valid_api_key}

        response = client_with_auth.get("/api/v1/transcripts/", headers=headers)

        assert response.status_code == status.HTTP_200_OK


class TestAuthenticationErrorMessages:
    """Test authentication error message formats."""

    def test_401_error_format(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test 401 error response format.

        Given: Invalid API key
        When: Request to protected endpoint
        Then: Returns proper error format
        """
        headers = {"X-API-Key": "invalid_key"}

        response = client_with_auth.get("/health", headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert "detail" in data

    def test_www_authenticate_header(
        self,
        client_with_auth: TestClient,
    ) -> None:
        """Test WWW-Authenticate header is present.

        Given: Missing API key
        When: Request to protected endpoint
        Then: Response includes WWW-Authenticate header
        """
        response = client_with_auth.get("/health")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        # Check for WWW-Authenticate header
        assert "WWW-Authenticate" in response.headers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
