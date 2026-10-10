"""Exercise new private contracts through real orchestration and HTTP boundaries.

Transport responses are literal protocol fixtures, never semantic model proof.
"""
import copy
import json
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.services.llm_service import LLMServiceError, summarize_text
from test_grounded_pipeline import configured, composition_response, extraction_response


SOURCE = "Mira says visitors usually register before entry.\nRegistered visitors may borrow a badge.\nVisitors return the badge before leaving."
EXTRACT = {
    "fact_1": {"topic": "Entry", "claim": "Mira says visitors usually register before entry.",
               "evidence": [1], "attribution": "Mira", "importance": "core"},
    "fact_2": {"topic": "Badge", "claim": "Registered visitors may borrow a badge.",
               "evidence": [2], "attribution": "source", "importance": "support"},
    "fact_3": {"topic": "Departure", "claim": "Visitors return the badge before leaving.",
               "evidence": [3], "attribution": "source", "importance": "core"},
    **{f"fact_{i}": None for i in range(4, 13)},
}
PLAN = {"topic": "Entry and badges", "principle": "Register before borrowing a badge.",
        "conditions": ["Visitors usually register before entry; borrowing is optional."],
        "consequences": ["The badge is returned before departure."],
        "fact_ids": ["F1_1", "F1_2", "F1_3"]}
COMPOSE = {
    "summary": [{"text": "Mira says visitors usually register before entry.", "fact_ids": ["F1_1"]}],
    "point_1": {"topic": "Entry and badges", "text": "Registered visitors may borrow a badge.",
                "fact_ids": ["F1_1", "F1_2"]},
    **{f"point_{i}": None for i in range(2, 8)},
    "theme_plan": {"theme_1": PLAN, **{f"theme_{i}": None for i in range(2, 8)}},
}
FINAL = {"summary": COMPOSE["summary"], "key_points": [
    {"topic": "Entry and badges", "text": "Registered visitors may borrow a badge and return it before leaving.",
     "fact_ids": ["F1_1", "F1_2", "F1_3"]}]}
AUDIT = {"additional_facts": [], "output": FINAL, "checks": [
    {"item_id": item, "supported": True, "qualifiers_preserved": True,
     "attribution_preserved": True, "scope_preserved": True} for item in ("S1", "P1")]}


def invoke(responses, requests, traces, *, source=SOURCE):
    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) > len(responses):
            pytest.fail("A failed contract must stop before another paid request")
        response = responses[len(requests) - 1]
        content = response if isinstance(response, str) else json.dumps(response)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": content}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        return summarize_text(source, title="Visitor rules", output_language="en",
                              client=client, diagnostic=traces.append)


def test_planned_theme_and_all_source_facts_reach_only_audit_with_core_gap():
    # Removing the theme from the audit input or rejecting draft core gaps breaks this.
    requests, traces = [], []
    result = invoke([EXTRACT, COMPOSE, AUDIT], requests, traces)
    assert result.summary == "Mira says visitors usually register before entry."
    assert result.key_points == ["Registered visitors may borrow a badge and return it before leaving."]
    assert len(requests) == 3
    audit = json.loads(requests[2]["messages"][1]["content"])
    assert audit["sources"] == [{"id": "part1", "line_count": 3,
        "text": "[1] Mira says visitors usually register before entry.\n[2] Registered visitors may borrow a badge.\n[3] Visitors return the badge before leaving."}]
    assert audit["facts"] == [
        {"id": f"F1_{i}", "source_id": "part1", **EXTRACT[f"fact_{i}"]} for i in range(1, 4)]
    assert audit["candidate"] == {"summary": COMPOSE["summary"],
        "key_points": [{**COMPOSE["point_1"], "fact_ids": ["F1_2"]}]}
    assert audit["missing_core_fact_ids"] == ["F1_3"]
    expected_hint = {"point_index": 1, **{key: value for key, value in PLAN.items() if key != "fact_ids"},
                     "hint_ids": PLAN["fact_ids"]}
    assert audit["theme_plan"] == [expected_hint]
    assert traces[-1]["theme_plan"] == [expected_hint]
    assert traces[-1]["planned_calls"] == 3
    assert [stage["stage"] for stage in traces[-1]["stages"]] == ["extract", "compose", "audit"]


