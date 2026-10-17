"""A bounded revision stage: preserve source and account for one real request."""
import json

import httpx
import pytest

from app.config import Settings, settings
from app.services import llm_service as service


@pytest.fixture
def configured(monkeypatch):
    values = {"llm_base_url": "https://llm.example/v1", "llm_provider": "openai-compatible",
              "llm_model": "model", "llm_summary_strategy": "legacy", "llm_summary_generation_mode": "single",
              "llm_summary_length_mode": "adaptive", "llm_summary_fidelity_mode": "long",
              "llm_summary_response_format": "json_object", "llm_summary_thinking_mode": "disabled",
              "llm_summary_chunk_chars": 120, "llm_summary_max_chunks": 16, "llm_max_input_chars": 6000,
              "llm_summary_max_output_tokens": 4096, "llm_summary_output_token_ceiling": 8192,
              "llm_summary_point_ceiling": 14, "llm_summary_source_context_chars": 8,
              "llm_summary_notes_language": "source", "llm_summary_source_context_mode": "auto"}
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value, raising=False)


def draft():
    return service.LLMSummaryResult("A source overview.", ["An accurate conditional mechanism."], "saved", "model")


def client_for(responses, captured):
    def provider(request):
        captured.append(json.loads(request.content))
        value = responses[len(captured) - 1]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, httpx.Response):
            return value
        return httpx.Response(200, json={"model": "model", "choices": [{"message": {"content": json.dumps(value)},
                                                                     "finish_reason": "stop"}]})
    return httpx.Client(transport=httpx.MockTransport(provider))


def test_complete_source_and_draft_are_passed_without_deleting_claims(configured):
    source = "Earlier context.\nRepeated phrase.\nLater context.\nRepeated phrase.\nA necessary end condition."
    expected = {"summary": "A corrected overview.", "key_points": ["A complete mechanism with its condition."]}
    captured, trace = [], []
    with client_for([expected], captured) as client:
        result = service.refine_summary(source, draft(), title="Title", output_language="zh-CN",
                                        client=client, diagnostic=trace.append)
    evidence = json.loads(captured[0]["messages"][1]["content"].split("Evidence and draft:\n", 1)[1])
    assert evidence["original_transcript"] == source
    assert evidence["draft"] == {"summary": draft().summary, "key_points": draft().key_points}
    assert list(evidence) == ["original_transcript", "draft"]
    assert result.summary == expected["summary"] and result.key_points == expected["key_points"]
    assert result.provider == settings.llm_provider and result.model == "model"
    assert len(captured) == 1 and captured[0]["max_tokens"] == 4096
    assert [(row["stage"], row["status"]) for row in trace] == [("source_revision", "started"), ("source_revision", "passed")]
    assert all("original_transcript" not in row and "draft" not in row for row in trace)


def test_multiple_sections_generate_then_revise_exactly_once(configured):
    source = "A beginning. " + "conditional evidence " * 8 + "Closing next step."
    chunks = service._summary_chunks(source, 120)
    assert len(chunks) == 2
    outputs = [{"summary": "Leaf.", "key_points": ["Leaf mechanism."]}] * 2 + [
        {"summary": "Draft.", "key_points": ["Draft mechanism."]},
        {"summary": "Final.", "key_points": ["Final mechanism and closing condition."]}]
    captured = []
    with client_for(outputs, captured) as client:
        result = service.summarize_text(source, title="Title", output_language="zh-CN", client=client)
    assert len(captured) == 4 and result.summary == "Final."
    evidence = json.loads(captured[-1]["messages"][1]["content"].split("Evidence and draft:\n", 1)[1])
    assert evidence["original_transcript"] == source
    assert evidence["draft"]["summary"] == "Draft."
    assert "Section summaries:\n" in captured[2]["messages"][1]["content"]


@pytest.mark.parametrize("fidelity,source,expected_calls", [("off", "detail " * 27, 3), ("long", "Short condition.", 1)])
def test_disabled_or_single_section_does_not_add_a_call(configured, monkeypatch, fidelity, source, expected_calls):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", fidelity)
    captured = []
    output = {"summary": "Overview.", "key_points": ["Mechanism."]}
    with client_for([output] * expected_calls, captured) as client:
        service.summarize_text(source, title="Title", output_language="zh-CN", client=client)
    assert len(captured) == expected_calls


@pytest.mark.parametrize("key,value", [("llm_summary_fidelity_mode", "invalid"), ("llm_summary_fidelity_mode", True),
    ("llm_summary_strategy", "facts"), ("llm_summary_generation_mode", "staged"), ("llm_summary_length_mode", "fixed")])
