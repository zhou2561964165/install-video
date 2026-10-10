"""Offline budget regressions: applicable skills first, narrow module interfaces.

Engineering conventions: skill priority; UI uses ui-ux-pro-max/design-system and
three-layer tokens; configurable capabilities; yt-dlp only ytdlp_service; LLM
only llm_service; visual scene is read-only. Fixtures contain no corpus or secrets.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import dotenv
import httpx
import pytest


RUNNER = Path(__file__).resolve().parents[2] / (
    "docs/acceptance-reports/2026-10-05-grounded-summary-evidence/scripts/evaluate.py"
)
URL = "https://offline.invalid/v1/chat/completions"


@pytest.fixture
def runner(monkeypatch, tmp_path):
    # Neutralize dotenv before importing the unmodified runner for the RED run.
    # The spy records the forbidden side effect without opening any user's .env.
    dotenv_calls = []
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: dotenv_calls.append((a, k)))
    spec = importlib.util.spec_from_file_location("grounded_budget_evaluation", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.dotenv_calls = dotenv_calls
    report = tmp_path / "report"
    report.mkdir()
    (report / "rubric.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(module, "REPORT", report)
    monkeypatch.setattr(module, "RESULTS", report / "results")
    monkeypatch.setattr(module, "SHARED_LEDGER", tmp_path / "prior/results/request-ledger.json")
    monkeypatch.setattr(module, "MODULES", {})
    monkeypatch.setattr(module, "settings", SimpleNamespace(**module.CONFIG))
    return module


@pytest.fixture
def clients(runner):
    opened = []

    def make(handler):
        http = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
        opened.append(http)
        frozen = {
            "module_sha256": {},
            "rubric_sha256": hashlib.sha256((runner.REPORT / "rubric.json").read_bytes()).hexdigest(),
            "samples": [{"id": "sample", "sections": 1, "expected_posts": 1}],
            "model": "offline-model", "options": {},
            "stage_prompts": {"extract": "extract only"},
        }
        client = runner.BudgetClient(http, "test-phase", frozen)
        client.sample = "sample"
        return client

    yield make
    for http in opened:
        http.close()


def post(runner, client):
    return client.post(URL, headers={"Authorization": "Bearer header-sentinel"}, json={
        "model": "offline-model", "temperature": 0.2,
        "max_tokens": runner.CONFIG["llm_summary_max_output_tokens"],
        "messages": [{"role": "system", "content": "extract only"}],
    })


def ledger(runner):
    return json.loads(runner.SHARED_LEDGER.read_text(encoding="utf-8"))


def evidence(runner):
    path = runner.RESULTS / "responses/01.json"
    assert path.exists(), "every received response must have durable sanitized evidence"
    row = ledger(runner)["requests"][0]
    assert row["response_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text(encoding="utf-8"))


def success():
    return httpx.Response(200, json={
        "choices": [{"message": {"content": "{}", "reasoning_content": "reasoning-sentinel"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    })


def test_import_does_not_load_dotenv(runner):
    assert runner.dotenv_calls == []


def test_session_refuses_existing_prior_caller_lock(runner):
    lock = runner.SHARED_LEDGER.parent / ".http-session-lock"
    lock.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        with runner.caller_guard():
            pytest.fail("an existing shared caller must exclude this session")
    assert lock.is_dir()  # Never remove somebody else's lock.
    assert not runner.SHARED_LEDGER.exists()


def test_standalone_post_refuses_shared_caller_before_reserving(runner, clients):
    lock = runner.SHARED_LEDGER.parent / ".http-session-lock"
    lock.mkdir(parents=True)
    sent = []
    client = clients(lambda request: sent.append(request) or success())
    with pytest.raises(FileExistsError):
        post(runner, client)
    assert sent == []
    assert client.sample_post == 0
    assert not runner.SHARED_LEDGER.exists()


def test_ledger_guard_refuses_standalone_reservation(runner, clients):
    lock = runner.SHARED_LEDGER.parent / "ledger.lock"
    lock.mkdir(parents=True)
    sent = []
    client = clients(lambda request: sent.append(request) or success())
    with pytest.raises(FileExistsError):
        post(runner, client)
    assert sent == []
    assert not runner.SHARED_LEDGER.exists()
    assert lock.is_dir()
    assert not (runner.SHARED_LEDGER.parent / ".http-session-lock").exists()


def test_response_completion_preserves_later_reservations_and_earlier_updates(runner, clients):
    runner.SHARED_LEDGER.parent.mkdir(parents=True)
    old = {"ordinal": 1, "phase": "earlier", "status": "reserved"}
    runner.SHARED_LEDGER.write_text(json.dumps({"ceiling": runner.CEILING, "requests": [old]}))

    def interleave(request):
        current = ledger(runner)
        assert current["requests"][1]["status"] == "reserved"
        current["requests"][0]["status"] = "completed_elsewhere"
        current["requests"].append({"ordinal": 3, "phase": "other", "status": "reserved"})
        runner.SHARED_LEDGER.write_text(json.dumps(current), encoding="utf-8")
        return success()

    post(runner, clients(interleave))
    rows = ledger(runner)["requests"]
    assert [row["ordinal"] for row in rows] == [1, 2, 3]
    assert rows[0]["status"] == "completed_elsewhere"
    assert rows[1]["status"] == "response"
    assert "response_sha256" in rows[1]
    assert rows[2] == {"ordinal": 3, "phase": "other", "status": "reserved"}


def test_http_error_has_hashed_evidence_without_provider_secrets(runner, clients):
    body = json.dumps({
        "error": {"type": "rate_limit_error", "code": "rate_limit_exceeded",
                  "message": "message-sentinel", "api_key": "key-sentinel",
                  "reasoning": "reasoning-sentinel"},
        "choices": [{"message": {"content": "echoed-key-sentinel"}}],
        "headers": {"Authorization": "provider-header-sentinel"},
    }).encode()
    calls = []
    client = clients(lambda request: calls.append(request) or httpx.Response(
        429, content=body, headers={"X-Secret": "response-header-sentinel"}))
    response = post(runner, client)
    saved = evidence(runner)
    assert response.status_code == saved["http_status"] == 429
    assert saved["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert saved["error_type"] == "rate_limit_error"
    assert saved["error_code"] == "rate_limit_exceeded"
    assert "sentinel" not in json.dumps(saved)
    assert "sentinel" not in runner.SHARED_LEDGER.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError):
        post(runner, client)
    assert len(calls) == len(ledger(runner)["requests"]) == client.sample_post == 1


def test_unknown_provider_error_markers_are_not_copied(runner, clients):
    client = clients(lambda request: httpx.Response(400, json={
        "error": {"type": "secret-sentinel", "code": "secret-sentinel"}}))
    post(runner, client)
    saved = evidence(runner)
    assert saved["error_type"] == saved["error_code"] == "other"
    assert "sentinel" not in json.dumps(saved)


@pytest.mark.parametrize("status", [200, 502])
def test_invalid_json_keeps_body_hash_and_reservation_without_raw_body(runner, clients, status):
    body = b'{"error": "invalid-json-secret-sentinel'
    calls = []
    client = clients(lambda request: calls.append(request) or httpx.Response(status, content=body))
    if status == 200:
        with pytest.raises(json.JSONDecodeError):
            post(runner, client)
    else:
        assert post(runner, client).status_code == 502
    saved = evidence(runner)
    assert saved["http_status"] == status
    assert saved["error_type"] == "invalid_json"
    assert saved["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert "sentinel" not in json.dumps(saved)
    with pytest.raises(RuntimeError):
        post(runner, client)
    assert len(calls) == len(ledger(runner)["requests"]) == client.sample_post == 1


def test_success_evidence_filters_nested_usage_and_reasoning(runner, clients):
    body = {
        "choices": [{"message": {"content": "{}", "reasoning_content": "reasoning-sentinel"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
                  "secret": "usage-sentinel",
                  "prompt_tokens_details": {"cached_tokens": 1, "api_key": "key-sentinel"}},
    }
    post(runner, clients(lambda request: httpx.Response(200, json=body)))
    saved = evidence(runner)
    assert saved["content"] == "{}"
    assert saved["finish_reason"] == "stop"
    assert saved["usage"] == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
                              "prompt_tokens_details": {"cached_tokens": 1}}
    assert "sentinel" not in json.dumps(saved)
    assert "sentinel" not in runner.SHARED_LEDGER.read_text(encoding="utf-8")


def test_success_evidence_preserves_supported_text_blocks(runner, clients):
    body = {"choices": [{"message": {"content": [
        {"type": "text", "text": '{"facts":'},
        {"type": "reasoning", "text": "reasoning-sentinel"},
        {"type": "text", "text": "[]}"}],
        "reasoning_content": "reasoning-sentinel"}, "finish_reason": "stop"}]}
    post(runner, clients(lambda request: httpx.Response(200, json=body)))
    saved = evidence(runner)
    assert saved["content"] == '{"facts":[]}'
    assert "sentinel" not in json.dumps(saved)


def test_transport_failure_remains_counted_and_exhausts_shared_budget(runner, clients, monkeypatch):
    monkeypatch.setattr(runner, "CEILING", 1)
    calls = []

    def fail(request):
        calls.append(request)
        raise httpx.ConnectError("transport-secret-sentinel", request=request)

    first = clients(fail)
    with pytest.raises(httpx.ConnectError):
        post(runner, first)
    assert ledger(runner)["requests"][0]["status"] == "ConnectError"
    assert first.sample_post == 1
    with pytest.raises(RuntimeError):
        post(runner, clients(lambda request: calls.append(request) or success()))
    assert len(calls) == len(ledger(runner)["requests"]) == 1
    assert "sentinel" not in runner.SHARED_LEDGER.read_text(encoding="utf-8")


def test_sequential_callers_reuse_released_locks_and_get_distinct_ordinals(runner, clients):
    post(runner, clients(lambda request: success()))
    post(runner, clients(lambda request: success()))
    assert [row["ordinal"] for row in ledger(runner)["requests"]] == [1, 2]
    assert (runner.RESULTS / "responses/01.json").exists()
    assert (runner.RESULTS / "responses/02.json").exists()
    assert not list(runner.SHARED_LEDGER.parent.glob("*.lock"))