@pytest.mark.parametrize("stage", ["extract", "compose", "audit"])
def test_illegal_private_contract_stops_at_its_stage_without_retry(stage):
    # Invalid extract containers, unknown composition fields, and overlong
    # finals remain failures when the caller explicitly disables repairs.
    responses = copy.deepcopy([EXTRACT, COMPOSE, AUDIT])
    index = ["extract", "compose", "audit"].index(stage)
    if stage == "extract":
        responses[0] = {"facts": [EXTRACT["fact_1"]]}
    elif stage == "compose":
        responses[1]["unknown_field"] = True
    else:
        responses[2]["output"]["summary"][0]["text"] = "x" * 801
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        invoke(responses[:index + 1], requests, traces)
    assert error.value.error_type == "llm_invalid_response"
    assert len(requests) == index + 1
    assert traces[-1]["status"] == "failed"


def test_complete_theme_plan_counts_toward_actual_audit_capacity(monkeypatch):
    # Omitting the plan from capacity accounting would send the third request.
    composition = copy.deepcopy(COMPOSE)
    composition["theme_plan"]["theme_1"]["conditions"] = ["c" * 240] * 7
    requests, traces = [], []
    invoke([EXTRACT, composition, AUDIT], requests, traces)
    audit_size = len(json.dumps(requests[2], ensure_ascii=False))
    monkeypatch.setattr(settings, "llm_max_input_chars", audit_size - 1)
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        invoke([EXTRACT, composition], requests, traces)
    assert error.value.error_type == "llm_input_too_large"
    assert len(requests) == 2
    assert len(traces[-1]["facts"]) == 3
    assert traces[-1]["theme_plan"][0]["conditions"] == ["c" * 240] * 7
    assert "audit" not in traces[-1]


def test_global_theme_can_assign_facts_from_two_parts_in_n_plus_two_calls(monkeypatch):
    # Per-part composition, losing cross-source assignments, or an extra stage breaks this.
    first, second = "Mira says visitors usually register before entry.", "Registered visitors may borrow a badge."
    monkeypatch.setattr(settings, "llm_summary_facts_chunk_chars", len(first))
    extract1 = {"fact_1": EXTRACT["fact_1"], **{f"fact_{i}": None for i in range(2, 13)}}
    extract2 = {"fact_1": dict(EXTRACT["fact_2"], evidence=[1], importance="core"),
                **{f"fact_{i}": None for i in range(2, 13)}}
    composition = copy.deepcopy(COMPOSE)
    composition["point_1"]["fact_ids"] = ["F1_1", "F2_1"]
    composition["theme_plan"]["theme_1"]["fact_ids"] = ["F1_1", "F2_1"]
    composition["theme_plan"]["theme_1"]["consequences"] = []
    audit = copy.deepcopy(AUDIT)
    audit["output"]["key_points"][0] = copy.deepcopy(composition["point_1"])
    requests, traces = [], []
    result = invoke([extract1, extract2, composition, audit], requests, traces, source=first + "\n" + second)
    assert result.key_points == ["Registered visitors may borrow a badge."]
    assert len(requests) == 4 and traces[-1]["planned_calls"] == 4
    audit_input = json.loads(requests[3]["messages"][1]["content"])
    assert [source["id"] for source in audit_input["sources"]] == ["part1", "part2"]
    assert [fact["id"] for fact in audit_input["facts"]] == ["F1_1", "F2_1"]
    assert audit_input["theme_plan"][0]["hint_ids"] == ["F1_1", "F2_1"]
    assert audit_input["candidate"]["key_points"][0]["fact_ids"] == ["F2_1"]
    assert audit_input["missing_core_fact_ids"] == []


