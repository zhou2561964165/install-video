"""Bounded complete checks are guardrails, never semantic certification."""
import json

import httpx
import pytest
from app.services import summary_review as review
from app.services import llm_service as service
from app.config import settings
from test_summary_source_review import configured

SOURCE = "A particular device supports addition. It cannot do other tasks."
DRAFT = {"summary": "The video explains a device.", "key_points": ["The category supports only addition."]}


def checks():
    return {
        "target_0": {"assessment": "supported", "source_quote": "A particular device",
                     "finding": "The overview names the example."},
        "target_1": {"assessment": "needs_correction", "source_quote": "A particular device supports addition.",
                     "finding": "Preserve the particular example's scope instead of generalizing its category."}}


def test_complete_review_binds_reordered_slots_to_actual_draft():
    value = dict(reversed(list(checks().items())))
    result = review.parse_checks(value, source=SOURCE, draft=DRAFT)
    assert result.index("Target 0") < result.index("Target 1")
    assert DRAFT["summary"] in result and DRAFT["key_points"][0] in result
    for item in value.values():
        assert all(item[field] in result for field in ("assessment", "source_quote", "finding"))


@pytest.mark.parametrize("fault", ["missing", "extra_target", "old_array", "wrong_source", "extra_field",
    "target_number", "draft_quote", "invalid_assessment", "bool_assessment", "empty_quote", "empty_finding",
    "long_quote", "long_finding", "nonstring_quote", "nonstring_finding", "stitched_quote"])
def test_invalid_slot_or_unbound_quote_cannot_be_accepted(fault):
    value = checks()
    if fault == "missing":
        value.pop("target_1")
    elif fault == "extra_target":
        value["target_2"] = value["target_1"].copy()
    elif fault == "old_array":
        value = {"checks": list(value.values())}
    else:
        field, replacement = {
            "wrong_source": ("source_quote", "A sentence that was never supplied."),
            "extra_field": ("answer", "Unrequested field"),
            "target_number": ("target", 1),
            "draft_quote": ("draft_quote", DRAFT["key_points"][0]),
            "invalid_assessment": ("assessment", "accurate"),
            "bool_assessment": ("assessment", True),
            "empty_quote": ("source_quote", "   "),
            "empty_finding": ("finding", "   "),
            "long_quote": ("source_quote", "a" * 121),
            "long_finding": ("finding", "a" * 81),
            "nonstring_quote": ("source_quote", 1),
            "nonstring_finding": ("finding", ["Unrequested list"]),
            "stitched_quote": ("source_quote", "A particular device ... other tasks."),
        }[fault]
        value["target_1"][field] = replacement
    with pytest.raises(ValueError):
        review.parse_checks(value, source=SOURCE, draft=DRAFT)


def test_only_whitespace_is_normalized_for_contiguous_quote_origin():
    value = checks()
    value["target_1"]["source_quote"] = "A particular\n device supports addition."
    result = review.parse_checks(value, source=SOURCE, draft=DRAFT)
    assert value["target_1"]["source_quote"] in result


def test_field_length_boundaries_retain_complete_content():
    value = checks()
    value["target_1"]["source_quote"] = "a" * 120
    value["target_1"]["finding"] = "b" * 80
    result = review.parse_checks(value, source=SOURCE + " " + "a" * 120, draft=DRAFT)
    assert "a" * 120 in result and "b" * 80 in result


def test_uncertain_assessment_is_retained_without_semantic_success():
    value = checks()
    value["target_1"]["assessment"] = "uncertain"
    value["target_1"]["finding"] = "The category scope is unresolved."
    result = review.parse_checks(value, source=SOURCE, draft=DRAFT)
    assert "uncertain" in result and "The category scope is unresolved." in result


