"""Exercise real summary stages and parsers with only vendor HTTP replaced."""
import copy
import json

import httpx
import pytest

from app.config import settings
from app.services.llm_service import LLMServiceError, summarize_text


SOURCE = "Mira says the library usually closes on Mondays for maintenance."
FACT = {"topic": "Opening hours", "claim": SOURCE, "evidence": [1],
        "attribution": "Mira", "importance": "core"}
CANDIDATE = {"summary": [{"text": "Mira says the library usually closes on Mondays for maintenance.", "fact_ids": ["F1_1"]}],
             "key_points": [{"topic": "Opening hours", "text": "According to Mira, the library usually closes on Mondays for maintenance.", "fact_ids": ["F1_1"]}]}
CHECKS = [{"item_id": item, "supported": True, "qualifiers_preserved": True,
           "attribution_preserved": True, "scope_preserved": True} for item in ("S1", "P1")]
AUDIT = {"additional_facts": [], "output": CANDIDATE, "checks": CHECKS}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    for name, value in {"llm_base_url": "https://model.example/v1", "llm_model": "fixture-model",
                        "llm_provider": "compatible", "llm_summary_strategy": "facts",
                        "llm_summary_response_format": "json_object", "llm_max_input_chars": 60000,
                        "llm_summary_chunk_chars": 20000, "llm_summary_max_chunks": 16,
                        "llm_summary_max_output_tokens": 4096,
                        "llm_summary_facts_max_source_chars": 40000,
                        "llm_summary_facts_chunk_chars": 20000,
                        "llm_summary_facts_max_per_chunk": 12,
                        "llm_summary_facts_max_evidence_sentences": 32,
                        "llm_summary_max_point_chars": 240}.items():
        monkeypatch.setattr(settings, name, value, raising=False)


def run(responses, *, transcript=SOURCE, trace=None):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        response = responses[len(requests) - 1]
        if isinstance(response, int):
            return httpx.Response(response, json={"error": "unavailable"})
        content = response if isinstance(response, str) else json.dumps(response)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = summarize_text(transcript, title="Library policy", output_language="en", client=client, diagnostic=trace)
    return result, requests


def test_facts_pipeline_audits_source_and_preserves_public_shape():
    traces = []
    result, requests = run([{"facts": [FACT]}, CANDIDATE, AUDIT], trace=traces.append)
    assert result.summary == SOURCE
    assert result.key_points == [CANDIDATE["key_points"][0]["text"]]
    assert result.provider == "compatible" and result.model == "fixture-model"
    assert len(requests) == 3
    assert all(request["response_format"] == {"type": "json_object"} for request in requests)
    audit_input = json.loads(requests[2]["messages"][1]["content"])
    assert audit_input["sources"][0]["text"] == "[1] " + SOURCE
    assert audit_input["candidate"] == CANDIDATE
    completed = traces[-1]
    assert completed["strategy"] == "facts" and completed["planned_calls"] == 3
    assert completed["facts"][0]["quote"] == SOURCE
    assert completed["facts"][0]["evidence_indices"] == [1]
    assert completed["facts"][0]["start"] == 0
    assert completed["facts"][0]["end"] == len(SOURCE)


@pytest.mark.parametrize("stage", ["extract", "compose", "audit"])
def test_failure_at_each_stage_stops_without_retry_or_legacy_fallback(stage):
    responses = [{"facts": [FACT]}, CANDIDATE, AUDIT]
    index = ["extract", "compose", "audit"].index(stage)
    responses[index] = 503
    calls = []
    def respond(request):
        calls.append(request)
        value = responses[len(calls)-1]
        return httpx.Response(value, json={}) if isinstance(value, int) else httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(value)}, "finish_reason": "stop"}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client, pytest.raises(LLMServiceError) as error:
        summarize_text(SOURCE, title="t", output_language="en", client=client)
    assert error.value.error_type == "llm_error"
    assert len(calls) == index + 1


@pytest.mark.parametrize("mode", ["strict_tool", "json_schema"])
def test_explicit_facts_unsupported_protocol_rejected_before_http(monkeypatch, mode):
    monkeypatch.setattr(settings, "llm_summary_response_format", mode)
    with pytest.raises(LLMServiceError) as error:
        run([])
    assert error.value.error_type == "llm_unconfigured"


def test_invalid_evidence_stops_after_extraction():
    fact = dict(FACT, evidence=[99])
    with pytest.raises(LLMServiceError) as error:
        run([{"facts": [fact]}])
    assert error.value.error_type == "llm_invalid_response"


def test_verbatim_quote_field_is_rejected_instead_of_accepted():
    fact = dict(FACT, quote="The library always closes.")
    with pytest.raises(LLMServiceError) as error:
        run([{"facts": [fact]}])
    assert error.value.error_type == "llm_invalid_response"


