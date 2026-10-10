"""Transcript summarization grows within a finite resource budget, without text cuts."""
import json

import httpx
import pytest

from app.config import Settings, settings
from app.services import llm_service as service


@pytest.fixture
def adaptive(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(settings, "llm_model", "model")
    monkeypatch.setattr(settings, "llm_summary_strategy", "legacy")
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_object")
    monkeypatch.setattr(settings, "llm_summary_length_mode", "adaptive", raising=False)
    monkeypatch.setattr(settings, "llm_summary_output_token_ceiling", 8192, raising=False)
    monkeypatch.setattr(settings, "llm_summary_point_ceiling", 14, raising=False)
    monkeypatch.setattr(settings, "llm_summary_max_output_tokens", 4096)


def client_for(body, captured):
    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "content": json.dumps(body)}, "finish_reason": "stop"}]})
    return httpx.Client(transport=httpx.MockTransport(respond))


def test_default_length_mode_is_adaptive():
    assert Settings().llm_summary_length_mode == "adaptive"


def test_long_transcript_can_keep_more_themes_and_complete_long_points(adaptive):
    captured = []
    points = [f"Theme {i}: " + "necessary condition and consequence; " * 12 for i in range(9)]
    body = {"summary": "Overview. " * 100, "key_points": points}
    with client_for(body, captured) as client:
        result = service.summarize_text("A source detail. " * 1000, title="Lecture", output_language="en", client=client)
    assert result.summary == body["summary"].strip()
    assert result.key_points == [point.strip() for point in points]
    assert len(captured) == 1
    assert 4096 < captured[0]["max_tokens"] <= 8192
    assert "at most seven" not in captured[0]["messages"][1]["content"]
    assert "240 characters" not in captured[0]["messages"][0]["content"]
    assert "fact_ids" not in captured[0]["messages"][0]["content"]


def test_short_source_does_not_get_a_long_source_budget(adaptive):
    captured = []
    with client_for({"summary": "A fact.", "key_points": ["A fact."]}, captured) as client:
        service.summarize_text("A fact.", title="Short", output_language="en", client=client)
    assert captured[0]["max_tokens"] == 4096


def test_budget_growth_is_capped_and_invalid_config_is_rejected(adaptive, monkeypatch):
    profile = service._summary_budget(10**9)
    assert profile.max_tokens == 8192
    assert profile.max_points == 14
    monkeypatch.setattr(settings, "llm_summary_output_token_ceiling", True)
    with pytest.raises(service.LLMServiceError) as error:
        service._summary_budget(10)
    assert error.value.error_type == "llm_unconfigured"


def test_adaptive_schema_has_no_per_point_character_limit(adaptive, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_schema")
    options = service._summary_options(service._summary_budget(30000))
    points = options["text"]["format"]["schema"]["properties"]["key_points"]
    assert "maxLength" not in points["items"]
    assert 7 < points["maxItems"] <= 14


def test_finite_point_limit_still_rejects_without_truncation_or_retry(adaptive):
    captured = []
    with client_for({"summary": "Too many.", "key_points": [str(i) for i in range(15)]}, captured) as client:
        with pytest.raises(service.LLMServiceError):
            service.summarize_text("Detail " * 2500, title="Long", output_language="en", client=client)
    assert len(captured) == 1


def test_merge_budget_uses_original_source_size_not_short_notes(adaptive, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_chunk_chars", 8000)
    captured = []
    def respond(request):
        payload = json.loads(request.content)
        captured.append(payload)
        merge = "Section summaries:" in payload["messages"][1]["content"]
        body = {"summary": "Closing conclusion.", "key_points": [f"Topic {i}" for i in range(9)] if merge else ["Section topic."]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}, "finish_reason": "stop"}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = service.summarize_text("A detail. " * 1600, title="Long", output_language="en", client=client)
    assert len(captured) == 3
    assert len(result.key_points) == 9
    assert captured[-1]["max_tokens"] > captured[0]["max_tokens"]


@pytest.mark.parametrize("kwargs", [
    {"llm_summary_length_mode": "unlimited"},
    {"llm_summary_output_token_ceiling": True},
    {"llm_summary_output_token_ceiling": 1000},
    {"llm_summary_output_token_ceiling": 65537},
    {"llm_summary_point_ceiling": True},
    {"llm_summary_point_ceiling": 33},
])
def test_invalid_adaptive_settings_fail_at_startup(kwargs):
    with pytest.raises(ValueError, match="llm_summary_"):
        Settings(**kwargs)


def test_adaptive_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_LENGTH_MODE", "adaptive")
    monkeypatch.setenv("LLM_SUMMARY_OUTPUT_TOKEN_CEILING", "10000")
    monkeypatch.setenv("LLM_SUMMARY_POINT_CEILING", "18")
    configured = Settings.from_env()
    assert configured.llm_summary_output_token_ceiling == 10000
    assert configured.llm_summary_point_ceiling == 18


@pytest.mark.parametrize("mode", ["adaptive", "fixed"])
def test_existing_larger_base_budget_gets_a_finite_default_ceiling(mode, monkeypatch):
    configured = Settings(llm_summary_length_mode=mode, llm_summary_max_output_tokens=12000)
    assert configured.llm_summary_output_token_ceiling == 12000
    monkeypatch.setenv("LLM_SUMMARY_MAX_OUTPUT_TOKENS", "12000")
    monkeypatch.delenv("LLM_SUMMARY_OUTPUT_TOKEN_CEILING", raising=False)
    assert Settings.from_env().llm_summary_output_token_ceiling == 12000


def test_adaptive_tool_uses_the_same_budget_for_schema_and_parsing(adaptive, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_response_format", "strict_tool")
    captured = []
    long_point = "An essential condition. " * 30
    def respond(request):
        payload = json.loads(request.content)
        captured.append(payload)
        properties = payload["tools"][0]["function"]["parameters"]["properties"]
        arguments = {key: "" for key in properties}
        arguments.update(summary="Lecture overview.", point_1=long_point)
        return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {
            "role": "assistant", "tool_calls": [{"type": "function", "function": {
                "name": "emit_video_summary", "arguments": json.dumps(arguments)}}]}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = service.summarize_text("A detail. " * 1500, title="Lecture", output_language="en", client=client)
    assert result.key_points == [long_point.strip()]
    assert len(captured[0]["tools"][0]["function"]["parameters"]["properties"]) > 8