def test_schema_has_exact_draft_slots_and_bounded_assessment_records():
    for count in (1, 7, 14, 32):
        schema = review.checks_schema(count)
        keys = {f"target_{i}" for i in range(count + 1)}
        assert set(schema["properties"]) == set(schema["required"]) == keys
        assert schema["additionalProperties"] is False
        item = schema["$defs"]["SourceCheck"]
        assert set(item["properties"]) == set(item["required"]) == {"assessment", "source_quote", "finding"}
        assert item["additionalProperties"] is False
        assert set(item["properties"]["assessment"]["enum"]) == {"supported", "needs_correction", "uncertain"}
        assert item["properties"]["source_quote"]["minLength"] == 1
        assert item["properties"]["source_quote"]["maxLength"] == 120
        assert item["properties"]["finding"]["minLength"] == 1
        assert item["properties"]["finding"]["maxLength"] == 80


@pytest.mark.parametrize("point_count,expected", [(1, 640), (7, 2176), (14, 3968), (32, 8576)])
def test_output_token_allowance_scales_with_all_actual_targets(point_count, expected):
    assert review.checks_output_tokens(point_count) == expected


@pytest.mark.parametrize("point_count", [0, 33, True, 1.0, "1"])
def test_schema_and_token_allowance_reject_invalid_point_counts(point_count):
    with pytest.raises(ValueError):
        review.checks_schema(point_count)
    with pytest.raises(ValueError):
        review.checks_output_tokens(point_count)


@pytest.fixture
def configured_checks(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "checks")
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_schema")


def native_client(outputs, captured):
    def provider(request):
        captured.append(json.loads(request.content))
        output = outputs[len(captured) - 1]
        content = output if isinstance(output, str) else json.dumps(output)
        return httpx.Response(200, json={"object": "response", "status": "completed", "output": [
            {"type": "message", "role": "assistant", "status": "completed",
             "content": [{"type": "output_text", "text": content}]}]})
    return httpx.Client(transport=httpx.MockTransport(provider))


def evidence(body):
    return json.loads(body["input"][0]["content"].split("Evidence and draft:\n", 1)[1])


def test_two_calls_carry_bound_complete_checks_and_native_schema(configured_checks):
    draft = service.LLMSummaryResult(DRAFT["summary"], DRAFT["key_points"], "saved", "model")
    final = {"summary": DRAFT["summary"], "key_points": ["The particular device supports addition."]}
    captured = []
    with native_client([checks(), final], captured) as client:
        result = service.review_summary(SOURCE, draft, title="Title", output_language="en", client=client)
    assert len(captured) == 2 and result.key_points == final["key_points"]
    feedback = evidence(captured[1])["review_feedback"]
    assert "Target 0" in feedback and "Target 1" in feedback
    assert DRAFT["summary"] in feedback and DRAFT["key_points"][0] in feedback
    assert checks()["target_1"]["finding"] in feedback
    assert evidence(captured[0])["original_transcript"] == evidence(captured[1])["original_transcript"] == SOURCE
    assert set(captured[0]["text"]["format"]["schema"]["properties"]) == {"target_0", "target_1"}


@pytest.mark.parametrize("fault", ["missing", "false_quote", "extra_target", "long_finding",
    "duplicate_json_key", "duplicate_nested_json_key"])
def test_invalid_model_checks_stop_after_first_attempt(configured_checks, fault):
    value = checks()
    if fault == "missing":
        value.pop("target_1")
    elif fault == "false_quote":
        value["target_1"]["source_quote"] = "Not in the source."
    elif fault == "extra_target":
        value["target_2"] = value["target_1"].copy()
    elif fault == "long_finding":
        value["target_1"]["finding"] = "a" * 81
    elif fault == "duplicate_json_key":
        value = json.dumps(value)[:-1] + ',"target_0":' + json.dumps(value["target_0"]) + "}"
    else:
        value = json.dumps(value).replace(
            '"assessment": "needs_correction"',
            '"assessment": "supported", "assessment": "needs_correction"', 1,
        )
    captured = []
    with native_client([value], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.review_summary(SOURCE, service.LLMSummaryResult(DRAFT["summary"], DRAFT["key_points"], "saved", "model"),
                                   title="Title", output_language="en", client=client)
    assert error.value.error_type == "llm_invalid_response" and len(captured) == 1
