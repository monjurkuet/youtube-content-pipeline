"""Whisper transcription provider using Groq API."""

import logging
from src.core.config import get_settings_with_yaml
from src.core.exceptions import WhisperError
from src.core.schemas import RawTranscript

logger = logging.getLogger(__name__)


class WhisperProvider:
    """Provides transcription using Groq Whisper API."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings_with_yaml()

    def transcribe(self, audio_path: str, language: str = "en") -> RawTranscript:
        """Transcribe audio file using Groq Whisper API."""
        # Groq API (sole provider)
        if not self.settings.groq_api_key:
            raise WhisperError("GROQ_API_KEY not configured")
        
        try:
            from src.transcription.groq_provider import GroqTranscriptionProvider
            
            logger.info("Using Groq Whisper API")
            provider = GroqTranscriptionProvider(self.settings)
            return provider.transcribe(audio_path, language)
        except Exception as e:
            logger.error(f"Groq API transcription failed: {e}")
            raise WhisperError(f"Transcription failed: {e}")
