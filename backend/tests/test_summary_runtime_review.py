"""Regression cases for source-stop and unpaid pre-POST configuration boundaries."""

import json

import httpx
import pytest

from app.config import settings
from app.services.llm_service import LLMServiceError, summarize_text
from test_grounded_pipeline import configured, SOURCE, FACT, CANDIDATE, AUDIT, extraction_response
from test_normalized_pipeline import invoke


@pytest.fixture(autouse=True)
def retry_policy(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_format_retries", 1)
    monkeypatch.setattr(settings, "llm_summary_semantic_retries", 1)
    monkeypatch.setattr(settings, "llm_summary_max_extra_calls", 2)


@pytest.mark.parametrize("field,value", [("quote", "manufactured"), ("source_id", "invented")])
@pytest.mark.parametrize("wrapper", ["plain", "fenced", "marker"])
def test_forbidden_extraction_provenance_stays_terminal_after_normalization(field, value, wrapper):
    payload = {"fact_1": {**FACT, field: value}}
    if wrapper == "marker":
        payload["type"] = "json_object"
    raw = json.dumps(payload)
    if wrapper == "fenced":
        raw = "```json\n" + raw + "\n```"
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        invoke([raw, extraction_response([FACT]), CANDIDATE, AUDIT], requests, traces)
    assert error.value.error_type == "llm_invalid_response"
    assert len(requests) == 1
    assert traces[-1]["error_category"] == "source"
    assert traces[-1]["retry_budget"]["used"] == 0
    assert len(traces[-1]["stages"]) == 1
    assert traces[-1]["stages"][0]["status"] == "failed"


@pytest.mark.parametrize("strategy", ["facts", "auto"])
@pytest.mark.parametrize("field,value", [
    ("llm_base_url", ""), ("llm_base_url", " "), ("llm_model", ""), ("llm_model", " "),
])
def test_missing_endpoint_configuration_is_blocked_before_paid_count(monkeypatch, strategy, field, value):
    monkeypatch.setattr(settings, "llm_summary_strategy", strategy)
    monkeypatch.setattr(settings, field, value)
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        invoke([], requests, traces)
    assert error.value.error_type == "llm_unconfigured"
    assert requests == []
    assert traces[-1]["strategy"] == "facts"
    assert traces[-1]["error_category"] == "config"
    assert traces[-1]["paid_calls"] == 0
    assert traces[-1]["retry_budget"]["used"] == 0
    stage = traces[-1]["stages"][-1]
    assert stage["stage"] == "extract" and stage["attempt"] == 1
    assert stage["status"] == "blocked" and stage["paid_attempt"] is False


@pytest.mark.parametrize("field,value,error_type", [
    ("llm_summary_max_extra_calls", 3, "llm_unconfigured"),
    ("llm_summary_facts_max_source_chars", 10, "llm_input_too_large"),
])
def test_existing_first_stage_preflight_still_runs_before_attempt_trace(monkeypatch, field, value, error_type):
    monkeypatch.setattr(settings, "llm_base_url", "")
    monkeypatch.setattr(settings, field, value)
    requests, traces = [], []
    with pytest.raises(LLMServiceError) as error:
        invoke([], requests, traces)
    assert error.value.error_type == error_type
    assert requests == [] and traces == []


@pytest.mark.parametrize("field", ["llm_base_url", "llm_model"])
def test_config_blocked_repair_does_not_consume_extra_call(monkeypatch, field):
    requests, traces = [], []

    def respond(request):
        requests.append(request)
        monkeypatch.setattr(settings, field, "")
        return httpx.Response(200, json={"choices": [
            {"finish_reason": "stop", "message": {"content": "invalid"}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMServiceError) as error:
            summarize_text(SOURCE, title="Policy", output_language="en", client=client, diagnostic=traces.append)
    assert error.value.error_type == "llm_unconfigured"
    assert len(requests) == 1 and traces[-1]["paid_calls"] == 1
    assert traces[-1]["retry_budget"]["used"] == 0
    assert traces[-1]["retry_budget"]["format_used"] == 0
    stage = traces[-1]["stages"][-1]
    assert stage["attempt"] == 2 and stage["status"] == "blocked"
    assert stage["error_category"] == "config" and stage["paid_attempt"] is False


def test_attempted_network_failure_remains_counted_and_terminal():
    requests, traces = [], []
    with pytest.raises(LLMServiceError):
        invoke([httpx.ConnectError("offline")], requests, traces)
    assert len(requests) == 1 and traces[-1]["paid_calls"] == 1
    assert traces[-1]["error_category"] == "network"
    assert traces[-1]["retry_budget"]["used"] == 0
    stage = traces[-1]["stages"][-1]
    assert stage["status"] == "failed" and stage["paid_attempt"] is True
