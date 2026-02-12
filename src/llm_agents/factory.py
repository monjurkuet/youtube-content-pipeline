"""LLM client factory for creating API clients."""


from openai import OpenAI

from src.core.config import get_settings


class LLMClientFactory:
    """Factory for creating LLM API clients."""

    _instance: OpenAI | None = None

    @classmethod
    def get_client(cls) -> OpenAI:
        """Get or create OpenAI-compatible client."""
        if cls._instance is None:
            settings = get_settings()
            cls._instance = OpenAI(
                base_url=settings.llm_api_base,
                api_key=settings.llm_api_key,
                timeout=90.0,
            )
        return cls._instance

    @classmethod
    def reset_client(cls):
        """Reset the client (useful for testing)."""
        cls._instance = None


def get_llm_client() -> OpenAI:
    """Get the global LLM client instance."""
    return LLMClientFactory.get_client()
