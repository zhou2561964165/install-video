"""Literal vendor fixtures exercise the real HTTP and codec boundaries."""
import copy
import json
import subprocess
import sys
from pathlib import Path
import httpx
import pytest

from app.config import settings
from app.services.llm_service import LLMServiceError, summarize_text
from test_grounded_pipeline import configured, SOURCE, FACT, CANDIDATE, AUDIT, extraction_response


@pytest.fixture(autouse=True)
def retries(configured, monkeypatch):
    for name, value in {"llm_summary_format_retries": 1, "llm_summary_semantic_retries": 1,
                        "llm_summary_max_extra_calls": 2}.items():
        monkeypatch.setattr(settings, name, value, raising=False)


def invoke(responses, requests, traces=None):
    def respond(request):
        requests.append(json.loads(request.content))
        assert len(requests) <= len(responses), "Unexpected paid attempt"
        response = responses[len(requests) - 1]
        if isinstance(response, Exception):
            raise response
        if isinstance(response, int):
            return httpx.Response(response, json={})
        content = response if isinstance(response, str) else json.dumps(response)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        return summarize_text(SOURCE, title="Policy", output_language="en", client=client,
                              diagnostic=traces.append if traces is not None else None)


def body(request):
    return json.loads(request["messages"][1]["content"])


def test_paragraph_and_string_points_normalize_locally_before_the_planned_audit():
    requests, traces = [], []
    raw = {"summary": SOURCE, "key_points": [SOURCE]}
    result = invoke([extraction_response([FACT]), raw, AUDIT], requests, traces)
    assert result.summary == SOURCE and len(requests) == 3
    assert body(requests[2])["candidate"]["summary"] == CANDIDATE["summary"]
    assert body(requests[2])["candidate"]["key_points"][0]["text"] == SOURCE
    assert body(requests[2])["candidate"]["key_points"][0]["fact_ids"] == ["F1_1"]
    assert traces[-1]["retry_budget"]["used"] == 0


def test_unresolved_composer_goes_to_original_audit_with_complete_source_bank():
    requests = []
    raw = {"summary": "Unrelated weather patterns.", "key_points": ["Unknown evening schedule."]}
    invoke([extraction_response([FACT]), raw, AUDIT], requests)
    audit = body(requests[2])
    assert len(requests) == 3 and audit["candidate"]["summary"][0]["fact_ids"] == []
    assert audit["reference_status"]["unresolved"] == ["S1", "P1"]
    assert audit["facts"][0]["claim"] == SOURCE
    assert audit["sources"][0]["text"] == "[1] " + SOURCE


def test_format_repair_preserves_raw_and_stage_input_and_does_not_restart_extraction():
    requests, traces = [], []
    raw = '{"summary": null, "key_points": []}'
    invoke([extraction_response([FACT]), raw, CANDIDATE, AUDIT], requests, traces)
    assert len(requests) == 4
    repair = body(requests[2])
    assert repair["repair"]["category"] == "format"
    assert repair["repair"]["previous_response"] == raw
    assert repair["facts"] == body(requests[1])["facts"]
    assert traces[-1]["retry_budget"]["format_used"] == 1


def test_negative_audit_gets_one_targeted_revision_and_never_publishes_negative():
    bad = copy.deepcopy(AUDIT)
    bad["checks"][1]["supported"] = False
    requests = []
    invoke([extraction_response([FACT]), CANDIDATE, bad, AUDIT], requests)
    assert len(requests) == 4
    revision = body(requests[3])
    assert revision["repair"]["category"] == "semantic"
    assert revision["repair"]["failed_items"] == ["P1"]
    assert json.loads(revision["repair"]["previous_response"]) == bad
    assert revision["sources"] == body(requests[2])["sources"]


@pytest.mark.parametrize("setting,responses,count", [
    ("llm_summary_format_retries", [extraction_response([FACT]), "invalid"], 2),
    ("llm_summary_semantic_retries", [extraction_response([FACT]), CANDIDATE,
        {**AUDIT, "checks": [{**check, "supported": False} for check in AUDIT["checks"]]}], 3),
])
def test_disabled_category_stops_before_additional_paid_attempt(monkeypatch, setting, responses, count):
    monkeypatch.setattr(settings, setting, 0)
    requests = []
    with pytest.raises(LLMServiceError):
        invoke(responses, requests)
    assert len(requests) == count


def test_two_categories_share_maximum_two_additional_calls():
    bad = copy.deepcopy(AUDIT)
    bad["checks"][0]["scope_preserved"] = False
    requests, traces = [], []
    with pytest.raises(LLMServiceError):
        invoke([extraction_response([FACT]), "bad", CANDIDATE, bad, bad], requests, traces)
    assert len(requests) == 5 and traces[-1]["retry_budget"]["used"] == 2
    assert traces[-1]["status"] == "failed"


@pytest.mark.parametrize("response", [503, httpx.ConnectError("offline")])
def test_provider_and_network_failure_do_not_retry(response):
    requests = []
    with pytest.raises(LLMServiceError):
        invoke([response], requests)
    assert len(requests) == 1


def test_illegal_audit_source_stops_before_any_repair():
    bad = copy.deepcopy(AUDIT)
    bad["additional_facts"] = [{**FACT, "source_id": "invented"}]
    requests, traces = [], []
    with pytest.raises(LLMServiceError):
        invoke([extraction_response([FACT]), CANDIDATE, bad], requests, traces)
    assert len(requests) == 3 and traces[-1]["error_category"] == "source"


