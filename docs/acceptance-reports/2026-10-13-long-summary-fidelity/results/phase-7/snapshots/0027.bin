"""Subject and scope checks bind review fields to one source and draft target."""
import json

import httpx
import pytest

from app.config import Settings, settings
from app.services import llm_service as service
from app.services import summary_review as review
from test_summary_source_review import configured


SOURCE = (
    "A fixed-program computer is a category. This calculator is one example. "
    "It only knows how to do addition, multiplication, subtraction, division."
)
DRAFT = {
    "summary": "A fixed-program computer is a category.",
    "key_points": ["Fixed-program computers only know the four arithmetic operations."],
}


def subject_checks():
    return {
        "target_0": {
            "assessment": "supported",
            "scope_relation": "same",
            "source_subject": "A fixed-program computer",
            "draft_subject": "A fixed-program computer",
            "source_quote": "A fixed-program computer is a category.",
            "finding": "The overview keeps the source scope.",
        },
        "target_1": {
            "assessment": "needs_correction",
            "scope_relation": "draft_broader",
            "source_subject": "This calculator",
            "draft_subject": "Fixed-program computers",
            "source_quote": "This calculator is one example. It only knows how to do addition, multiplication, subtraction, division.",
            "finding": "The source limit belongs to one example, not the category.",
        },
    }


def test_subject_check_schema_requires_bound_subject_and_scope_fields():
    builder = getattr(review, "subject_checks_schema", None)
    assert callable(builder), "Phase-7 subject/scope schema is not implemented"
    schema = builder(1)
    expected = {"assessment", "scope_relation", "source_subject", "draft_subject", "source_quote", "finding"}
    target = schema["$defs"]["SubjectCheck"]
    assert set(target["required"]) == set(target["properties"]) == expected
    assert set(target["properties"]["scope_relation"]["enum"]) == {
        "same", "draft_broader", "draft_narrower", "uncertain"
    }


def test_subject_checks_bind_relation_evidence_and_actual_draft_targets():
    parser = getattr(review, "parse_subject_checks", None)
    assert callable(parser), "Phase-7 subject/scope parser is not implemented"
    payload = dict(reversed(list(subject_checks().items())))
    feedback = parser(payload, source=SOURCE, draft=DRAFT)
    assert feedback.index("Target 0") < feedback.index("Target 1")
    for field in ("assessment", "scope_relation", "source_subject", "draft_subject", "source_quote", "finding"):
        assert subject_checks()["target_1"][field] in feedback
    assert DRAFT["key_points"][0] in feedback


@pytest.mark.parametrize("mutation", [
    "missing_target", "extra_target", "missing_field", "extra_field", "source_subject_unbound", "draft_subject_unbound",
    "quote_not_source", "quote_case_changed", "stitched_quote", "supported_with_null_source", "supported_with_null_draft",
    "supported_with_broader_scope", "uncertain_scope_marked_supported", "source_subject_without_quote",
    "empty_subject", "invalid_relation", "nonstring_subject", "long_subject",
])
def test_subject_checks_reject_invalid_or_cross_bound_fields(mutation):
    parser = getattr(review, "parse_subject_checks", None)
    assert callable(parser), "Phase-7 subject/scope parser is not implemented"
    value = subject_checks()
    target = value["target_1"]
    if mutation == "missing_target":
        value.pop("target_1")
    elif mutation == "extra_target":
        value["target_2"] = target.copy()
    elif mutation == "missing_field":
        target.pop("scope_relation")
    elif mutation == "extra_field":
        target["claim_id"] = "P1"
    elif mutation == "source_subject_unbound":
        target["source_subject"] = "A fixed-program computer"
    elif mutation == "draft_subject_unbound":
        target["draft_subject"] = "unrelated devices"
    elif mutation == "quote_not_source":
        target["source_quote"] = "A different calculator is faster."
    elif mutation == "quote_case_changed":
        target["source_quote"] = target["source_quote"].replace("This calculator", "this calculator")
    elif mutation == "stitched_quote":
        target["source_quote"] = "This calculator is one example ... division."
    elif mutation == "supported_with_null_source":
        target.update(assessment="supported", source_quote=None, source_subject=None, scope_relation="same")
    elif mutation == "supported_with_null_draft":
        target.update(assessment="supported", draft_subject=None, scope_relation="same")
    elif mutation == "supported_with_broader_scope":
        target["assessment"] = "supported"
    elif mutation == "uncertain_scope_marked_supported":
        target.update(assessment="supported", scope_relation="uncertain")
    elif mutation == "source_subject_without_quote":
        target.update(source_quote=None, source_subject="This calculator", scope_relation="uncertain", assessment="uncertain")
    elif mutation == "empty_subject":
        target["source_subject"] = "   "
    elif mutation == "invalid_relation":
        target["scope_relation"] = "equivalent"
    elif mutation == "nonstring_subject":
        target["draft_subject"] = 4
    else:
        target["source_subject"] = "x" * 65

    with pytest.raises(ValueError):
        parser(value, source=SOURCE, draft=DRAFT)


