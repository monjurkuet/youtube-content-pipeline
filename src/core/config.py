"""Configuration settings for the LLM-driven Video Content Pipeline."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "video_pipeline"

    # LLM API Configuration
    llm_api_base: str = "http://localhost:8087/v1"
    llm_api_key: str = "sk-dummy"

    # Model Selection for LLM-Driven Pipeline
    llm_transcript_model: str = "gemini-2.5-flash"  # Agent 1: Transcript Intelligence
    llm_frame_model: str = "qwen3-vl-plus"  # Agent 2: Frame Intelligence
    llm_synthesis_model: str = "gemini-2.5-flash"  # Agent 3: Synthesis

    # Legacy model setting (for backward compatibility)
    llm_model: str = "qwen3-vl-plus"
    gemini_model: str = "gemini-2.5-flash"

    # LLM Timeouts (seconds)
    transcript_timeout: int = 60
    frame_timeout: int = 90
    synthesis_timeout: int = 60

    # Retries
    max_retries: int = 3
    retry_delay: float = 2.0

    # LLM Schema Repair (fallback for validation errors)
    enable_llm_repair: bool = True  # Enable LLM-based schema repair
    llm_repair_max_attempts: int = 1  # Max repair attempts per validation failure
    llm_repair_temperature: float = 0.1  # Low temp for precise repairs

    # Video Processing
    video_resolution: str = "720p"  # 720p for faster download
    video_format: str = "best[height<=720][ext=mp4]/best[height<=720]"
    video_frame_quality: int = 2  # ffmpeg quality (2=high)

    # Legacy visual settings
    visual_max_frames: int = 20
    visual_scene_threshold: float = 0.3
    visual_fallback_interval: int = 30
    visual_resolution: str = "720p"
    visual_temp_dir: str = "/tmp/video_analysis"

    # Frame Extraction (LLM-Driven)
    frame_batch_size: int = 15
    max_frames_to_extract: int = 20
    target_frames_to_keep: int = 8
    default_coverage_interval: int = 180  # seconds

    # Audio Processing
    audio_format: str = "mp3"
    audio_bitrate: str = "128k"

    # OpenVINO / Whisper Settings
    openvino_whisper_model: str = "openai/whisper-base"
    openvino_device: str = "AUTO"  # AUTO, GPU, CPU
    openvino_cache_dir: str = "~/.cache/whisper_openvino"
    whisper_chunk_length: int = 30  # seconds

    # Pipeline Settings
    pipeline_work_dir: str = "/tmp/llm_video_analysis"
    pipeline_cache_dir: str = "/tmp/llm_analysis_cache"
    pipeline_enable_cache: bool = True
    pipeline_save_to_db: bool = True
    pipeline_retry_frames_individually: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra env vars not defined in model

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
