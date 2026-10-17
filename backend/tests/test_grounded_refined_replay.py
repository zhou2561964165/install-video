"""Replay real refined extracts/compose; reject synthetic audit responses.

These zero-network checks establish pipeline admission and final contracts,
never model correctness or semantic coverage. Historical evidence stays read-only.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.services import llm_service as service
from app.services.llm_service import LLMServiceError, summarize_text
from test_grounded_pipeline import composition_response, extraction_response


PROJECT = Path(__file__).resolve().parents[2]
RESULTS = PROJECT / "docs/acceptance-reports/2026-10-07-grounded-summary-refined/results"
CORPUS = PROJECT / "docs/acceptance-reports/2026-10-04-natural-subtitle-quality/corpus"


@pytest.fixture
def refined(monkeypatch):
    # Reuse the established historical caption preparation without changing
    # production or replacing the frozen sources/facts expected by the guards.
    script = PROJECT / "docs/acceptance-reports/2026-10-10-source-first-summary-live/scripts/evaluate.py"
    spec = importlib.util.spec_from_file_location("refined_historical_preparation", script)
    historical = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(historical)
    monkeypatch.setattr(service, "_summary_input", historical.cleaned)
    for name, value in {
        "llm_base_url": "https://offline.invalid/v1", "llm_api_key": "offline-only",
        "llm_model": "offline-model", "llm_provider": "compatible",
        "llm_summary_strategy": "facts", "llm_summary_response_format": "json_object",
        "llm_summary_thinking_mode": "disabled", "llm_max_input_chars": 100000,
        "llm_summary_chunk_chars": 20000, "llm_summary_max_chunks": 16,
        "llm_summary_max_output_tokens": 4096, "llm_summary_facts_chunk_chars": 8000,
        "llm_summary_facts_max_source_chars": 40000, "llm_summary_facts_max_per_chunk": 12,
        "llm_summary_facts_max_evidence_sentences": 128,
        "llm_summary_facts_max_summary_chars": 800, "llm_summary_max_point_chars": 240,
        "llm_summary_facts_compose_max_output_tokens": 8192,
        "llm_summary_facts_audit_max_output_tokens": 8192,
        # This historical replay isolates terminal boundaries with repairs off.
        "llm_summary_format_retries": 0, "llm_summary_semantic_retries": 0,
        "llm_summary_max_extra_calls": 0,
    }.items():
        monkeypatch.setattr(settings, name, value)
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    sample = next(row for row in manifest["samples"] if row["id"] == "en-long")
    source = (CORPUS / sample["file"]).read_bytes()
    assert hashlib.sha256(source).hexdigest() == sample["sha256"]
    trace = json.loads((RESULTS / "organization-refined-en-long-trace.json").read_text(encoding="utf-8"))["events"][-1]
    responses = []
    for ordinal in range(7, 13):
        record = json.loads((RESULTS / f"responses/{ordinal:02}.json").read_text(encoding="utf-8"))
        assert record["sample"] == "en-long"
        assert record["stage"] == ("extract" if ordinal < 12 else "compose")
        content = record["content"]
        if ordinal < 12:
            extraction = json.loads(content)
            assert set(extraction) == {"facts"} and 1 <= len(extraction["facts"]) <= 12
            # Historical raw remains read-only. Container-only adaptation is not
            # evidence that a new model can generate slots or global theme plans.
            content = json.dumps(extraction_response(extraction["facts"]), ensure_ascii=False)
        responses.append(content)
    composition = json.loads(responses[-1])
    candidate = {"summary": composition["summary"],
                 "key_points": [composition[f"point_{index}"] for index in range(1, 8)]}
    assert set(composition) == {"summary", *(f"point_{index}" for index in range(1, 8))}
    responses[-1] = json.dumps(composition_response(candidate), ensure_ascii=False)
    assert len(trace["facts"]) == 55
    assert len(candidate["summary"]) == 8
    assert len(" ".join(item["text"] for item in candidate["summary"])) == 1060
    return source.decode("utf-8"), responses, trace, candidate


def replay_to_audit(refined, audit_response, requests, traces):
    source, responses, _, _ = refined

    def respond(request):
        requests.append(json.loads(request.content))
        ordinal = len(requests)
        if ordinal > 7:
            pytest.fail("Audit failure must not trigger retry or another pipeline")
        if ordinal == 7 and isinstance(audit_response, int):
            return httpx.Response(audit_response, json={"error": "offline audit failure"})
        content = responses[ordinal - 1] if ordinal < 7 else json.dumps(audit_response, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": content}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        return summarize_text(source, title="Lecture 1: What is Computation?",
                              output_language="zh-CN", client=client, diagnostic=traces.append)


def test_real_refined_candidate_reaches_full_audit_with_missing_core_and_no_retry(refined):
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        replay_to_audit(refined, 503, requests, traces)
    assert error.value.error_type == "llm_error"
    assert len(requests) == 7
    assert [entry["stage"] for entry in traces[-1]["stages"]] == ["extract"] * 5 + ["compose", "audit"]
    assert traces[-1]["planned_calls"] == 7
    assert traces[-1]["status"] == "failed" and "audit" not in traces[-1]
    audit = json.loads(requests[-1]["messages"][1]["content"])
    frozen = refined[2]
    expected_facts = [{"id": fact["id"], "source_id": fact["source_id"], "topic": fact["topic"],
                       "claim": fact["claim"], "evidence": fact["evidence_indices"],
                       "attribution": fact["attribution"], "importance": fact["importance"]}
                      for fact in frozen["facts"]]
    expected_sources = [{"id": part["id"],
                         "line_count": len(lines := [line for line in part["text"].split("\n") if line]),
                         "text": "\n".join(f"[{index}] {line}" for index, line in enumerate(lines, 1))}
                        for part in frozen["sources"]]
    assert audit["facts"] == expected_facts
    assert audit["sources"] == expected_sources
    # Program associations replace the old model hints; wording stays exact.
    original = refined[3]
    candidate = audit["candidate"]
    assert [item["text"] for item in candidate["summary"]] == [item["text"] for item in original["summary"]]
    assert [(item["topic"], item["text"]) for item in candidate["key_points"]] == [
        (item["topic"], item["text"]) for item in original["key_points"]]
    known = {item["id"] for item in frozen["facts"]}
    used = {ref for item in (*candidate["summary"], *candidate["key_points"]) for ref in item["fact_ids"]}
    assert used <= known
    assert audit["missing_core_fact_ids"] == [item["id"] for item in frozen["facts"]
        if item["importance"] == "core" and item["id"] not in used]
    assert all(set(item["fact_ids"]) < known for item in (*candidate["summary"], *candidate["key_points"]))
    assert "reference_status" in audit
    assert len(json.dumps(requests[-1], ensure_ascii=False)) < 100000


def rejected_audit(refined):
    # Preserve all seven actual points but shorten summary solely to isolate
    # final rejection reasons. This response never earns a success assertion.
    return {"additional_facts": [],
            "output": {"summary": [copy.deepcopy(refined[3]["summary"][2])],
                       "key_points": copy.deepcopy(refined[3]["key_points"])},
            "checks": []}


def test_real_refined_final_missing_core_is_rejected_after_planned_audit(refined):
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        replay_to_audit(refined, rejected_audit(refined), requests, traces)
    assert error.value.error_type == "llm_invalid_response"
    # These real paraphrases can first fail program association; neither an
    # unresolved final nor missing core coverage may escape the audit boundary.
    assert str(error.value.__cause__) in {"missing_core_fact", "unresolved_references"}
    assert len(requests) == 7
    assert traces[-1]["status"] == "failed" and "audit" not in traces[-1]


@pytest.mark.parametrize("boundary,reason", [
    ("summary_count", "too_many_summary_items"), ("summary_chars", "summary_too_long"),
    ("point_count", "too_many_points"), ("point_chars", "point_too_long"),
])
def test_real_refined_audit_cannot_publish_over_final_boundary(refined, boundary, reason):
    audit = rejected_audit(refined)
    output = audit["output"]
    if boundary == "summary_count":
        output["summary"] = [{"text": f"Contract clause {index}", "fact_ids": ["F1_7"]} for index in range(8)]
    elif boundary == "summary_chars":
        output["summary"][0]["text"] = "x" * 801
    elif boundary == "point_count":
        output["key_points"].append({"topic": "Extra", "text": "Extra point", "fact_ids": ["F2_3"]})
    else:
        output["key_points"][0]["text"] = "x" * 241
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        replay_to_audit(refined, audit, requests, traces)
    assert error.value.error_type == "llm_invalid_response"
    assert str(error.value.__cause__) == reason
    assert len(requests) == 7
    assert traces[-1]["status"] == "failed" and "audit" not in traces[-1]
