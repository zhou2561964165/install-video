from pathlib import Path

import pytest

from app.config import Settings, settings


def test_settings_defaults():
    s = Settings()
    assert s.max_concurrent_downloads == 3
    assert s.ttl_seconds == 3600
    assert s.network_retries == 2
    assert s.network_retry_backoff_seconds == 0.5
    assert isinstance(s.temp_dir, Path)
    assert s.db_url.startswith("sqlite:///")


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT", "5")
    monkeypatch.setenv("TTL_SECONDS", "60")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_MAX_INPUT_CHARS", "12345")
    monkeypatch.setenv("NETWORK_RETRIES", "4")
    monkeypatch.setenv("NETWORK_RETRY_BACKOFF_SECONDS", "1.25")
    s = Settings.from_env()
    assert s.max_concurrent_downloads == 5
    assert s.ttl_seconds == 60
    assert s.llm_model == "test-model"
    assert s.llm_max_input_chars == 12345
    assert s.network_retries == 4
    assert s.network_retry_backoff_seconds == 1.25


@pytest.mark.parametrize(
    ("settings_values", "message"),
    [
        ({"network_retries": -1}, "network_retries must be >= 0"),
        (
            {"network_retry_backoff_seconds": -0.01},
            "network_retry_backoff_seconds must be finite and >= 0",
        ),
        (
            {"network_retry_backoff_seconds": float("nan")},
            "network_retry_backoff_seconds must be finite and >= 0",
        ),
        (
            {"network_retry_backoff_seconds": float("inf")},
            "network_retry_backoff_seconds must be finite and >= 0",
        ),
        (
            {"network_retry_backoff_seconds": float("-inf")},
            "network_retry_backoff_seconds must be finite and >= 0",
        ),
    ],
)
def test_settings_reject_invalid_network_retry_configuration(settings_values, message):
    with pytest.raises(ValueError, match=message):
        Settings(**settings_values)


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


def test_summary_output_controls_are_loaded_from_env(monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_RESPONSE_FORMAT", "json_object")
    monkeypatch.setenv("LLM_SUMMARY_THINKING_MODE", "disabled")
    configured = Settings.from_env()
    assert configured.llm_summary_response_format == "json_object"
    assert configured.llm_summary_thinking_mode == "disabled"


@pytest.mark.parametrize("name,value", [
    ("LLM_SUMMARY_RESPONSE_FORMAT", "yaml"),
    ("LLM_SUMMARY_RESPONSE_FORMAT", "enabled"),
    ("LLM_SUMMARY_THINKING_MODE", "text"),
    ("LLM_SUMMARY_THINKING_MODE", "sometimes"),
])
def test_invalid_summary_output_controls_fail_at_startup(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match="llm_summary_"):
        Settings.from_env()


def test_schema_summary_controls_are_loaded_from_env(monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_RESPONSE_FORMAT", "json_schema")
    monkeypatch.setenv("LLM_SUMMARY_MAX_POINT_CHARS", "180")
    configured = Settings.from_env()
    assert configured.llm_summary_response_format == "json_schema"
    assert configured.llm_summary_max_point_chars == 180


@pytest.mark.parametrize("value", [0, -1])
def test_schema_point_length_must_be_positive(value):
    with pytest.raises(ValueError, match="llm_summary_max_point_chars"):
        Settings(llm_summary_max_point_chars=value)


def test_summary_source_context_configuration_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_SOURCE_CONTEXT_CHARS", "0")
    assert Settings.from_env().llm_summary_source_context_chars == 0
    with pytest.raises(ValueError, match="llm_summary_source_context_chars"):
        Settings(llm_summary_source_context_chars=-1)


def test_grounded_summary_controls_load_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_STRATEGY", "facts")
    monkeypatch.setenv("LLM_SUMMARY_FACTS_MAX_SOURCE_CHARS", "35000")
    monkeypatch.setenv("LLM_SUMMARY_FACTS_CHUNK_CHARS", "6000")
    monkeypatch.setenv("LLM_SUMMARY_FACTS_MAX_PER_CHUNK", "8")
    monkeypatch.setenv("LLM_SUMMARY_FACTS_MAX_EVIDENCE_SENTENCES", "16")
    configured = Settings.from_env()
    assert configured.llm_summary_strategy == "facts"
    assert configured.llm_summary_facts_max_source_chars == 35000
    assert configured.llm_summary_facts_chunk_chars == 6000
    assert configured.llm_summary_facts_max_per_chunk == 8
    assert configured.llm_summary_facts_max_evidence_sentences == 16


@pytest.mark.parametrize("changes", [
    {"llm_summary_strategy": "retry"},
    {"llm_summary_facts_max_source_chars": 0},
    {"llm_summary_facts_max_source_chars": True},
    {"llm_summary_facts_chunk_chars": 0},
    {"llm_summary_facts_chunk_chars": True},
    {"llm_summary_facts_max_per_chunk": 0},
    {"llm_summary_facts_max_per_chunk": 100},
    {"llm_summary_facts_max_evidence_sentences": 0},
    {"llm_summary_facts_max_evidence_sentences": 257},
])
def test_grounded_configuration_rejects_invalid_limits(changes):
    with pytest.raises(ValueError, match="llm_summary_"):
        Settings(**changes)


def test_grounded_organization_limits_load_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_FACTS_MAX_SUMMARY_CHARS", "650")
    monkeypatch.setenv("LLM_SUMMARY_FACTS_COMPOSE_MAX_OUTPUT_TOKENS", "8192")
    monkeypatch.setenv("LLM_SUMMARY_FACTS_AUDIT_MAX_OUTPUT_TOKENS", "10000")
    configured = Settings.from_env()
    assert configured.llm_summary_facts_max_summary_chars == 650
    assert configured.llm_summary_facts_compose_max_output_tokens == 8192
    assert configured.llm_summary_facts_audit_max_output_tokens == 10000


@pytest.mark.parametrize("changes", [
    {"llm_summary_facts_max_summary_chars": 0},
    {"llm_summary_facts_max_summary_chars": 4001},
    {"llm_summary_facts_compose_max_output_tokens": -1},
    {"llm_summary_facts_audit_max_output_tokens": True},
    {"llm_summary_facts_audit_max_output_tokens": 65537},
])
def test_grounded_organization_rejects_invalid_configuration(changes):
    with pytest.raises(ValueError, match="llm_summary_facts"):
        Settings(**changes)
