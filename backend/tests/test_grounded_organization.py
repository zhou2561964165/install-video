"""Zero-network replay checks protocol and orchestration, never semantic quality."""
import copy
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.services.llm_service import LLMServiceError, summarize_text
from test_grounded_pipeline import composition_response, extraction_response


PROJECT = Path(__file__).resolve().parents[2]
EVIDENCE = PROJECT / "docs/acceptance-reports/2026-10-05-grounded-summary-evidence/results"
CORPUS = PROJECT / "docs/acceptance-reports/2026-10-04-natural-subtitle-quality/corpus"


@pytest.fixture
def replay(monkeypatch):
    for key, value in {
        "llm_base_url": "https://offline.invalid/v1", "llm_model": "offline-model",
        "llm_provider": "compatible", "llm_summary_strategy": "facts",
        "llm_summary_response_format": "json_object", "llm_max_input_chars": 100000,
        "llm_summary_chunk_chars": 20000, "llm_summary_max_chunks": 16,
        "llm_summary_max_output_tokens": 4096, "llm_summary_facts_chunk_chars": 8000,
        "llm_summary_facts_max_source_chars": 40000, "llm_summary_facts_max_per_chunk": 12,
        "llm_summary_facts_max_evidence_sentences": 128,
        "llm_summary_facts_max_summary_chars": 800, "llm_summary_max_point_chars": 240,
        "llm_summary_facts_compose_max_output_tokens": 8192,
        "llm_summary_facts_audit_max_output_tokens": 8192,
        "llm_summary_format_retries": 0, "llm_summary_semantic_retries": 0,
        "llm_summary_max_extra_calls": 0,
    }.items():
        monkeypatch.setattr(settings, key, value)
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    sample = next(row for row in manifest["samples"] if row["id"] == "en-long")
    source = (CORPUS / sample["file"]).read_bytes()
    assert hashlib.sha256(source).hexdigest() == sample["sha256"]
    trace = json.loads((EVIDENCE / "evidence-wide-en-long-trace.json").read_text(encoding="utf-8"))["events"][-1]
    facts = trace["facts"]
    assert len(facts) == 54
    extracts = []
    for part in trace["sources"]:
        part_facts = [{"topic": f["topic"], "claim": f["claim"],
                                   "evidence": f["evidence_indices"], "attribution": f["attribution"],
                                   "importance": f["importance"]}
                                  for f in facts if f["source_id"] == part["id"]]
        assert 1 <= len(part_facts) <= 12
        # Only migrate the historical container; no fact is dropped or rewritten.
        extracts.append(extraction_response(part_facts))
    # A synthetic model response deliberately exercises references and bounds.
    # Its true flags and reference coverage are NOT a source-accuracy score.
    points = [{"topic": f"Group {i + 1}", "text": group[0]["claim"],
               "fact_ids": [f["id"] for f in group]}
              for i in range(7) if (group := facts[i::7])]
    candidate = {"summary": [{"text": "Course concepts, computations, types, operations and variable bindings.",
                               "fact_ids": [f["id"] for f in facts]}], "key_points": points}
    composition = composition_response(candidate)
    checks = [{"item_id": item, "supported": True, "qualifiers_preserved": True,
               "attribution_preserved": True, "scope_preserved": True}
              for item in ["S1", *(f"P{i}" for i in range(1, 8))]]
    audit = {"additional_facts": [], "output": candidate, "checks": checks}
    return source.decode("utf-8"), extracts + [composition, audit], candidate


def run_replay(replay, traces, requests):
    source, responses, _ = replay
    def respond(request):
        requests.append(json.loads(request.content))
        content = responses[len(requests) - 1]
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(content)}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        return summarize_text(source, title="Lecture 1", output_language="en", client=client, diagnostic=traces.append)


def test_saved_long_facts_with_synthetic_all_id_coverage_are_rejected(replay):
    traces, requests = [], []
    with pytest.raises(LLMServiceError) as error:
        run_replay(replay, traces, requests)
    assert error.value.error_type == "llm_invalid_response"
    assert len(requests) == 7
    assert [item["max_tokens"] for item in requests] == [4096] * 5 + [8192, 8192]
    # These fabricated grouped hints do not establish support for all facts.
    # Retain the historical evidence; require real text association and core
    # coverage instead of turning true mock flags into a quality assertion.
    assert len(traces[-1]["facts"]) == 54
    assert traces[-1]["status"] == "failed"
    assert traces[-1]["error_category"] == "semantic"
    assert "audit" not in traces[-1]
    assert traces[-1]["planned_calls"] == 7


def test_default_input_capacity_stops_long_audit_without_source_or_fact_dropping(replay, monkeypatch):
    monkeypatch.setattr(settings, "llm_max_input_chars", 60000)
    traces, requests = [], []
    with pytest.raises(LLMServiceError) as error:
        run_replay(replay, traces, requests)
    assert error.value.error_type == "llm_input_too_large"
    assert len(requests) == 6
    assert len(traces[-1]["facts"]) == 54
    assert "audit" not in traces[-1]


def test_eighth_composition_slot_stops_before_audit_without_retry(replay):
    source, responses, candidate = replay
    responses = copy.deepcopy(responses)
    responses[5]["point_8"] = responses[5]["point_1"]
    traces, requests = [], []
    with pytest.raises(LLMServiceError) as error:
        run_replay((source, responses, candidate), traces, requests)
    assert error.value.error_type == "llm_invalid_response"
    assert len(requests) == 6
    assert len(traces[-1]["facts"]) == 54


def test_invalid_stage_budget_fails_before_any_paid_extraction(replay, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_facts_compose_max_output_tokens", -1)
    traces, requests = [], []
    with pytest.raises(LLMServiceError) as error:
        run_replay(replay, traces, requests)
    assert error.value.error_type == "llm_unconfigured"
    assert requests == []
