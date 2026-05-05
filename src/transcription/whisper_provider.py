"""Whisper transcription provider with multi-backend fallback chain.

Instead of a single if/else backend selection, this provider builds an
ordered chain of available transcription backends and tries each one
in sequence until one succeeds. This ensures that a single provider
outage (e.g., Groq 429 rate limit) doesn't kill the entire pipeline.

Fallback order (when TRANSCRIPTION_BACKEND=groq, the default):
  1. Groq Whisper API (cloud, rate-limited)
  2. whisper.cpp local server (localhost:8334, unlimited)
  3. Local transcript service (custom job-queue, if configured)

When TRANSCRIPTION_BACKEND=local_service:
  1. Local transcript service
  2. whisper.cpp local server
  3. Groq Whisper API
"""

import logging
from typing import Protocol

from src.core.config import get_settings_with_yaml
from src.core.exceptions import WhisperError
from src.core.schemas import RawTranscript

logger = logging.getLogger(__name__)


class TranscriptionBackend(Protocol):
    """Protocol for transcription backends in the fallback chain."""

    name: str

    def transcribe(self, audio_path: str, language: str = "en") -> RawTranscript: ...


class WhisperProvider:
    """Provides transcription using a fallback chain of backends.

    The chain is ordered by the TRANSCRIPTION_BACKEND setting (primary first),
    with the other providers as fallbacks. Each provider is only included if
    it's available (API key configured, server reachable, etc.).

    Example:
        >>> provider = WhisperProvider()
        >>> # Tries Groq first, then whisper.cpp if Groq fails
        >>> result = provider.transcribe("/path/to/audio.mp3")
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings_with_yaml()
        self._chain: list[TranscriptionBackend] = self._build_provider_chain()

    def _build_provider_chain(self) -> list[TranscriptionBackend]:
        """Build an ordered list of available providers.

        The primary provider (based on TRANSCRIPTION_BACKEND) goes first,
        followed by fallback providers in priority order.

        Returns:
            List of initialized transcription backends.

        Raises:
            WhisperError: If no providers are available at all.
        """
        providers: list[TranscriptionBackend] = []
        backend = getattr(self.settings, "transcription_backend", "groq").lower()

        # Build all candidate providers
        groq = self._try_make_groq()
        whispercpp = self._try_make_whispercpp()
        local_service = self._try_make_local_service()

        if backend == "local_service":
            # Primary: custom local service, Fallback: whisper.cpp, then Groq
            if local_service:
                providers.append(local_service)
            if whispercpp:
                providers.append(whispercpp)
            if groq:
                providers.append(groq)
        else:
            # Default: Primary is Groq, Fallback: whisper.cpp, then local service
            if groq:
                providers.append(groq)
            if whispercpp:
                providers.append(whispercpp)
            if local_service:
                providers.append(local_service)

        if not providers:
            raise WhisperError(
                "No transcription providers available. "
                "Configure GROQ_API_KEY, ensure whisper.cpp is running, "
                "or set up the local transcript service."
            )

        provider_names = [p.name for p in providers]
        logger.info("Transcription fallback chain: %s", " → ".join(provider_names))
        return providers

    def _try_make_groq(self) -> TranscriptionBackend | None:
        """Try to create a Groq provider. Returns None if not configured."""
        try:
            from src.transcription.groq_provider import GroqTranscriptionProvider

            provider = GroqTranscriptionProvider(self.settings)
            # _load_api_key raises WhisperError if key is missing
            return provider
        except WhisperError:
            logger.debug("Groq provider not available: API key not configured")
            return None

    def _try_make_whispercpp(self) -> TranscriptionBackend | None:
        """Try to create a whisper.cpp provider. Returns None if server is down."""
        try:
            from src.transcription.whispercpp_provider import WhisperCppProvider

            base_url = getattr(
                self.settings, "whispercpp_base_url", "http://localhost:8334"
            )
            timeout_sec = getattr(
                self.settings, "whispercpp_timeout_sec", 600
            )
            provider = WhisperCppProvider(
                base_url=base_url,
                timeout_sec=timeout_sec,
            )
            if provider.is_available():
                logger.debug("whisper.cpp provider available at %s", base_url)
                return provider
            logger.debug("whisper.cpp server not reachable at %s", base_url)
            return None
        except Exception as exc:
            logger.debug("whisper.cpp provider init failed: %s", exc)
            return None

    def _try_make_local_service(self) -> TranscriptionBackend | None:
        """Try to create a local service provider. Returns None if not configured."""
        try:
            from src.transcription.local_service_provider import (
                LocalTranscriptServiceProvider,
            )

            return LocalTranscriptServiceProvider(self.settings)
        except WhisperError:
            logger.debug("Local service provider not available: not configured")
            return None

    def transcribe(self, audio_path: str, language: str = "en") -> RawTranscript:
        """Transcribe audio using the provider fallback chain.

        Tries each provider in order. If a provider raises WhisperError,
        moves on to the next. If all providers fail, raises WhisperError.

        Args:
            audio_path: Path to the audio file to transcribe.
            language: Language code for transcription (default: "en").

        Returns:
            RawTranscript from the first successful provider.

        Raises:
            WhisperError: If all providers in the chain fail.
        """
        if not self._chain:
            raise WhisperError("No transcription providers available")

        last_error: Exception | None = None
        for provider in self._chain:
            try:
                logger.info("Trying transcription provider: %s", provider.name)
                result = provider.transcribe(audio_path, language)
                logger.info("Provider %s succeeded", provider.name)
                return result
            except WhisperError as exc:
                logger.warning(
                    "Provider %s failed: %s — trying next in chain",
                    provider.name,
                    exc,
                )
                last_error = exc
                continue
            except Exception as exc:
                logger.warning(
                    "Provider %s unexpected error: %s — trying next in chain",
                    provider.name,
                    exc,
                )
                last_error = exc
                continue

        raise WhisperError(
            f"All {len(self._chain)} transcription providers failed. "
            f"Last error: {last_error}"
        )
