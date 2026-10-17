"""Generic regression coverage for category-to-example subject scope guidance."""
import json

import httpx
import pytest

from app.config import settings
from app.services import llm_service as service


@pytest.fixture
def configured(monkeypatch):
    values = {
        "llm_base_url": "https://llm.example/v1",
        "llm_model": "model",
        "llm_provider": "openai-compatible",
        "llm_summary_strategy": "legacy",
        "llm_summary_generation_mode": "single",
        "llm_summary_length_mode": "adaptive",
        "llm_summary_fidelity_mode": "off",
        "llm_summary_response_format": "json_object",
        "llm_summary_thinking_mode": "disabled",
        "llm_summary_max_output_tokens": 4096,
        "llm_summary_output_token_ceiling": 8192,
        "llm_summary_point_ceiling": 14,
        "llm_summary_max_point_chars": 240,
        "llm_summary_chunk_chars": 20000,
        "llm_summary_source_context_chars": 1200,
        "llm_summary_notes_language": "source",
        "llm_summary_source_context_mode": "auto",
        "llm_summary_review_max_output_tokens": 4096,
        "llm_max_input_chars": 60000,
        "llm_summary_max_chunks": 16,
    }
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value, raising=False)


def test_generation_prompt_tracks_subject_after_category_introduces_example(configured):
    source = (
        "A family of instruments can perform different tasks. One example is a meter. "
        "This instrument records duration, while other models also measure distance."
    )
    captured = []

    def provider(request):
        captured.append(json.loads(request.content))
        body = {"summary": "An overview.", "key_points": ["A supported topic."]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}, "finish_reason": "stop"}]})

    budget = service._summary_budget(len(source))
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        service._summary_request(source, title="Source", output_language="en", client=client)

    system = captured[0]["messages"][0]["content"]
    assert "grammatical subject" in system
    assert "demonstrative or pronoun" in system
    assert "category" in system and "specific instance" in system
    assert "calculator" not in system.lower()
    assert budget.max_points == 7


def test_global_theme_editing_guidance_is_only_sent_to_final_merge(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_schema")
    captured = []

    def provider(request):
        captured.append(json.loads(request.content))
        body = {"summary": "A source overview.", "key_points": ["A source condition."]}
        return httpx.Response(200, json={"object": "response", "status": "completed", "output": [{
            "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(body)}],
        }]})

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        for merge in (False, True):
            service._summary_request("A source condition.", title="Source", output_language="en",
                client=client, merge=merge, source_chars=40000)

    assert len(captured) == 2
    leaf, merged = captured
    for guidance in (
        "Organize themes across all section notes",
        "section order does not determine final point order",
        "Do not retain the first section's list and append a few later points",
        "Check the complete source, especially later sections",
        "necessary conditions, conclusions, and transitions",
        "Merge overlapping themes without dropping independent substantive content",
    ):
        assert guidance in merged["input"][-1]["content"]
        assert guidance not in leaf["input"][-1]["content"]
    assert merged["instructions"] == leaf["instructions"]
    assert merged["text"] == leaf["text"]
    assert merged["max_output_tokens"] == leaf["max_output_tokens"] == 8192
    schema = merged["text"]["format"]["schema"]
    assert schema["properties"]["key_points"]["maxItems"] == 14


def test_review_and_revision_prompts_compare_source_and_draft_subject_scope(configured, monkeypatch):
    source = "A group has varied capabilities. One example is a meter. This instrument measures duration."
    draft = {"summary": "An overview.", "key_points": ["The entire group measures duration."]}
    budget = service._summary_budget(len(source))
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "checks")
    feedback = "The source predicate applies to one instance; the draft applies it to the whole group."

    revision = service._summary_revision_messages(
        source, draft, title="Source", output_language="en", budget=budget, feedback=feedback,
    )
    review = service._summary_review_messages(source, draft, title="Source", output_language="en")

    assert "grammatical subject and scope in the source" in revision[0]["content"]
    assert "draft subject" in revision[0]["content"]
    assert "source subject and draft subject" in review[0]["content"]
    assert "source subject" in review[0]["content"]
    assert "draft subject" in review[0]["content"]
    assert "one correct clause does not validate a different clause" in review[0]["content"]
    assert "calculator" not in revision[0]["content"].lower()
    assert "calculator" not in review[0]["content"].lower()


