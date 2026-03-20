"""Tests for Groq transcription provider."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.transcription.groq_provider import GroqTranscriptionProvider
from src.core.exceptions import WhisperError
from src.core.schemas import RawTranscript, TranscriptSegment


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = Mock()
    settings.groq_api_key = "test_key"
    settings.groq_whisper_model = "whisper-large-v3"
    settings.groq_chunk_duration = 600
    settings.groq_chunk_overlap = 5
    settings.groq_max_file_size_mb = 25
    return settings


class TestGroqTranscriptionProvider:
    """Test Groq transcription provider."""

    def test_init_with_api_key(self, mock_settings):
        """Test initialization with API key."""
        provider = GroqTranscriptionProvider(mock_settings)
        assert provider.api_key == "test_key"

    def test_init_without_api_key(self):
        """Test initialization without API key raises error."""
        mock_settings = Mock()
        mock_settings.groq_api_key = ""
        with pytest.raises(WhisperError, match="GROQ_API_KEY not configured"):
            GroqTranscriptionProvider(mock_settings)

    @patch('src.transcription.groq_provider.requests.post')
    def test_transcribe_success(self, mock_post, mock_settings, tmp_path):
        """Test successful transcription."""
        # Setup
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio")
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "text": "Hello world",
            "segments": [
                {"text": "Hello world", "start": 0.0, "end": 1.0}
            ],
            "language": "en"
        }
        mock_post.return_value = mock_response
        
        # Execute
        provider = GroqTranscriptionProvider(mock_settings)
        result = provider.transcribe(str(audio_file), "en")
        
        # Verify
        assert isinstance(result, RawTranscript)
        assert result.source == "groq_whisper"
        assert len(result.segments) == 1
        assert result.segments[0].text == "Hello world"

    @patch('src.transcription.groq_provider.requests.post')
    def test_transcribe_api_error(self, mock_post, mock_settings, tmp_path):
        """Test API error handling."""
        # Setup
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio")
        
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response
        
        # Execute & Verify
        provider = GroqTranscriptionProvider(mock_settings)
        with pytest.raises(WhisperError, match="Groq API error 401"):
            provider.transcribe(str(audio_file), "en")

    def test_transcribe_file_not_found(self, mock_settings):
        """Test file not found error."""
        provider = GroqTranscriptionProvider(mock_settings)
        
        with pytest.raises(WhisperError, match="Audio file not found"):
            provider.transcribe("/nonexistent/file.wav", "en")

    def test_parse_response(self, mock_settings):
        """Test response parsing."""
        provider = GroqTranscriptionProvider(mock_settings)
        
        result = {
            "text": "Hello world",
            "segments": [
                {"text": "Hello", "start": 0.0, "end": 0.5},
                {"text": "world", "start": 0.5, "end": 1.0}
            ],
            "language": "en"
        }
        
        transcript = provider._parse_response(result, "en")
        
        assert isinstance(transcript, RawTranscript)
        assert transcript.source == "groq_whisper"
        assert len(transcript.segments) == 2
        assert transcript.segments[0].text == "Hello"
        assert transcript.segments[1].text == "world"

    def test_merge_transcriptions_single_chunk(self, mock_settings):
        """Test merging with single chunk returns same transcript."""
        provider = GroqTranscriptionProvider(mock_settings)
        
        chunk1 = RawTranscript(
            video_id="",
            segments=[
                TranscriptSegment(text="Hello", start=0.0, duration=0.5),
                TranscriptSegment(text="world", start=0.5, duration=0.5)
            ],
            source="groq_whisper",
            language="en"
        )
        
        merged = provider._merge_transcriptions([chunk1])
        
        assert isinstance(merged, RawTranscript)
        assert merged.source == "groq_whisper"
        assert len(merged.segments) == 2

    def test_merge_transcriptions_empty(self, mock_settings):
        """Test merging empty list returns empty transcript."""
        provider = GroqTranscriptionProvider(mock_settings)
        
        merged = provider._merge_transcriptions([])
        
        assert isinstance(merged, RawTranscript)
        assert merged.source == "groq_whisper"
        assert len(merged.segments) == 0
