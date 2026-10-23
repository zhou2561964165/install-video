"""Codec/serialization regressions; these tests do not score model semantics."""
import json

import pytest

from app.config import settings
from app.services import llm_service as service


def test_schema_presents_points_before_overview(monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_schema")
    monkeypatch.setattr(settings, "llm_summary_thinking_mode", "disabled")
    schema = service._summary_options(include_editorial=True)["text"]["format"]["schema"]
    assert list(schema["properties"]) == ["key_points", "summary", "title", "conclusion"]
    assert schema["required"] == ["key_points", "summary"]
    legacy = service._summary_options()["text"]["format"]["schema"]
    assert list(legacy["properties"]) == ["key_points", "summary"]


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("points", [[1], [True], [None], [{}], [["nested"]]])
def test_codec_never_coerces_non_string_points(strict, points):
    from app.services.summary_output import decode_payload
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        decode_payload({"summary": "overview", "key_points": points}, strict=strict)


def test_codec_preserves_nonempty_content_and_serialization_order():
    from app.services.summary_output import decode_payload
    point = "每节课评价；通常课后反馈；讲者相信努力有助于技能。" * 30
    payload = {"summary": "  讲者的教学实践  ", "key_points": [point], "legacy_extra": "ignored"}
    decoded = decode_payload(payload)
    assert decoded.summary == payload["summary"]
    assert decoded.key_points == [point]
    assert list(decoded.model_dump()) == ["key_points", "summary", "title", "conclusion"]
    assert decoded.title == decoded.conclusion == ""


def test_compat_drops_empty_points_before_counting_budget():
    payload = {"summary": " overview ", "key_points": ["point"] * 7 + [" \n "]}
    assert service._parse_summary_json(json.dumps(payload)) == ("overview", ["point"] * 7)


@pytest.mark.parametrize("strict,accepted", [(False, True), (True, False)])
def test_extra_fields_follow_existing_modes(strict, accepted):
    raw = json.dumps({"summary": "overview", "key_points": ["point"], "extra": "data"})
    if accepted:
        assert service._parse_summary_json(raw, strict=strict) == ("overview", ["point"])
    else:
        with pytest.raises(service.LLMServiceError) as error:
            service._parse_summary_json(raw, strict=strict)
        assert error.value.error_type == "llm_invalid_response"


def test_strict_raw_length_check_precedes_strip_and_adaptive_retains_long_points():
    raw = json.dumps({"summary": " overview ", "key_points": [" point "]})
    with pytest.raises(service.LLMServiceError):
        service._parse_summary_json(raw, strict=True, budget=service._SummaryBudget(100, 7, 5))
    assert service._parse_summary_json(raw, strict=True, budget=service._SummaryBudget(100, 7, None)) == (
        "overview", ["point"])


def test_single_generation_shape_and_raw_source_survive_without_extra_post(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://fixture.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "fixture-only")
    monkeypatch.setattr(settings, "llm_provider", "compatible")
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_object")
    monkeypatch.setattr(settings, "llm_summary_thinking_mode", "disabled")
    source = "A speaker may evaluate every session.\nThey believe effort matters."
    calls = []
    class Client:
        def post(self, url, headers, json):
            import httpx
            calls.append(json)
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
                "content": '{"key_points":["fixture point"],"summary":"fixture overview"}'}}]},
                request=httpx.Request("POST", url))
    result = service._summary_request(source, title="Source", output_language="en", client=Client())
    assert result.summary == "fixture overview" and result.key_points == ["fixture point"]
    assert len(calls) == 1
    assert calls[0]["messages"][-1]["content"].endswith(source)
    # Check the documented wire example as JSON, not an exact prose prompt.
    example = calls[0]["messages"][0]["content"].split("Example JSON shape", 1)[1].split(": ", 1)[1]
    assert list(json.loads(example)) == ["key_points", "summary", "title", "conclusion"]


@pytest.mark.parametrize("response_format", ["json_object", "json_schema"])
def test_editorial_fields_and_markdown_topics_survive_one_generation(monkeypatch, response_format):
    import httpx

    for name, value in {
        "llm_base_url": "https://fixture.invalid/v1", "llm_model": "fixture-only",
        "llm_provider": "compatible", "llm_summary_response_format": response_format,
        "llm_summary_thinking_mode": "disabled", "llm_summary_length_mode": "adaptive",
    }.items():
        monkeypatch.setattr(settings, name, value)
    body = {
        "title": "  Conditions determine the result  ",
        "summary": "The source relates a condition to an outcome.",
        "key_points": ["## Conditions and outcome\n\nAn explanation.\n\n### A separate stage\n\nA qualified result."],
        "conclusion": "  The outcome remains conditional.  ",
    }
    captured = []

    def provider(request):
        payload = json.loads(request.content)
        captured.append(payload)
        raw = json.dumps(body)
        if response_format == "json_schema":
            result = {"object": "response", "status": "completed", "output": [{
                "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": raw}],
            }]}
        else:
            result = {"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}
        return httpx.Response(200, json=result)

    source = "A condition leads to an outcome in the given situation."
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = service._summary_request(source, title="Video", output_language="en", client=client)
    assert len(captured) == 1
    assert result.title == body["title"].strip()
    assert result.conclusion == body["conclusion"].strip()
    assert result.summary == body["summary"]
    assert result.key_points == body["key_points"]
    payload = captured[0]
    user = (payload["input"] if response_format == "json_schema" else payload["messages"])[-1]["content"]
    assert user.endswith(source)
    assert "## topic heading" in user and "### subheadings only when" in user
    assert "If the source is too limited for a distinct synthesis" in user


@pytest.mark.parametrize("field", ["title", "conclusion"])
def test_editorial_fields_never_coerce_non_strings_or_leak_raw_values(field):
    raw = json.dumps({"summary": "overview", "key_points": ["point"], field: {"private": "raw"}})
    with pytest.raises(service.LLMServiceError) as error:
        service._parse_summary_json(raw, strict=True)
    assert error.value.error_type == "llm_invalid_response"
    assert "private" not in str(error.value)
