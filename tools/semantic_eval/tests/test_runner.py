"""Offline transport tests; every write and lock stays inside pytest temp paths."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel


@pytest.fixture
def runner(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "runner.py"
    spec = importlib.util.spec_from_file_location("semantic_runner_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    monkeypatch.setattr(module, "dependencies", lambda: {"ragas": "0.4.3"})
    monkeypatch.setattr(module, "load_key", lambda: "test-secret")
    for name in module.ASSETS:
        target = tmp_path / "tools/semantic_eval" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
    cases = [{"id": "scope", "source": "one calculator", "response": "all calculators",
              "expected_supported": False, "error_kind": "scope", "core_questions": ["which?"]}]
    (tmp_path / "tools/semantic_eval/cases.json").write_text(json.dumps(cases), encoding="utf-8")
    (tmp_path / "tools/semantic_eval/bound_sources.json").write_text('{"assets": []}', encoding="utf-8")
    for name, value in [(module.GROUP, {"reserved_posts": 10}),
                        (module.PHASE7, {"status": "frozen", "reserved_posts": 0}),
                        (module.IO_HELPER, {})]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
    module._test_output = tmp_path / "results/phase-1"
    monkeypatch.setattr(module, "evaluate", fake_evaluate)
    return module


class Answer(BaseModel):
    value: int


def fake_evaluate(source, response, complete, adapter_path=None):
    assert source == "one calculator" and response == "all calculators"
    complete("decompose " + response, Answer)
    second = complete("NLI " + source, Answer)
    return {"score": float(second["value"]), "all_supported": bool(second["value"]),
            "statements": [response], "verdicts": [{"statement": response, "verdict": second["value"]}],
            "results": [{"statement": response, "verdict": second["value"]}], "limitations": ["diagnostic only"]}


def transport(calls, *, fail=False, secret=False):
    def handle(request):
        calls.append(json.loads(request.content))
        if fail:
            raise httpx.ConnectError("test-secret", request=request)
        text = "test-secret" if secret else '{"value":0}'
        return httpx.Response(200, json={"status": "completed", "model": "deepseek-v4-pro",
            "output": [{"type": "reasoning", "content": "PRIVATE REASONING"},
                       {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5, "extra": "test-secret"}})
    return httpx.MockTransport(handle)


def test_two_calls_persist_before_send_and_verify_verdict_statistics(runner):
    output = runner._test_output
    runner.freeze(output)
    calls = []
    inner = transport(calls)
    def handler(request):
        ledger = json.loads((output / "request-ledger.json").read_text())
        assert ledger["requests"][-1]["status"] == "reserved"
        assert len(ledger["requests"]) == len(calls) + 1
        return inner.handle_request(request)
    result = runner.run(output, caller="root", transport=httpx.MockTransport(handler))
    assert len(calls) == 2
    assert "expected_supported" not in json.dumps(calls)
    assert result["statistics"] == {"cases": 1, "false_accepts": 0, "false_rejects": 0}
    assert runner.verify(output)["reserved_posts"] == 2
    saved = "\n".join(p.read_text(encoding="utf-8") for p in output.rglob("*.json"))
    assert "test-secret" not in saved and "PRIVATE REASONING" not in saved


@pytest.mark.parametrize("change", ["tamper", "cap"])
def test_preflight_tamper_or_cap_never_sends(runner, change):
    output = runner._test_output
    if change == "cap":
        cases = json.loads((runner.PROJECT / "tools/semantic_eval/cases.json").read_text()) * 9
        for index, case in enumerate(cases):
            cases[index] = dict(case, id=str(index))
        (runner.PROJECT / "tools/semantic_eval/cases.json").write_text(json.dumps(cases))
        with pytest.raises(RuntimeError):
            runner.freeze(output)
        return
    runner.freeze(output)
    (runner.PROJECT / "tools/semantic_eval/CASE_NOTES.md").write_text("changed")
    calls = []
    with pytest.raises(RuntimeError):
        runner.run(output, caller="root", transport=transport(calls))
    assert calls == []
    assert json.loads((output / "request-ledger.json").read_text())["status"] == "closed"


@pytest.mark.parametrize("secret", [False, True])
def test_first_error_stops_closes_and_does_not_persist_secret(runner, secret):
    output = runner._test_output
    runner.freeze(output)
    calls = []
    with pytest.raises(RuntimeError):
        runner.run(output, caller="root", transport=transport(calls, fail=not secret, secret=secret))
    assert len(calls) == 1
    assert runner.verify(output)["reserved_posts"] == 1
    assert json.loads((output / "request-ledger.json").read_text())["status"] == "closed"
    assert "test-secret" not in "".join(p.read_text() for p in output.rglob("*.json"))
    with pytest.raises(RuntimeError):
        runner.run(output, caller="root", transport=transport(calls))
    assert len(calls) == 1


@pytest.mark.parametrize(("text", "key"), [
    (r'{"statements":["\u0074est-secret"]}', "test-secret"),
    (r'{"nested":[{"\u0074est-secret":"safe"}]}', "test-secret"),
    (r'{"nested":{"message":"test\"secret"}}', 'test"secret'),
], ids=["escaped-value", "nested-object-key", "escaped-quote"])
def test_decoded_credential_echo_redacts_raw_and_stops_first_call(runner, monkeypatch, text, key):
    output = runner._test_output
    monkeypatch.setattr(runner, "load_key", lambda: key)
    runner.freeze(output)
    calls = []
    base = transport(calls)
    def handler(request):
        body = base.handle_request(request).json()
        body["output"][1]["content"][0]["text"] = text
        return httpx.Response(200, json=body)
    with pytest.raises(RuntimeError):
        runner.run(output, caller="root", transport=httpx.MockTransport(handler))
    assert len(calls) == 1
    assert runner.read(output / "raw/01.json")["output_text"] == "[redacted]"
    assert runner.read(output / "result.json")["results"] == []
    assert runner.verify(output)["outcome"] == "error"
    assert key not in "".join(p.read_text() for p in output.rglob("*.json"))


def test_invalid_output_json_closes_without_retry_or_repair(runner):
    output = runner._test_output
    runner.freeze(output)
    calls = []
    base = transport(calls)
    def handler(request):
        body = base.handle_request(request).json()
        body["output"][1]["content"][0]["text"] = '{"value":'
        return httpx.Response(200, json=body)
    with pytest.raises(RuntimeError):
        runner.run(output, caller="root", transport=httpx.MockTransport(handler))
    assert len(calls) == 1
    assert runner.read(output / "raw/01.json")["output_text"] == '{"value":'
    assert runner.verify(output)["outcome"] == "error"


def test_missing_nli_does_not_get_success(runner, monkeypatch):
    output = runner._test_output
    runner.freeze(output)
    def incomplete(source, response, complete, adapter_path):
        complete("one", Answer)
        return {"score": 1, "all_supported": True}
    monkeypatch.setattr(runner, "evaluate", incomplete)
    with pytest.raises(RuntimeError):
        runner.run(output, caller="root", transport=transport([]))
    assert runner.verify(output)["outcome"] == "error"


def test_verify_detects_result_tampering(runner):
    output = runner._test_output
    runner.freeze(output)
    runner.run(output, caller="root", transport=transport([]))
    (output / "result.json").write_text('{}')
    with pytest.raises(RuntimeError):
        runner.verify(output)


@pytest.mark.parametrize("problem", ["wrong_model", "duplicate_json", "uncoerced_bool", "consumed_raw_drift", "third_call"])
def test_protocol_and_budget_errors_stop_before_another_send(runner, monkeypatch, problem):
    output = runner._test_output
    runner.freeze(output)
    calls = []
    base = transport(calls)
    def handler(request):
        reply = base.handle_request(request)
        body = reply.json()
        if problem == "wrong_model":
            body["model"] = "other-model"
        if problem in {"duplicate_json", "uncoerced_bool"}:
            body["output"][1]["content"][0]["text"] = ('{"value":0,"value":1}' if problem == "duplicate_json" else '{"value":true}')
        return httpx.Response(200, json=body)
    if problem in {"uncoerced_bool", "consumed_raw_drift", "third_call"}:
        def custom(source, response, complete, adapter_path):
            first = complete("first", Answer)
            if problem == "uncoerced_bool":
                assert type(first["value"]) is bool
                raise RuntimeError("Adapter rejects original boolean verdict")
            if problem == "consumed_raw_drift":
                (output / "raw/01.json").write_text('{}')
            complete("second", Answer)
            complete("third", Answer)
        monkeypatch.setattr(runner, "evaluate", custom)
    with pytest.raises(RuntimeError):
        runner.run(output, caller="root", transport=httpx.MockTransport(handler))
    assert len(calls) == (2 if problem == "third_call" else 1)
    assert json.loads((output / "result.json").read_text())["outcome"] == "error"


def test_mock_transport_rejected_before_real_project_writes(runner, monkeypatch):
    original = Path(__file__).resolve().parents[3]
    monkeypatch.setattr(runner, "PROJECT", original)
    with pytest.raises(RuntimeError, match="system-temp"):
        runner.run(original / runner.DEFAULT_OUTPUT, caller="root", transport=transport([]))


def test_live_adapter_can_change_after_closed_snapshot_replay(runner):
    output = runner._test_output
    runner.freeze(output)
    runner.run(output, caller="root", transport=transport([]))
    (runner.PROJECT / "tools/semantic_eval/ragas_adapter.py").write_text("changed")
    assert runner.verify(output)["outcome"] == "completed"


def test_shared_caller_lock_blocks_without_sending(runner):
    output = runner._test_output
    runner.freeze(output)
    calls = []
    with runner.directory_guard(runner.PROJECT / runner.LOCK):
        with pytest.raises(FileExistsError):
            runner.run(output, caller="root", transport=transport(calls))
    assert calls == []
    assert json.loads((output / "request-ledger.json").read_text())["status"] == "frozen"


def test_freeze_requires_locked_environment_and_never_loads_key(runner, monkeypatch):
    def forbidden():
        raise AssertionError("Secret loader must not execute")
    monkeypatch.setattr(runner, "load_key", forbidden)
    assert runner.freeze(runner._test_output)["network"] is False
    with pytest.raises(FileExistsError):
        runner.freeze(runner._test_output)