def test_invalid_budget_is_validated_before_first_paid_request(monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_max_extra_calls", 3)
    requests = []
    with pytest.raises(LLMServiceError) as exc:
        invoke([], requests)
    assert exc.value.error_type == "llm_unconfigured" and requests == []


def test_final_string_output_is_normalized_without_inventing_checks():
    requests = []
    audit = {**AUDIT, "output": {"summary": SOURCE, "key_points": [SOURCE]}}
    result = invoke([extraction_response([FACT]), CANDIDATE, audit], requests)
    assert result.key_points == [SOURCE] and len(requests) == 3


def test_audit_missing_checks_remains_a_failure_and_gets_no_true_flags(monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_format_retries", 0)
    requests = []
    with pytest.raises(LLMServiceError):
        invoke([extraction_response([FACT]), CANDIDATE,
                {"additional_facts": [], "output": CANDIDATE}], requests)
    assert len(requests) == 3


def test_wrong_check_type_is_format_repair_and_false_check_is_semantic():
    malformed = copy.deepcopy(AUDIT)
    malformed["checks"][0]["supported"] = "true"
    requests = []
    invoke([extraction_response([FACT]), CANDIDATE, malformed, AUDIT], requests)
    assert body(requests[3])["repair"]["category"] == "format"


@pytest.mark.parametrize("checks", [[], [{**AUDIT["checks"][0], "item_id": "unknown"}, AUDIT["checks"][1]]])
def test_missing_or_misidentified_check_records_are_format_repairs(checks):
    requests = []
    invoke([extraction_response([FACT]), CANDIDATE, {**AUDIT, "checks": checks}, AUDIT], requests)
    assert body(requests[3])["repair"]["category"] == "format"


def test_final_unresolved_output_gets_targeted_revision_not_public_result():
    unresolved = {**AUDIT, "output": {"summary": "Unrelated climate observations.",
                                     "key_points": ["Unknown district weather."]}}
    requests = []
    invoke([extraction_response([FACT]), CANDIDATE, unresolved, AUDIT], requests)
    assert body(requests[3])["repair"]["reason"] == "unresolved_references"
    assert body(requests[3])["repair"]["failed_items"] == ["S1", "P1"]


def test_repair_capacity_counts_complete_previous_response_and_does_not_send_or_truncate(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_input_chars", 12000)
    raw = 'invalid ' + 'x' * 13000
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as exc:
        invoke([extraction_response([FACT]), raw], requests, traces)
    assert exc.value.error_type == "llm_input_too_large"
    assert len(requests) == 2 and traces[-1]["error_category"] == "capacity"
    assert traces[-1]["retry_budget"]["used"] == 0


def test_repair_attempt_retains_recovery_kind_in_trace():
    requests, traces = [], []
    invoke([extraction_response([FACT]), "bad", CANDIDATE, AUDIT], requests, traces)
    assert traces[-1]["stages"][2]["recovery"] == "model_format_repair"


def test_extraction_json_structure_gets_format_repair_with_same_numbered_source():
    requests = []
    invoke(["invalid", extraction_response([FACT]), CANDIDATE, AUDIT], requests)
    assert len(requests) == 4
    repair = body(requests[1])
    assert repair["repair"]["category"] == "format"
    assert repair["source"] == body(requests[0])["source"]


def test_extraction_quote_field_is_source_failure_without_repair():
    requests, traces = [], []
    with pytest.raises(LLMServiceError):
        invoke([extraction_response([{**FACT, "quote": "manufactured"}])], requests, traces)
    assert len(requests) == 1 and traces[-1]["error_category"] == "source"


def test_capacity_blocked_attempt_has_trace_but_is_not_paid_or_extra_budget(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_input_chars", 12000)
    requests, traces = [], []
    with pytest.raises(LLMServiceError):
        invoke([extraction_response([FACT]), "bad" + "x" * 13000], requests, traces)
    blocked = traces[-1]["stages"][-1]
    assert blocked["stage"] == "compose" and blocked["attempt"] == 2
    assert blocked["error_category"] == "capacity" and blocked["status"] == "blocked"
    assert blocked["paid_attempt"] is False and traces[-1]["paid_calls"] == 2


def test_auto_strategy_does_not_fall_back_on_invalid_retry_configuration(monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_strategy", "auto")
    monkeypatch.setattr(settings, "llm_summary_format_retries", True)
    requests = []
    with pytest.raises(LLMServiceError) as exc:
        invoke([], requests)
    assert exc.value.error_type == "llm_unconfigured" and requests == []


def test_optimized_python_still_consumes_and_enforces_the_repair_budget():
    # Production can run with -O; the budget mutation must never depend on assert.
    script = '''
import sys
sys.path.insert(0, "tests")
import httpx, pytest
from app.config import settings
from app.services.llm_service import LLMServiceError, summarize_text
from test_grounded_pipeline import configured, SOURCE
configured.__wrapped__(pytest.MonkeyPatch())
settings.llm_summary_format_retries = 1
settings.llm_summary_semantic_retries = 1
settings.llm_summary_max_extra_calls = 2
calls, traces = [], []
def respond(request):
    calls.append(request)
    if len(calls) > 2:
        raise RuntimeError("Repair budget was bypassed")
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "invalid"}}]})
with httpx.Client(transport=httpx.MockTransport(respond)) as client:
    try:
        summarize_text(SOURCE, title="Policy", output_language="en", client=client, diagnostic=traces.append)
    except LLMServiceError:
        pass
    else:
        raise RuntimeError("Invalid responses were published")
if len(calls) != 2 or traces[-1]["retry_budget"]["format_used"] != 1:
    raise RuntimeError("Wrong repair count")
'''
    result = subprocess.run([sys.executable, "-B", "-O", "-c", script],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
