"""Exercise caller-derived audit gaps with real stages and vendor HTTP replaced.

These tests verify reference diagnostics and failure boundaries, not the
semantic quality of model-generated wording.
"""
import copy
import json

import httpx
import pytest

from app.config import settings
from app.services.llm_service import LLMServiceError, summarize_text
from test_grounded_pipeline import composition_response, extraction_response


LINES = [
    "The workshop requires registration.",
    "Registered visitors collect a badge at reception.",
    "The practical session ends with a safety review.",
    "The example badge is blue.",
    "Visitors return the badge before leaving.",
]
FACTS = [
    {"topic": topic, "claim": line, "evidence": [index],
     "attribution": "source", "importance": importance}
    for index, (line, topic, importance) in enumerate(zip(
        LINES, ["Registration", "Reception", "Safety", "Example", "Departure"],
        ["core", "core", "core", "support", "core"],
    ), 1)
]
CANDIDATE = {
    "summary": [{"text": LINES[0], "fact_ids": ["F1_1"]}],
    "key_points": [{"topic": "Reception", "text": LINES[1], "fact_ids": ["F1_2"]}],
}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    values = {
        "llm_summary_format_retries": 0, "llm_summary_semantic_retries": 0,
        "llm_summary_max_extra_calls": 0,
        "llm_base_url": "https://model.example/v1", "llm_api_key": "",
        "llm_model": "fixture-model", "llm_provider": "compatible",
        "llm_summary_strategy": "facts", "llm_summary_response_format": "json_object",
        "llm_max_input_chars": 60000, "llm_summary_chunk_chars": 20000,
        "llm_summary_max_chunks": 16, "llm_summary_max_output_tokens": 4096,
        "llm_summary_facts_max_source_chars": 40000,
        "llm_summary_facts_chunk_chars": 20000, "llm_summary_facts_max_per_chunk": 12,
        "llm_summary_facts_max_evidence_sentences": 32,
        "llm_summary_facts_max_summary_chars": 800, "llm_summary_max_point_chars": 240,
        "llm_summary_facts_compose_max_output_tokens": 0,
        "llm_summary_facts_audit_max_output_tokens": 0,
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


def audited(output):
    identifiers = [f"S{i}" for i in range(1, len(output["summary"]) + 1)]
    identifiers += [f"P{i}" for i in range(1, len(output["key_points"]) + 1)]
    return {"additional_facts": [], "output": output, "checks": [
        {"item_id": identifier, "supported": True, "qualifiers_preserved": True,
         "attribution_preserved": True, "scope_preserved": True}
        for identifier in identifiers
    ]}


def transport(candidate, final, requests):
    compose = composition_response(candidate)
    responses = [extraction_response(FACTS), compose, audited(final)]

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(responses[len(requests) - 1]),
            },
        }]})

    return httpx.MockTransport(respond)


def invoke(candidate, final, requests):
    with httpx.Client(transport=transport(candidate, final, requests)) as client:
        return summarize_text("\n".join(LINES), title="Workshop policy",
                              output_language="en", client=client)


def completed_candidate():
    final = copy.deepcopy(CANDIDATE)
    final["summary"].append({"text": LINES[2], "fact_ids": ["F1_3"]})
    final["key_points"].append({"topic": "Departure", "text": LINES[4], "fact_ids": ["F1_5"]})
    return final


def test_audit_receives_only_unreferenced_core_ids_in_fact_order():
    requests = []
    result = invoke(CANDIDATE, completed_candidate(), requests)
    audit_input = json.loads(requests[2]["messages"][1]["content"])
    assert audit_input["missing_core_fact_ids"] == ["F1_3", "F1_5"]
    assert audit_input["candidate"] == CANDIDATE
    assert len(requests) == 3
    assert result.key_points[-1] == "Visitors return the badge before leaving."


def test_audit_gap_detection_uses_summary_and_points_without_requiring_support():
    requests = []
    final = completed_candidate()
    result = invoke(final, final, requests)
    audit_input = json.loads(requests[2]["messages"][1]["content"])
    assert audit_input["missing_core_fact_ids"] == []
    assert len(requests) == 3
    assert result.summary == (
        "The workshop requires registration. The practical session ends with a safety review."
    )


def test_final_core_reference_gap_still_fails_without_retry():
    requests = []
    with pytest.raises(LLMServiceError) as error:
        invoke(CANDIDATE, CANDIDATE, requests)
    assert error.value.error_type == "llm_invalid_response"
    assert len(requests) == 3
    audit_input = json.loads(requests[2]["messages"][1]["content"])
    assert audit_input["missing_core_fact_ids"] == ["F1_3", "F1_5"]
