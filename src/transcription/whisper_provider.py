"""Whisper transcription provider using a configured backend."""

import logging
from src.core.config import get_settings_with_yaml
from src.core.exceptions import WhisperError
from src.core.schemas import RawTranscript

logger = logging.getLogger(__name__)


class WhisperProvider:
    """Provides transcription using the configured backend."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings_with_yaml()

    def transcribe(self, audio_path: str, language: str = "en") -> RawTranscript:
        """Transcribe audio file using the configured backend."""
        backend = getattr(self.settings, "transcription_backend", "groq").lower()

        try:
            if backend == "local_service":
                from src.transcription.local_service_provider import LocalTranscriptServiceProvider

                logger.info("Using local transcript service backend")
                provider = LocalTranscriptServiceProvider(self.settings)
                return provider.transcribe(audio_path, language)

            if not self.settings.groq_api_key:
                raise WhisperError("GROQ_API_KEY not configured")

            from src.transcription.groq_provider import GroqTranscriptionProvider

            logger.info("Using Groq Whisper API")
            provider = GroqTranscriptionProvider(self.settings)
            return provider.transcribe(audio_path, language)
        except Exception as e:
            logger.error("Configured transcription backend failed: %s", e)
            raise WhisperError(f"Transcription failed: {e}")
