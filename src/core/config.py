"""Configuration settings for the Transcription Pipeline."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore[attr-defined]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and config.yaml."""

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

    # Rate Limiting Configuration
    rate_limiting_enabled: bool = True
    rate_limiting_min_delay: float = 2.0
    rate_limiting_max_delay: float = 5.0
    rate_limiting_retry_delay: float = 10.0
    rate_limiting_max_retries: int = 3

    # YouTube API Configuration
    youtube_api_use_cookies: bool = True
    youtube_api_cookie_cache_hours: int = 24
    youtube_api_timeout: int = 30
    youtube_api_languages: list[str] = ["en", "en-US", "en-GB"]

    # Batch Configuration
    batch_default_size: int = 5
    batch_show_progress: bool = True

    # Convenience properties
    @property
    def work_dir(self) -> Path:
        """Get work directory as Path."""
        return Path(self.pipeline_work_dir)

    @property
    def cache_dir(self) -> Path:
        """Get cache directory as Path."""
        return Path(self.pipeline_cache_dir)

    @property
    def rate_limiting_delay_range(self) -> tuple[float, float]:
        """Get rate limiting delay range as tuple."""
        return (self.rate_limiting_min_delay, self.rate_limiting_max_delay)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def load_yaml_config(config_path: Path | str | None = None) -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file. Defaults to ./config.yaml or ./config.yml

    Returns:
        Dictionary with configuration values
    """
    if config_path is None:
        # Try default locations
        possible_paths = [
            Path("config.yaml"),
            Path("config.yml"),
            Path(__file__).parent.parent.parent / "config.yaml",
            Path(__file__).parent.parent.parent / "config.yml",
        ]
        for path in possible_paths:
            if path.exists():
                config_path = path
                break

    if config_path is None or not Path(config_path).exists():
        return {}

    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: Failed to load config file: {e}")
        return {}


def apply_yaml_config(settings: Settings, config: dict) -> Settings:
    """
    Apply YAML configuration to settings object.

    Environment variables take precedence over YAML config.

    Args:
        settings: Settings object to update
        config: Configuration dictionary from YAML

    Returns:
        Updated Settings object
    """
    # Rate limiting
    if "rate_limiting" in config:
        rl = config["rate_limiting"]
        if "enabled" in rl and not settings.rate_limiting_enabled:
            settings.rate_limiting_enabled = rl["enabled"]
        if "min_delay" in rl and settings.rate_limiting_min_delay == 2.0:
            settings.rate_limiting_min_delay = float(rl["min_delay"])
        if "max_delay" in rl and settings.rate_limiting_max_delay == 5.0:
            settings.rate_limiting_max_delay = float(rl["max_delay"])
        if "retry_delay" in rl and settings.rate_limiting_retry_delay == 10.0:
            settings.rate_limiting_retry_delay = float(rl["retry_delay"])
        if "max_retries" in rl and settings.rate_limiting_max_retries == 3:
            settings.rate_limiting_max_retries = int(rl["max_retries"])

    # YouTube API
    if "youtube_api" in config:
        yt = config["youtube_api"]
        if "use_cookies" in yt and not settings.youtube_api_use_cookies:
            settings.youtube_api_use_cookies = yt["use_cookies"]
        if "cookie_cache_hours" in yt and settings.youtube_api_cookie_cache_hours == 24:
            settings.youtube_api_cookie_cache_hours = int(yt["cookie_cache_hours"])
        if "timeout" in yt and settings.youtube_api_timeout == 30:
            settings.youtube_api_timeout = int(yt["timeout"])
        if "languages" in yt:
            settings.youtube_api_languages = yt["languages"]

    # Batch
    if "batch" in config:
        batch = config["batch"]
        if "default_size" in batch and settings.batch_default_size == 5:
            settings.batch_default_size = int(batch["default_size"])
        if "show_progress" in batch:
            settings.batch_show_progress = bool(batch["show_progress"])

    # Whisper
    if "whisper" in config:
        whisper = config["whisper"]
        if "audio_format" in whisper and settings.audio_format == "mp3":
            settings.audio_format = whisper["audio_format"]
        if "audio_bitrate" in whisper and settings.audio_bitrate == "128k":
            settings.audio_bitrate = whisper["audio_bitrate"]
        if "chunk_length" in whisper and settings.whisper_chunk_length == 30:
            settings.whisper_chunk_length = int(whisper["chunk_length"])

    # Pipeline
    if "pipeline" in config:
        pipeline = config["pipeline"]
        if "work_dir" in pipeline and settings.pipeline_work_dir == "/tmp/transcription_pipeline":
            settings.pipeline_work_dir = pipeline["work_dir"]
        if "cache_dir" in pipeline and settings.pipeline_cache_dir == "/tmp/transcription_cache":
            settings.pipeline_cache_dir = pipeline["cache_dir"]
        if "enable_cache" in pipeline:
            settings.pipeline_enable_cache = bool(pipeline["enable_cache"])
        if "save_to_db" in pipeline:
            settings.pipeline_save_to_db = bool(pipeline["save_to_db"])

    return settings


def get_settings_with_yaml(config_path: Path | str | None = None) -> Settings:
    """
    Get settings with YAML configuration applied.

    Priority: Environment Variables > YAML Config > Defaults

    Args:
        config_path: Optional path to config file

    Returns:
        Settings object with YAML configuration applied
    """
    settings = get_settings()
    config = load_yaml_config(config_path)
    return apply_yaml_config(settings, config)