def test_fixture_migration_preserves_eighth_point_for_production_rejection():
    # A fixture adapter that silently trims an invalid eighth point bypasses validation.
    extracted = extraction_response([dict(EXTRACT["fact_1"], importance="core") for _ in range(8)])
    candidate = {"summary": [{"text": "Visitor registration.", "fact_ids": [f"F1_{i}" for i in range(1, 9)]}],
        "key_points": [{"topic": f"Rule {i}", "text": f"Visitor registration rule {i}.", "fact_ids": [f"F1_{i}"]}
                       for i in range(1, 9)]}
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        invoke([extracted, composition_response(candidate)], requests, traces)
    assert error.value.error_type == "llm_invalid_response"
    assert len(requests) == 2


@pytest.mark.parametrize("invalid", [None, "invalid item", {}, {"topic": "Missing fields"}])
def test_fixture_migration_keeps_invalid_fact_array_item_rejected_at_extract(invalid):
    # Old array elements are facts, never new unused null slots.
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        invoke([extraction_response([EXTRACT["fact_1"], invalid])], requests, traces)
    assert error.value.error_type == "llm_invalid_response"
    assert len(requests) == 1
    assert traces[-1]["status"] == "failed"


@pytest.mark.parametrize("invalid", [None, {}, {"topic": "Missing fields"}])
def test_fixture_migration_keeps_invalid_point_array_item_rejected_at_compose(invalid):
    # A malformed old point must not become a trailing unused point/theme pair.
    candidate = {"summary": COMPOSE["summary"], "key_points": [COMPOSE["point_1"], invalid]}
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        invoke([EXTRACT, composition_response(candidate)], requests, traces)
    assert error.value.error_type == "llm_invalid_response"
    assert len(requests) == 2
    assert traces[-1]["status"] == "failed"


def test_array_string_point_is_preserved_as_unresolved_and_sent_to_audit():
    candidate = {"summary": COMPOSE["summary"], "key_points": [COMPOSE["point_1"], "invalid item"]}
    requests, traces = [], []
    invoke([EXTRACT, composition_response(candidate), AUDIT], requests, traces)
    audit = json.loads(requests[2]["messages"][1]["content"])
    assert len(requests) == 3
    assert audit["candidate"]["key_points"][1]["text"] == "invalid item"
    assert audit["candidate"]["key_points"][1]["fact_ids"] == []
    assert "P2" in audit["reference_status"]["unresolved"]


def test_saved_thirteen_fact_extraction_still_fails_without_truncation(monkeypatch):
    # The historical failed response is retained with all 13 facts, never turned into 12.
    project = Path(__file__).resolve().parents[2]
    results = project / "docs/acceptance-reports/2026-10-07-grounded-summary-final/results/responses"
    corpus = project / "docs/acceptance-reports/2026-10-04-natural-subtitle-quality/corpus"
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    sample = next(sample for sample in manifest["samples"] if sample["id"] == "en-long")
    source = (corpus / sample["file"]).read_text(encoding="utf-8")
    responses = []
    for ordinal, expected_count in [(7, 9), (8, 10), (9, 13)]:
        saved = json.loads((results / f"{ordinal:02}.json").read_text(encoding="utf-8"))
        assert saved["sample"] == "en-long" and saved["stage"] == "extract"
        old = json.loads(saved["content"])
        assert set(old) == {"facts"} and len(old["facts"]) == expected_count
        responses.append(extraction_response(old["facts"]))
    assert len(responses[2]) == 13 and responses[2]["fact_13"] is not None
    monkeypatch.setattr(settings, "llm_max_input_chars", 100000)
    monkeypatch.setattr(settings, "llm_summary_facts_chunk_chars", 8000)
    monkeypatch.setattr(settings, "llm_summary_facts_max_evidence_sentences", 128)
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        invoke(responses, requests, traces, source=source)
    assert error.value.error_type == "llm_invalid_response"
    assert len(requests) == 3
    assert len(traces[-1]["facts"]) == 19
    assert [stage["stage"] for stage in traces[-1]["stages"]] == ["extract"] * 3
