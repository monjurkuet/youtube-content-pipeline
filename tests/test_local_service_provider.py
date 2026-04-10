"""Tests for the local transcript service provider."""

from unittest.mock import Mock, patch

import pytest

from src.core.exceptions import WhisperError
from src.transcription.local_service_provider import LocalTranscriptServiceProvider


@pytest.fixture
def mock_settings():
    """Create mock settings for the local service provider."""
    settings = Mock()
    settings.transcript_service_base_url = "http://localhost:8346"
    settings.transcript_service_api_key = "change-me"
    settings.transcript_service_poll_interval_sec = 0.01
    settings.transcript_service_timeout_sec = 5
    settings.groq_whisper_model = "whisper-large-v3"
    settings.groq_chunk_duration = 600
    settings.groq_chunk_overlap = 5
    return settings


class TestLocalTranscriptServiceProvider:
    """Test local transcript service provider behavior."""

    def test_init_without_api_key_raises(self, mock_settings):
        """Provider should require an API key."""
        mock_settings.transcript_service_api_key = ""
        with pytest.raises(WhisperError, match="TRANSCRIPT_SERVICE_API_KEY not configured"):
            LocalTranscriptServiceProvider(mock_settings)

    @patch("src.transcription.local_service_provider.requests.get")
    @patch("src.transcription.local_service_provider.requests.post")
    def test_transcribe_success(self, mock_post, mock_get, mock_settings, tmp_path):
        """Provider should create a job and fetch its result."""
        audio_file = tmp_path / "sample.wav"
        audio_file.write_bytes(b"audio")

        create_response = Mock(status_code=202)
        create_response.json.return_value = {"job": {"id": "job-123"}}
        mock_post.return_value = create_response

        status_response = Mock(status_code=200)
        status_response.json.return_value = {"job": {"status": "succeeded"}}

        result_response = Mock(status_code=200)
        result_response.json.return_value = {
            "transcript": {
                "text": "hello world",
                "provider": "groq",
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": "hello world"},
                ],
            }
        }
        mock_get.side_effect = [status_response, result_response]

        provider = LocalTranscriptServiceProvider(mock_settings)
        result = provider.transcribe(str(audio_file))

        assert result.source == "local_service"
        assert result.language == "en"
        assert len(result.segments) == 1
        assert result.segments[0].text == "hello world"
        assert result.segments[0].duration == 1.5

    @patch("src.transcription.local_service_provider.requests.get")
    @patch("src.transcription.local_service_provider.requests.post")
    def test_transcribe_failed_job_raises(self, mock_post, mock_get, mock_settings, tmp_path):
        """Provider should surface remote job failures."""
        audio_file = tmp_path / "sample.wav"
        audio_file.write_bytes(b"audio")

        create_response = Mock(status_code=202)
        create_response.json.return_value = {"job": {"id": "job-123"}}
        mock_post.return_value = create_response

        status_response = Mock(status_code=200)
        status_response.json.return_value = {"job": {"status": "failed", "error": "remote fail"}}
        mock_get.return_value = status_response

        provider = LocalTranscriptServiceProvider(mock_settings)
        with pytest.raises(WhisperError, match="remote fail"):
            provider.transcribe(str(audio_file))
