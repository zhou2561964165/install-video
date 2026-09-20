from pathlib import Path
from app.config import Settings, settings


def test_settings_defaults():
    s = Settings()
    assert s.max_concurrent_downloads == 3
    assert s.ttl_seconds == 3600
    assert isinstance(s.temp_dir, Path)
    assert s.db_url.startswith("sqlite:///")


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT", "5")
    monkeypatch.setenv("TTL_SECONDS", "60")
    s = Settings.from_env()
    assert s.max_concurrent_downloads == 5
    assert s.ttl_seconds == 60


def test_global_settings_is_settings():
    assert isinstance(settings, Settings)