def test_null_subject_path_remains_uncertain_without_programmatic_repair():
    parser = getattr(review, "parse_subject_checks", None)
    assert callable(parser), "Phase-7 subject/scope parser is not implemented"
    value = subject_checks()
    value["target_1"].update(
        assessment="uncertain", scope_relation="uncertain", source_subject=None,
        draft_subject="Fixed-program computers", source_quote="It only knows how to do addition, multiplication, subtraction, division.",
        finding="The pronoun antecedent is outside the bounded quote.",
    )
    feedback = parser(value, source=SOURCE, draft=DRAFT)
    assert "Assessment: uncertain" in feedback
    assert "Source subject: null" in feedback
    assert "Draft subject: Fixed-program computers" in feedback


def test_missing_source_assertion_preserves_null_evidence_without_becoming_supported():
    parser = getattr(review, "parse_subject_checks", None)
    assert callable(parser), "Phase-7 subject/scope parser is not implemented"
    value = subject_checks()
    value["target_1"].update(
        assessment="needs_correction", scope_relation="uncertain", source_subject=None,
        draft_subject="Fixed-program computers", source_quote=None,
        finding="The source contains no matching assertion.",
    )
    feedback = parser(value, source=SOURCE, draft=DRAFT)
    assert "Assessment: needs_correction" in feedback
    assert "Scope relation (draft vs source): uncertain" in feedback
    assert "Source subject: null" in feedback and "Original evidence: null" in feedback


def test_subject_quote_normalizes_line_breaks_but_preserves_inline_whitespace():
    parser = getattr(review, "parse_subject_checks", None)
    assert callable(parser), "Phase-7 subject/scope parser is not implemented"
    value = subject_checks()
    source = SOURCE.replace("This calculator is", "This\ncalculator is")
    value["target_1"]["source_quote"] = value["target_1"]["source_quote"].replace(
        "This calculator is", "This\ncalculator is")
    parser(value, source=source, draft=DRAFT)

    value["target_1"]["source_quote"] = value["target_1"]["source_quote"].replace(
        "This\ncalculator is", "This  calculator is")
    with pytest.raises(ValueError):
        parser(value, source=source, draft=DRAFT)


@pytest.mark.parametrize("count,expected", [(1, 1152), (14, 7808), (32, 17024)])
def test_subject_checks_output_budget_scales_with_every_target(count, expected):
    budget = getattr(review, "subject_checks_output_tokens", None)
    assert callable(budget), "Phase-7 subject/scope output budget is not implemented"
    assert budget(count) == expected


