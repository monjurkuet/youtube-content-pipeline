"""Configuration settings for the Transcription Pipeline."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore[attr-defined]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(  # type: ignore[assignment]
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Allow extra env vars not defined in model
    )

    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "video_pipeline"

    # Audio Processing
    audio_format: str = "mp3"
    audio_bitrate: str = "128k"

    # OpenVINO / Whisper Settings
    openvino_whisper_model: str = "openai/whisper-base"
    openvino_device: str = "AUTO"  # AUTO, GPU, CPU
    openvino_cache_dir: str = "~/.cache/whisper_openvino"
    whisper_chunk_length: int = 30  # seconds

    # Pipeline Settings
    pipeline_work_dir: str = "/tmp/transcription_pipeline"
    pipeline_cache_dir: str = "/tmp/transcription_cache"
    pipeline_enable_cache: bool = True
    pipeline_save_to_db: bool = True

    # Convenience properties
    @property
    def work_dir(self) -> Path:
        """Get work directory as Path."""
        return Path(self.pipeline_work_dir)

    @property
    def cache_dir(self) -> Path:
        """Get cache directory as Path."""
        return Path(self.pipeline_cache_dir)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