def test_checks_request_uses_finite_responses_schema_and_one_revision(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "checks")
    source = "An example belongs to a family. This meter measures duration."
    draft = service.LLMSummaryResult(
        "An overview of the family.", ["A meter in the example measures duration."], "saved", "model",
    )
    checks = {
        "target_0": {
            "assessment": "supported",
            "source_quote": "An example belongs to a family.",
            "finding": "No scope mismatch found.",
        },
        "target_1": {
            "assessment": "supported",
            "source_quote": "This meter measures duration.",
            "finding": "The predicate stays with the example.",
        },
    }
    final = {"summary": draft.summary, "key_points": draft.key_points}
    captured = []

    def provider(request):
        body = json.loads(request.content)
        captured.append((request.url.path, body))
        if request.url.path.endswith("/responses"):
            payload = {"object": "response", "status": "completed", "output": [{
                "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(checks)}],
            }]}
        else:
            payload = {"choices": [{"message": {"content": json.dumps(final)}, "finish_reason": "stop"}]}
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = service.review_summary(source, draft, title="Source", output_language="en", client=client)

    assert result.key_points == final["key_points"] and len(captured) == 2
    path, review_body = captured[0]
    assert path.endswith("/responses")
    assert review_body["max_output_tokens"] == 640
    schema = review_body["text"]["format"]["schema"]
    assert set(schema["properties"]) == {"target_0", "target_1"}
    assert review_body["text"]["format"]["type"] == "json_schema"
    revision_path, revision_body = captured[1]
    assert revision_path.endswith("/chat/completions")
    assert "Target 0" in revision_body["messages"][1]["content"]
    assert "Target 1" in revision_body["messages"][1]["content"]
    assert checks["target_1"]["finding"] in revision_body["messages"][1]["content"]


def test_full_multisection_checks_path_has_bounded_arity_and_default_14_point_budget(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "checks")
    source = "A beginning. " + "A source detail. " * 2100 + "A closing condition."
    points = [f"Supported thematic point {index}." for index in range(1, 15)]
    draft = {"summary": "A source overview.", "key_points": points}
    checks = {
        f"target_{index}": {
            "assessment": "supported",
            "source_quote": "A source detail." if index else "A beginning.",
            "finding": "No material issue found.",
        }
        for index in range(15)
    }
    captured = []

    def provider(request):
        body = json.loads(request.content)
        path = request.url.path
        captured.append((path, body))
        if path.endswith("/responses"):
            response = {"object": "response", "status": "completed", "output": [{
                "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(checks)}],
            }]}
        else:
            call_index = sum(1 for prior_path, _ in captured if prior_path.endswith("/chat/completions"))
            output = draft if call_index >= 3 else {"summary": "A section overview.", "key_points": ["A section fact."]}
            response = {"choices": [{"message": {"content": json.dumps(output)}, "finish_reason": "stop"}]}
        return httpx.Response(200, json=response)

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = service.summarize_text(source, title="Source", output_language="en", client=client)

    assert result.key_points == points
    assert ["responses" if path.endswith("/responses") else "chat/completions" for path, _ in captured] == [
        "chat/completions", "chat/completions", "chat/completions", "responses", "chat/completions",
    ]
    assert captured[3][1]["max_output_tokens"] == 3968
    assert set(captured[3][1]["text"]["format"]["schema"]["properties"]) == {f"target_{index}" for index in range(15)}


@pytest.mark.parametrize("failure,expected_error", [
    ("incomplete", "llm_incomplete_response"),
    ("failed", "llm_error"),
    ("refusal", "llm_invalid_response"),
])
def test_checks_responses_failure_stops_after_one_request(configured, monkeypatch, failure, expected_error):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "checks")
    draft = service.LLMSummaryResult("An overview.", ["A source detail."], "saved", "model")
    captured = []

    def provider(request):
        captured.append(request.url.path)
        if failure == "refusal":
            response = {"object": "response", "status": "completed", "output": [{
                "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "refusal", "refusal": "Not available."}],
            }]}
        else:
            response = {"object": "response", "status": failure, "output": []}
        return httpx.Response(200, json=response)

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.review_summary("A source detail.", draft, title="Source", output_language="en", client=client)

    assert error.value.error_type == expected_error, str(error.value)
    assert captured == ["/v1/responses"]


def test_checks_output_budget_over_limit_is_rejected_before_request(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "checks")
    monkeypatch.setattr(settings, "llm_summary_review_max_output_tokens", 639)
    draft = service.LLMSummaryResult("A brief overview.", ["One key point."], "saved", "model")
    requests = []

    def provider(request):
        requests.append(request)
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.review_summary("A source claim.", draft, title="Source", output_language="en", client=client)

    assert error.value.error_type == "llm_unconfigured"
    assert requests == []


def test_multi_section_checks_budget_is_rejected_before_first_leaf(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "checks")
    monkeypatch.setattr(settings, "llm_summary_review_max_output_tokens", 639)
    source = "A heading. " + "A supported source detail. " * 900
    requests = []

    def provider(request):
        requests.append(request)
        body = {"summary": "An overview.", "key_points": ["A supported topic."]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}, "finish_reason": "stop"}]})

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text(source, title="Source", output_language="en", client=client)

    assert error.value.error_type == "llm_unconfigured"
    assert requests == []


def test_single_section_checks_mode_does_not_require_review_budget(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "checks")
    monkeypatch.setattr(settings, "llm_summary_review_max_output_tokens", 639)
    requests = []

    def provider(request):
        requests.append(request)
        body = {"summary": "An overview.", "key_points": ["A source detail."]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}, "finish_reason": "stop"}]})

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = service.summarize_text("A short source detail.", title="Source", output_language="en", client=client)

    assert result.summary == "An overview."
    assert len(requests) == 1
