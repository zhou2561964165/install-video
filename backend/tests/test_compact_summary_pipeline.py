"""Exercise compact facts orchestration by replacing only vendor HTTP."""
import copy
import json
import httpx
import pytest

from app.config import settings
from app.services.llm_service import LLMServiceError, summarize_text
from test_grounded_pipeline import configured, SOURCE, FACT, CANDIDATE, AUDIT, extraction_response


FLAGS = {"supported": True, "qualifiers_preserved": True,
         "attribution_preserved": True, "scope_preserved": True}
COMPOSE = {"summary": SOURCE, "point_1": {"topic": "Opening hours", "text": SOURCE, "fact_ids": ["F1_1"]},
    "theme_plan": {"theme_1": {"topic": "Opening hours", "principle": SOURCE,
        "conditions": [], "consequences": [], "fact_ids": ["F1_1"]}}}
COMPACT = {"additional_facts": [], "output": {"summary": {"text": SOURCE, "assertions": dict(FLAGS)},
    "point_1": {"topic": "Opening hours", "text": SOURCE, "fact_ids": ["F1_1"], "assertions": dict(FLAGS)}}}


@pytest.fixture(autouse=True)
def compact(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_quality_contract", "compact")
    monkeypatch.setattr(settings, "llm_summary_format_retries", 1)
    monkeypatch.setattr(settings, "llm_summary_semantic_retries", 1)
    monkeypatch.setattr(settings, "llm_summary_max_extra_calls", 2)


def invoke(responses, requests, traces, *, transcript=SOURCE):
    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) > len(responses):
            raise RuntimeError("Unexpected additional POST")
        output = responses[len(requests) - 1]
        content = output if isinstance(output, str) else json.dumps(output)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        return summarize_text(transcript, title="Opening hours", output_language="en", client=client, diagnostic=traces.append)


def user(request):
    return json.loads(request["messages"][1]["content"])


def test_compact_real_assertions_are_mapped_to_program_ids_and_public_output():
    requests, traces = [], []
    result = invoke([extraction_response([FACT]), COMPOSE, COMPACT], requests, traces)
    assert result.summary == SOURCE and result.key_points == [SOURCE]
    assert len(requests) == 3 and traces[-1]["paid_calls"] == 3
    assert traces[-1]["audit_protocol"] == "compact"
    assert [check["item_id"] for check in traces[-1]["audit"]["checks"]] == ["S1", "P1"]
    assert user(requests[2])["protected_attributions"]


def test_missing_draft_plan_and_unconfirmed_name_go_to_original_planned_audit():
    requests, traces = [], []
    draft = {"summary": "讲者陈文辉介绍：" + SOURCE, "key_points": [SOURCE]}
    result = invoke([extraction_response([FACT]), draft, COMPACT], requests, traces)
    assert len(requests) == 3 and result.summary == SOURCE
    reasons = {issue["reason"] for issue in user(requests[2])["quality_issues"]}
    assert "missing_theme_plan" in reasons and "unconfirmed_identity" in reasons


def test_source_failure_precedes_bad_output_assertion_and_gets_no_repair():
    bad = copy.deepcopy(COMPACT)
    bad["additional_facts"] = [{**FACT, "source_id": "invented"}]
    bad["output"]["summary"]["assertions"]["supported"] = 1
    requests, traces = [], []
    with pytest.raises(LLMServiceError):
        invoke([extraction_response([FACT]), COMPOSE, bad], requests, traces)
    assert len(requests) == 3 and traces[-1]["error_category"] == "source"
    assert traces[-1]["retry_budget"]["used"] == 0


def test_false_embedded_assertion_uses_one_semantic_revision():
    bad = copy.deepcopy(COMPACT)
    bad["output"]["point_1"]["assertions"]["scope_preserved"] = False
    requests, traces = [], []
    invoke([extraction_response([FACT]), COMPOSE, bad, COMPACT], requests, traces)
    assert len(requests) == 4 and user(requests[-1])["repair"]["category"] == "semantic"
    assert user(requests[-1])["repair"]["failed_items"] == ["P1"]


def test_unconfirmed_final_identity_cannot_pass_all_true_assertions():
    bad = copy.deepcopy(COMPACT)
    bad["output"]["summary"]["text"] = "讲者陈文辉介绍：" + SOURCE
    requests, traces = [], []
    invoke([extraction_response([FACT]), COMPOSE, bad, COMPACT], requests, traces)
    assert len(requests) == 4 and user(requests[-1])["repair"]["category"] == "semantic"
    assert user(requests[-1])["repair"]["failed_items"] == ["S1"]


def test_format_and_semantic_repairs_share_two_slots_and_preserve_stage_inputs():
    bad = copy.deepcopy(COMPACT)
    bad["output"]["summary"]["assertions"]["supported"] = False
    requests, traces = [], []
    invoke([extraction_response([FACT]), COMPOSE, "invalid JSON", bad, COMPACT], requests, traces)
    assert len(requests) == 5 and traces[-1]["retry_budget"]["used"] == 2
    assert [user(r)["repair"]["category"] for r in requests[-2:]] == ["format", "semantic"]
    for request in requests[-2:]:
        assert user(request)["sources"] == user(requests[2])["sources"]


@pytest.mark.parametrize("strategy", ["facts", "auto"])
def test_invalid_quality_mode_stops_before_the_first_post(monkeypatch, strategy):
    monkeypatch.setattr(settings, "llm_summary_quality_contract", "invalid")
    monkeypatch.setattr(settings, "llm_summary_strategy", strategy)
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as exc:
        invoke([], requests, traces)
    assert exc.value.error_type == "llm_unconfigured" and requests == []


def test_compat_mode_still_accepts_original_legacy_audit(monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_quality_contract", "compat")
    requests, traces = [], []
    result = invoke([extraction_response([FACT]), CANDIDATE, AUDIT], requests, traces)
    assert len(requests) == 3 and result.summary == SOURCE


def test_missing_core_revision_supplies_actual_bindings_and_missing_claims():
    second = "Pat says the swimming pool opens on Tuesdays for lessons."
    fact = {"topic": "Pool hours", "claim": second, "evidence": [2],
            "attribution": "Pat", "importance": "core"}
    compose = copy.deepcopy(COMPOSE)
    compose["point_1"]["fact_ids"].append("F1_2")
    compose["theme_plan"]["theme_1"]["fact_ids"].append("F1_2")
    bad = copy.deepcopy(COMPACT)
    bad["output"]["point_1"]["fact_ids"].append("F1_2")
    good = copy.deepcopy(COMPACT)
    good["output"]["summary"]["text"] = SOURCE + " " + second
    good["output"]["point_2"] = {"topic": "Pool hours", "text": second,
        "fact_ids": ["F1_2"], "assertions": dict(FLAGS)}
    requests, traces = [], []
    result = invoke([extraction_response([FACT, fact]), compose, bad, good], requests, traces,
                    transcript=SOURCE + "\n" + second)
    assert second in result.summary and len(requests) == 4
    repair = user(requests[-1])["repair"]
    assert repair["reason"] == "missing_core_fact" and repair["failed_items"] == ["F1_2"]
    details = repair["validation"]
    assert details["missing_core_facts"][0]["id"] == "F1_2"
    assert details["missing_core_facts"][0]["claim"] == second
    assert details["actual_output"]["key_points"][0]["fact_ids"] == ["F1_1"]
    assert json.loads(repair["previous_response"]) == bad
