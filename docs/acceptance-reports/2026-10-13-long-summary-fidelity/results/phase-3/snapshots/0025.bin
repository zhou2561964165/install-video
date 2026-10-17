"""A fixed review/revision workflow with no telemetry or hidden requests."""
import json

import httpx
import pytest
from langsmith.run_helpers import get_tracing_context

from app.config import Settings, settings
from app.services import llm_service as service


@pytest.fixture
def configured(monkeypatch):
    for key, value in {"llm_base_url": "https://llm.example/v1", "llm_model": "model",
        "llm_provider": "openai-compatible", "llm_summary_strategy": "legacy", "llm_summary_generation_mode": "single",
        "llm_summary_length_mode": "adaptive", "llm_summary_fidelity_mode": "review",
        "llm_summary_review_max_output_tokens": 2048, "llm_summary_max_output_tokens": 4096,
        "llm_summary_output_token_ceiling": 8192, "llm_summary_point_ceiling": 14,
        "llm_summary_response_format": "json_object", "llm_summary_thinking_mode": "disabled",
        "llm_summary_chunk_chars": 120, "llm_max_input_chars": 6000, "llm_summary_max_chunks": 16,
        "llm_summary_notes_language": "source", "llm_summary_source_context_mode": "auto"}.items():
        monkeypatch.setattr(settings, key, value, raising=False)


def draft():
    return service.LLMSummaryResult("A draft overview.", ["A source mechanism with its condition."], "saved", "model")


def client_for(outputs, captured):
    def provider(request):
        body = json.loads(request.content)
        captured.append(body)
        assert get_tracing_context()["enabled"] is False
        response = outputs[len(captured) - 1]
        if isinstance(response, httpx.Response):
            return response
        if isinstance(response, str):
            content = response
        else:
            content = json.dumps(response)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})
    return httpx.Client(transport=httpx.MockTransport(provider))


def evidence(body):
    return json.loads(body["messages"][1]["content"].split("Evidence and draft:\n", 1)[1])


def test_review_feedback_is_carried_to_revision_with_complete_source(configured, monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    source = "A particular example has a limitation.\nOther examples use the category differently.\nAn important closing condition."
    feedback = "Keep the limitation attached to the specific example and restore the closing relationship."
    final = {"summary": "Overview.", "key_points": ["A complete source mechanism and necessary condition."]}
    captured, trace = [], []
    with client_for([{"feedback": feedback}, final], captured) as client:
        result = service.review_summary(source, draft(), title="Title", output_language="zh-CN", client=client, diagnostic=trace.append)
    assert len(captured) == 2 and result.summary == final["summary"] and result.key_points == final["key_points"]
    assert evidence(captured[0])["original_transcript"] == source == evidence(captured[1])["original_transcript"]
    assert evidence(captured[0])["draft"] == evidence(captured[1])["draft"]
    assert evidence(captured[1])["review_feedback"] == feedback
    assert [body["max_tokens"] for body in captured] == [2048, 4096]
    assert [(row["stage"], row["status"]) for row in trace] == [("source_review", "started"), ("source_review", "passed"),
                                                               ("source_revision", "started"), ("source_revision", "passed")]
    assert all("feedback" not in row and "original_transcript" not in row for row in trace)


def test_multisection_default_path_has_two_final_stages_without_repeating_extraction(configured):
    source = "A beginning. " + "conditional evidence " * 8 + "Closing next step."
    outputs = [{"summary": "Leaf.", "key_points": ["Leaf mechanism."]}] * 2 + [
        {"summary": "Draft.", "key_points": ["Draft mechanism."]}, {"feedback": "Preserve the exact source scope."},
        {"summary": "Final.", "key_points": ["Final mechanism and necessary condition."]}]
    captured = []
    with client_for(outputs, captured) as client:
        # Plain map/reduce has no tracing entry; the fixed LCEL final stages do.
        from langsmith import tracing_context
        with tracing_context(enabled=False):
            result = service.summarize_text(source, title="Title", output_language="zh-CN", client=client)
    assert len(captured) == 5 and result.summary == "Final."
    assert "Section summaries:\n" in captured[2]["messages"][1]["content"]
    assert evidence(captured[3])["draft"]["summary"] == "Draft."


def test_single_section_in_review_mode_keeps_one_generation_without_final_stages(configured):
    captured = []
    output = {"summary": "Overview.", "key_points": ["A complete source condition."]}
    from langsmith import tracing_context
    with client_for([output], captured) as client, tracing_context(enabled=False):
        result = service.summarize_text("One short condition.", title="Title", output_language="zh-CN", client=client)
    assert len(captured) == 1 and result.key_points == output["key_points"]
    assert "Transcript:\n" in captured[0]["messages"][1]["content"]


def test_native_schema_review_and_revision_have_distinct_schema_roles(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_schema")
    captured = []
    def provider(request):
        body = json.loads(request.content)
        captured.append(body)
        content = {"feedback": "Preserve the source scope."} if len(captured) == 1 else {"summary": "Overview.", "key_points": ["Condition."]}
        return httpx.Response(200, json={"object": "response", "status": "completed", "output": [{"type": "message", "role": "assistant",
            "status": "completed", "content": [{"type": "output_text", "text": json.dumps(content)}]}]})
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = service.review_summary("Source condition.", draft(), title="Title", output_language="zh-CN", client=client)
    assert result.summary == "Overview." and len(captured) == 2
    assert [set(body["text"]["format"]["schema"]["properties"]) for body in captured] == [{"feedback"}, {"summary", "key_points"}]
    assert [body["max_output_tokens"] for body in captured] == [2048, 4096]


@pytest.mark.parametrize("bad", ["not json", {"feedback": ""}, {"feedback": "   "}, {"feedback": 2},
    {"feedback": "A source finding.", "extra": "Forbidden"}, '{"feedback":"First","feedback":"Second"}', httpx.Response(503)])
def test_bad_review_stops_after_one_request_and_never_revises(configured, bad):
    captured = []
    with client_for([bad], captured) as client:
        with pytest.raises(service.LLMServiceError):
            service.review_summary("Source condition.", draft(), title="Title", output_language="zh-CN", client=client)
    assert len(captured) == 1


def test_review_overflow_does_not_truncate_feedback_or_send_revision(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_max_input_chars", 3000)
    captured = []
    with client_for([{"feedback": "A necessary condition. " * 200}], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.review_summary("Source condition.", draft(), title="Title", output_language="zh-CN", client=client)
    assert error.value.error_type == "llm_input_too_large" and len(captured) == 1


@pytest.mark.parametrize("key,value", [("llm_summary_review_max_output_tokens", True), ("llm_summary_review_max_output_tokens", 0),
    ("llm_summary_review_max_output_tokens", 65537), ("llm_summary_response_format", "strict_tool")])
def test_invalid_review_configuration_has_no_paid_attempt(configured, monkeypatch, key, value):
    monkeypatch.setattr(settings, key, value)
    captured = []
    with client_for([], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text("A initial source condition.", title="Title", output_language="zh-CN", client=client)
    assert error.value.error_type == "llm_unconfigured" and not captured


def test_review_settings_are_finite_and_environment_configurable(monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_FIDELITY_MODE", "review")
    monkeypatch.setenv("LLM_SUMMARY_REVIEW_MAX_OUTPUT_TOKENS", "2048")
    cfg = Settings.from_env()
    assert cfg.llm_summary_fidelity_mode == "review" and cfg.llm_summary_review_max_output_tokens == 2048
    with pytest.raises(ValueError, match="llm_summary_review_max_output_tokens"):
        Settings(llm_summary_review_max_output_tokens=True)
