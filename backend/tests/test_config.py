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
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_MAX_INPUT_CHARS", "12345")
    s = Settings.from_env()
    assert s.max_concurrent_downloads == 5
    assert s.ttl_seconds == 60
    assert s.llm_model == "test-model"
    assert s.llm_max_input_chars == 12345


def test_global_settings_is_settings():
    assert isinstance(settings, Settings)


def test_default_paths_are_anchored_not_cwd_relative():
    s = Settings()
    # temp_dir 默认是绝对路径（锚定到 backend/），而非相对启动 CWD 的 "backend/tmp"
    assert s.temp_dir.is_absolute()
    assert s.temp_dir.name == "tmp"
    # db_url 默认不再指向相对 CWD 的 ./jobs.db，而是锚定到 backend/jobs.db
    assert "jobs.db" in s.db_url
    assert "./jobs.db" not in s.db_url