def test_incompatible_policy_is_rejected_before_any_post(configured, monkeypatch, key, value):
    monkeypatch.setattr(settings, key, value)
    captured = []
    with client_for([], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text("An initial source condition.", title="Title", output_language="zh-CN", client=client)
    assert error.value.error_type == "llm_unconfigured" and not captured


def test_long_source_that_cannot_fit_revision_is_rejected_before_leaf_post(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_max_input_chars", 350)
    captured = []
    with client_for([], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text("A long condition. " * 40, title="Title", output_language="zh-CN", client=client)
    assert error.value.error_type == "llm_input_too_large" and not captured


def test_actual_draft_capacity_is_checked_without_truncation(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_max_input_chars", 600)
    oversized = service.LLMSummaryResult("overview " * 100, ["A necessary condition."], "saved", "model")
    captured = []
    with client_for([], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.refine_summary("Source condition.", oversized, title="Title", output_language="zh-CN", client=client)
    assert error.value.error_type == "llm_input_too_large" and not captured


def test_revision_capacity_includes_fixed_system_guidance(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_max_input_chars", 800)
    captured = []
    output = {"summary": "Overview.", "key_points": ["A source condition."]}
    with client_for([output], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.refine_summary("A source condition.", draft(), title="Title", output_language="zh-CN", client=client)
    assert error.value.error_type == "llm_input_too_large" and not captured


@pytest.mark.parametrize("response_format", ["json_schema", "strict_tool"])
def test_revision_reuses_existing_native_structured_transports(configured, monkeypatch, response_format):
    monkeypatch.setattr(settings, "llm_summary_response_format", response_format)
    captured = []
    output = {"summary": "A corrected overview.", "key_points": ["A complete source condition."]}
    def provider(request):
        body = json.loads(request.content)
        captured.append((request.url.path, body))
        if response_format == "json_schema":
            response = {"object": "response", "status": "completed", "output": [{"type": "message", "role": "assistant",
                        "status": "completed", "content": [{"type": "output_text", "text": json.dumps(output)}]}]}
        else:
            arguments = {"summary": output["summary"], **{f"point_{i}": output["key_points"][0] if i == 1 else "" for i in range(1, 8)}}
            response = {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "tool_calls": [{
                        "type": "function", "function": {"name": "emit_video_summary", "arguments": json.dumps(arguments)}}]}}]}
        return httpx.Response(200, json=response)
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = service.refine_summary("A source condition.", draft(), title="Title", output_language="zh-CN", client=client)
    assert result.summary == output["summary"] and result.key_points == output["key_points"]
    assert len(captured) == 1
    path, body = captured[0]
    if response_format == "json_schema":
        assert path == "/v1/responses" and body["text"]["format"]["schema"]["properties"]["key_points"]["maxItems"] == 7
        assert "original_transcript" in body["input"][0]["content"] and body["max_output_tokens"] == 4096
    else:
        assert path == "/v1/chat/completions" and body["tools"][0]["function"]["name"] == "emit_video_summary"
        assert body["max_tokens"] == 4096


@pytest.mark.parametrize("bad", [None, service.LLMSummaryResult("", ["Fact."], "saved", "model"),
    service.LLMSummaryResult("Overview.", [], "saved", "model"),
    service.LLMSummaryResult("Overview.", ["Fact."] * 15, "saved", "model")])
def test_unusable_draft_is_rejected_without_post(configured, bad):
    captured = []
    with client_for([], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.refine_summary("Source condition.", bad, title="Title", output_language="zh-CN", client=client)
    assert error.value.error_type == "llm_invalid_response" and not captured


@pytest.mark.parametrize("failure", [httpx.ConnectError("offline"), httpx.Response(503), {"summary": "Overview.", "key_points": []}])
def test_revision_errors_stop_after_one_post_without_returning_old_draft(configured, failure):
    captured, trace = [], []
    with client_for([failure], captured) as client:
        with pytest.raises(service.LLMServiceError):
            service.refine_summary("Source condition.", draft(), title="Title", output_language="zh-CN",
                                   client=client, diagnostic=trace.append)
    assert len(captured) == 1
    assert [row["status"] for row in trace] == ["started", "failed"]


def test_revision_setting_is_opt_in_and_loaded_from_environment(monkeypatch):
    assert Settings().llm_summary_fidelity_mode == "off"
    monkeypatch.setenv("LLM_SUMMARY_FIDELITY_MODE", "long")
    assert Settings.from_env().llm_summary_fidelity_mode == "long"
    with pytest.raises(ValueError, match="llm_summary_fidelity_mode"):
        Settings(llm_summary_fidelity_mode="bad")