def test_negative_audit_flag_prevents_unaudited_result():
    audit = copy.deepcopy(AUDIT)
    audit["checks"][1]["qualifiers_preserved"] = False
    with pytest.raises(LLMServiceError) as error:
        run([{"facts": [FACT]}, CANDIDATE, audit])
    assert error.value.error_type == "llm_invalid_response"


def test_audit_repairs_overlong_candidate_without_truncating(monkeypatch):
    candidate = copy.deepcopy(CANDIDATE)
    candidate["key_points"][0]["text"] = "Some candidate wording. " * 12
    result, requests = run([{"facts": [FACT]}, candidate, AUDIT])
    assert len(requests) == 3
    assert result.key_points == [CANDIDATE["key_points"][0]["text"]]


def test_final_overlong_point_fails_instead_of_silent_truncation(monkeypatch):
    audit = copy.deepcopy(AUDIT)
    audit["output"]["key_points"][0]["text"] = "Some candidate wording. " * 12
    with pytest.raises(LLMServiceError) as error:
        run([{"facts": [FACT]}, CANDIDATE, audit])
    assert error.value.error_type == "llm_invalid_response"


def test_auto_uses_legacy_for_oversized_source_before_facts_request(monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_strategy", "auto")
    monkeypatch.setattr(settings, "llm_summary_facts_max_source_chars", 10)
    result, requests = run([{"summary": "Legacy policy", "key_points": ["Legacy point"]}])
    assert result.summary == "Legacy policy" and len(requests) == 1


def test_source_capacity_fails_before_first_paid_stage(monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_facts_max_source_chars", 10)
    with pytest.raises(LLMServiceError) as error:
        run([])
    assert error.value.error_type == "llm_input_too_large"


def test_two_parts_preserve_cleaned_source_offsets_and_closing_fact():
    ending = "Noor paused release."
    transcript = SOURCE + "\n" + "x" * (34658 - len(SOURCE) - len(ending) - 2) + "\n" + ending
    tail_fact = {"topic": "Release", "claim": ending, "evidence": [2],
                 "attribution": "Noor", "importance": "core"}
    candidate = copy.deepcopy(CANDIDATE)
    candidate["summary"][0]["fact_ids"].append("F2_1")
    candidate["summary"][0]["text"] += " " + ending
    candidate["key_points"].append({"topic": "Release", "text": ending, "fact_ids": ["F2_1"]})
    audit = {"additional_facts": [], "output": candidate,
             "checks": CHECKS + [{**CHECKS[1], "item_id": "P2"}]}
    traces = []
    result, requests = run([{"facts": [FACT]}, {"facts": [tail_fact]}, candidate, audit],
                           transcript=transcript, trace=traces.append)
    assert len(requests) == 4 and result.key_points[-1] == ending
    assert traces[-1]["planned_calls"] == 4
    assert traces[-1]["facts"][1]["start"] == 34638
    assert traces[-1]["facts"][1]["end"] == 34658
    assert traces[-1]["sources"][1]["global_start"] == 20000
    for fact in traces[-1]["facts"]:
        assert transcript[fact["start"]:fact["end"]] == fact["quote"]


def test_planned_audit_can_add_omitted_core_fact_with_validated_source():
    ending = "Noor paused release."
    candidate = copy.deepcopy(CANDIDATE)
    final = copy.deepcopy(CANDIDATE)
    final["key_points"].append({"topic": "Release", "text": ending, "fact_ids": ["A1"]})
    additional = {"source_id": "part1", "topic": "Release", "claim": ending, "evidence": [2],
                  "attribution": "Noor", "importance": "core"}
    audit = {"additional_facts": [additional], "output": final,
             "checks": CHECKS + [{**CHECKS[1], "item_id": "P2"}]}
    result, requests = run([{"facts": [FACT]}, candidate, audit], transcript=SOURCE + "\n" + ending)
    assert len(requests) == 3 and result.key_points[-1] == ending


def test_compose_capacity_stops_without_discarding_validated_facts(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_input_chars", 6000)
    facts = [dict(FACT, topic="t" * 120, claim="x" * 600) for _ in range(12)]
    traces = []
    with pytest.raises(LLMServiceError) as error:
        run([{"facts": facts}], trace=traces.append)
    assert error.value.error_type == "llm_input_too_large"
    assert len(traces[-1]["facts"]) == 12
    assert [entry["stage"] for entry in traces[-1]["stages"]] == ["extract"]


def test_source_json_escaping_capacity_checked_before_any_post(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_input_chars", 6000)
    with pytest.raises(LLMServiceError) as error:
        run([], transcript="\\" * 2000)
    assert error.value.error_type == "llm_input_too_large"


@pytest.mark.parametrize("mode", ["auto", "text", "json_object"])
def test_auto_supported_protocol_selects_fact_pipeline(monkeypatch, mode):
    monkeypatch.setattr(settings, "llm_summary_strategy", "auto")
    monkeypatch.setattr(settings, "llm_summary_response_format", mode)
    result, requests = run([{"facts": [FACT]}, CANDIDATE, AUDIT])
    assert result.summary == SOURCE and len(requests) == 3
    if mode != "json_object":
        assert "response_format" not in requests[0]


def test_auto_experimental_schema_selects_legacy_before_first_post(monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_strategy", "auto")
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_schema")
    requests = []
    def respond(request):
        requests.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"object": "response", "status": "completed", "output": [
            {"type": "message", "role": "assistant", "status": "completed", "content": [
                {"type": "output_text", "text": '{"summary":"Legacy","key_points":["Point"]}'}]}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = summarize_text(SOURCE, title="t", output_language="en", client=client)
    assert result.summary == "Legacy" and len(requests) == 1
    assert requests[0][0] == "/v1/responses"


def test_auto_retains_legacy_capacity_above_single_input_length(monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_strategy", "auto")
    transcript = "a" * 65000
    legacy = {"summary": "Legacy whole source", "key_points": ["Legacy point"]}
    result, requests = run([legacy] * 5, transcript=transcript)
    assert result.summary == "Legacy whole source" and len(requests) == 5
    assert len(requests[0]["messages"][1]["content"]) >= 20000
    assert len(requests[3]["messages"][1]["content"]) >= 5000


def test_missing_core_candidate_gets_one_planned_audit_chance():
    extra = "The repair budget is 400 dollars."
    fact2 = {"topic": "Budget", "claim": extra, "evidence": [2],
             "attribution": "source", "importance": "core"}
    final = copy.deepcopy(CANDIDATE)
    final["key_points"].append({"topic": "Budget", "text": extra, "fact_ids": ["F1_2"]})
    audit = {"additional_facts": [], "output": final,
             "checks": CHECKS + [{**CHECKS[1], "item_id": "P2"}]}
    result, requests = run([{"facts": [FACT, fact2]}, CANDIDATE, audit], transcript=SOURCE+"\n"+extra)
    assert len(requests) == 3 and result.key_points[-1] == extra


def test_unknown_candidate_ref_stops_before_audit():
    candidate = copy.deepcopy(CANDIDATE)
    candidate["summary"][0]["fact_ids"] = ["not-known"]
    with pytest.raises(LLMServiceError) as error:
        run([{"facts": [FACT]}, candidate])
    assert error.value.error_type == "llm_invalid_response"


def test_long_single_line_evidence_is_accepted_without_quote_limit():
    source = SOURCE + " " + "x" * (466 - len(SOURCE) - 1)
    fact = dict(FACT, evidence=[1])
    traces = []
    result, requests = run([{"facts": [fact]}, CANDIDATE, AUDIT], transcript=source, trace=traces.append)
    assert result.summary == SOURCE and len(requests) == 3
    assert len(traces[-1]["facts"][0]["quote"]) == 466
    assert traces[-1]["facts"][0]["end"] == 466


def test_named_speaker_outside_evidence_retains_separate_source_span():
    quote = "The library usually closes on Mondays for maintenance."
    source = "Speaker: Mira.\n" + quote
    fact = dict(FACT, claim=quote, evidence=[2], attribution="Mira")
    traces = []
    result, requests = run([{"facts": [fact]}, CANDIDATE, AUDIT], transcript=source, trace=traces.append)
    assert result.summary == SOURCE and len(requests) == 3
    evidence = traces[-1]["facts"][0]
    assert evidence["start"] == 15
    assert evidence["attribution_start"] == 9 and evidence["attribution_end"] == 13
    assert source[evidence["attribution_start"]:evidence["attribution_end"]] == "Mira"
    assert traces[-1]["audit"]["facts"][0]["attribution_start"] == 9


def test_facts_strategy_chunks_finer_than_legacy(monkeypatch):
    from app.services.llm_service import _summary_chunks
    monkeypatch.setattr(settings, "llm_summary_chunk_chars", 20000)
    monkeypatch.setattr(settings, "llm_summary_facts_chunk_chars", 8000)
    text = "x" * 25000
    legacy = _summary_chunks(text, min(settings.llm_summary_chunk_chars, settings.llm_max_input_chars))
    facts = _summary_chunks(text, min(settings.llm_summary_facts_chunk_chars, settings.llm_summary_chunk_chars, settings.llm_max_input_chars))
    assert len(facts) > len(legacy)
    assert max(len(chunk) for chunk in facts) <= 8000
