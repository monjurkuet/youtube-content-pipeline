"""Tests for YAML settings isolation behavior."""

from pathlib import Path

from src.core.config import get_settings, get_settings_with_yaml


def test_get_settings_with_yaml_does_not_mutate_cached_settings(tmp_path: Path) -> None:
    """Applying YAML should not mutate the cached Settings singleton."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "\n".join(
            [
                "batch:",
                "  default_size: 42",
                "ytdlp:",
                "  download_timeout_sec: 777",
            ]
        )
    )

    base = get_settings(force_reload=True)
    assert base.batch_default_size == 5
    assert base.ytdlp_download_timeout_sec == 300

    yaml_settings = get_settings_with_yaml(cfg)
    assert yaml_settings.batch_default_size == 42
    assert yaml_settings.ytdlp_download_timeout_sec == 777

    # Cached singleton remains untouched
    cached = get_settings()
    assert cached.batch_default_size == 5
    assert cached.ytdlp_download_timeout_sec == 300