def test_subject_check_settings_accept_explicit_candidate_and_finite_default(monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_FIDELITY_MODE", "subject_checks")
    monkeypatch.delenv("LLM_SUMMARY_SUBJECT_CHECKS_MAX_OUTPUT_TOKENS", raising=False)
    configured = Settings.from_env()
    assert configured.llm_summary_fidelity_mode == "subject_checks"
    assert configured.llm_summary_subject_checks_max_output_tokens == 8192
    assert configured.llm_summary_review_max_output_tokens == 4096


@pytest.mark.parametrize("value", [True, 0, 65537])
def test_subject_check_output_cap_rejects_invalid_configuration(value):
    with pytest.raises(ValueError, match="llm_summary_subject_checks_max_output_tokens"):
        Settings(llm_summary_subject_checks_max_output_tokens=value)


def test_subject_checks_use_native_schema_then_pass_bound_findings_to_one_revision(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "subject_checks", raising=False)
    monkeypatch.setattr(settings, "llm_summary_subject_checks_max_output_tokens", 8192, raising=False)
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_object", raising=False)
    captured = []
    final = {"summary": "An overview.", "key_points": ["The example has a local limit."]}

    def provider(request):
        body = json.loads(request.content)
        captured.append((request.url.path, body))
        if request.url.path.endswith("/responses"):
            content = subject_checks()
            response = {"object": "response", "status": "completed", "output": [{
                "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(content)}],
            }]}
        else:
            response = {"choices": [{"message": {"content": json.dumps(final)}, "finish_reason": "stop"}]}
        return httpx.Response(200, json=response)

    draft = service.LLMSummaryResult(DRAFT["summary"], DRAFT["key_points"], "saved", "model")
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = service.review_summary(SOURCE, draft, title="Title", output_language="en", client=client)

    assert result.summary == final["summary"] and result.key_points == final["key_points"]
    assert [path for path, _ in captured] == ["/v1/responses", "/v1/chat/completions"]
    review_body, revision_body = captured[0][1], captured[1][1]
    assert review_body["max_output_tokens"] == 1152
    assert review_body["text"]["format"]["type"] == "json_schema"
    assert set(review_body["text"]["format"]["schema"]["properties"]) == {"target_0", "target_1"}
    revision_text = revision_body["messages"][1]["content"]
    assert "Scope relation (draft vs source): draft_broader" in revision_text
    assert "Source subject: This calculator" in revision_text
    assert "Draft subject: Fixed-program computers" in revision_text
    assert "The source limit belongs to one example, not the category." in revision_text


def test_subject_checks_budget_overflow_rejects_multisection_before_first_request(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "subject_checks", raising=False)
    monkeypatch.setattr(settings, "llm_summary_subject_checks_max_output_tokens", 7807, raising=False)
    source = "Opening. " + "A detailed repeated source passage. " * 1500
    captured = []

    def provider(request):
        captured.append(request)
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text(source, title="Title", output_language="en", client=client)
    assert error.value.error_type == "llm_unconfigured"
    assert "主体范围核查目标数超过已配置输出预算" in str(error.value)
    assert captured == []


def test_saved_draft_fourteen_point_budget_accepts_7808_and_rejects_7807(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "subject_checks", raising=False)
    monkeypatch.setattr(settings, "llm_max_input_chars", 60_000, raising=False)
    source = "A specific source supports a distinct claim. " * 800
    points = [f"A specific source supports a distinct claim {index}." for index in range(14)]
    draft_payload = {"summary": "A specific source supports a distinct claim.", "key_points": points}
    records = {
        f"target_{index}": {
            "assessment": "supported", "scope_relation": "same",
            "source_subject": "A specific source", "draft_subject": "A specific source",
            "source_quote": "A specific source supports a distinct claim.", "finding": "No scoped mismatch.",
        }
        for index in range(15)
    }
    final = draft_payload
    calls = []

    def provider(request):
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path.endswith("/responses"):
            response = {"object": "response", "status": "completed", "output": [{
                "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(records)}],
            }]}
        else:
            response = {"choices": [{"message": {"content": json.dumps(final)}, "finish_reason": "stop"}]}
        return httpx.Response(200, json=response)

    draft = service.LLMSummaryResult(draft_payload["summary"], points, "saved", "model")
    monkeypatch.setattr(settings, "llm_summary_subject_checks_max_output_tokens", 7808, raising=False)
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = service.review_summary(source, draft, title="Title", output_language="en", client=client)
    assert len(calls) == 2 and calls[0][1]["max_output_tokens"] == 7808
    assert set(calls[0][1]["text"]["format"]["schema"]["properties"]) == {f"target_{i}" for i in range(15)}
    assert len(result.key_points) == 14

    calls.clear()
    monkeypatch.setattr(settings, "llm_summary_subject_checks_max_output_tokens", 7807, raising=False)
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.review_summary(source, draft, title="Title", output_language="en", client=client)
    assert error.value.error_type == "llm_unconfigured" and calls == []


@pytest.mark.parametrize("invalid_response", ["quote", "duplicate_json_target"])
def test_invalid_subject_checks_response_stops_after_single_review_request(configured, monkeypatch, invalid_response):
    monkeypatch.setattr(settings, "llm_summary_fidelity_mode", "subject_checks", raising=False)
    monkeypatch.setattr(settings, "llm_summary_subject_checks_max_output_tokens", 8192, raising=False)
    captured = []

    def provider(request):
        captured.append(request.url.path)
        if invalid_response == "duplicate_json_target":
            invalid = subject_checks()
            encoded = json.dumps(invalid)
            content = encoded[:-1] + ",\"target_0\":" + json.dumps(invalid["target_0"]) + "}"
        else:
            invalid = subject_checks()
            invalid["target_1"]["source_quote"] = "This calculator is paraphrased rather than quoted."
            content = json.dumps(invalid)
        response = {"object": "response", "status": "completed", "output": [{
            "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": content}],
        }]}
        return httpx.Response(200, json=response)

    draft = service.LLMSummaryResult(DRAFT["summary"], DRAFT["key_points"], "saved", "model")
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.review_summary(SOURCE, draft, title="Title", output_language="en", client=client)
    assert error.value.error_type == "llm_invalid_response"
    assert captured == ["/v1/responses"]
