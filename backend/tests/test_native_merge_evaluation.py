"""Finite native merge contrast; hermetic IO and narrow mature interfaces.

Engineering skills/tokens apply; protect UI/env/models/history; scene read-only
and yt-dlp confined to its service. No real HTTP or dotenv in this module.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test_long_fidelity_evaluation import ROOT, response
from test_long_normal_evaluation import entry as normal_fixture

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/native_merge_evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Native merge adapter missing"
    spec = importlib.util.spec_from_file_location("native_merge_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def entry(tmp_path, monkeypatch):
    module = load_entry()
    prior = normal_fixture.__wrapped__(tmp_path, monkeypatch)
    prior.freeze()
    prior.check()
    calls = []
    def post(*a, **kw):
        calls.append(1)
        body = response(len(calls)).json()
        n = (11, 9, 20)[len(calls) - 1]
        body["choices"][0]["message"]["content"] = json.dumps({
            "summary": f"Overview {len(calls)}", "key_points": [f"Leaf {len(calls)} condition {i}." for i in range(n)]})
        return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json=body)
    assert prior.run(transport=SimpleNamespace(post=post))["stopped_on_error"]
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, name, getattr(prior, name))
    module.select_phase("phase-9")
    monkeypatch.setattr(module.parent, "candidate_assets", prior.candidate_assets)
    monkeypatch.setattr(module.parent.engine, "history_paths", prior.engine.history_paths)
    monkeypatch.setattr(module.engine, "history_paths", prior.engine.history_paths)
    # Frozen inventory is fully owned by this system-temp project.
    monkeypatch.setattr(module, "candidate_assets", prior.candidate_assets)
    for key, value in module.CONFIG.items():
        setattr(prior.test_settings, key, value)
    monkeypatch.setattr(module, "_live_runtime", lambda: (
        prior.test_settings, prior.test_service, prior.test_service._endpoint()))
    module.prior, module.test_service = prior, prior.test_service
    return module


def native_response(*, status="completed", model="deepseek-v4-pro", count=14):
    return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid/responses"), json={
        "object": "response", "status": status, "model": model,
        "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
        "output": [{"type": "reasoning", "content": "DO-NOT-SAVE"},
            {"type": "message", "role": "assistant", "status": "completed",
             "content": [{"type": "output_text", "text": json.dumps({"summary": "Native overview",
                "key_points": [f"Native condition {i}." for i in range(count)]})}]}]})


def ready(entry):
    entry.freeze()
    entry.check()


def test_plan_is_offline_explicit_single_merge_of_only_accepted_notes(entry, monkeypatch):
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Plan read dotenv"))
    planned = entry.plan()
    assert planned["planned_posts"] == planned["phase_post_cap"] == 1
    assert planned["config"]["llm_model"] == "deepseek-v4-pro"
    assert planned["config"]["llm_summary_thinking_mode"] == "disabled"
    assert [len(n["key_points"]) for n in planned["samples"][0]["notes"]] == [11, 9]
    assert "response-03.json" not in json.dumps(planned["samples"][0]["leaf_evidence"]["paths"])
    assert not entry.RESULTS.exists()


def test_one_native_merge_preallocated_and_frozen_verify_is_independent_of_live_parent(entry, monkeypatch):
    old = {p: p.read_bytes() for p in entry.prior.RESULTS.rglob("*") if p.is_file()}
    ready(entry)
    calls = []
    def post(url, **kw):
        calls.append(kw["json"])
        assert url.endswith("/responses")
        assert entry.read(entry.GROUP)["reserved_posts"] == 4
        assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][-1]["status"] == "reserved"
        return native_response()
    result = entry.run(transport=SimpleNamespace(post=post))
    assert result["posts"] == 1 and not result["stopped_on_error"]
    payload = calls[0]
    assert payload["reasoning"] == {"effort": "none"} and payload["max_output_tokens"] == 8192
    assert payload["text"]["format"]["schema"]["properties"]["key_points"]["maxItems"] == 14
    supplied = payload["input"][-1]["content"]
    assert "Leaf 1 condition 10." in supplied and "Leaf 2 condition 8." in supplied
    assert "Leaf 3" not in supplied and "0100 Source-specific condition" in supplied
    assert "Ending condition and consequence." in supplied
    assert all(p.read_bytes() == raw for p, raw in old.items())
    safe = entry.read(entry.RESULTS / "response-01.json")
    assert safe["object"] == "response" and safe["status"] == "completed"
    assert "finish_reason" not in safe and "DO-NOT-SAVE" not in json.dumps(safe)
    (entry.prior.RESULTS / "response-01.json").write_text("live drift", encoding="utf-8")
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Verify read dotenv"))
    assert entry.verify_results()["posts"] == 1


@pytest.mark.parametrize("name", ["payload-01.json", "response-01.json", "response-02.json", "request-ledger.json", "closed-receipt.json", "en-long.json", "provenance.json"])
def test_parent_drift_after_freeze_stops_before_payment_and_closes(entry, name):
    ready(entry)
    path = entry.prior.RESULTS / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Parent drift paid")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 3
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.verify_results()["posts"] == 0


@pytest.mark.parametrize("fault", ["incomplete", "model", "overpoints", "http"])
def test_bad_provider_response_counts_once_never_retries(entry, fault):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        if fault == "http":
            raise httpx.ConnectError("offline")
        return native_response(status="incomplete" if fault == "incomplete" else "completed",
            model="wrong" if fault == "model" else "deepseek-v4-pro", count=15 if fault == "overpoints" else 14)
    result = entry.run(transport=SimpleNamespace(post=post))
    assert result["posts"] == 1 and result["stopped_on_error"] and calls == [1]
    assert entry.verify_results()["stopped_on_error"]
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=post))


def test_second_stage_refused_before_reservation(entry, monkeypatch):
    ready(entry)
    original = entry.ServiceAdapter.summarize_text
    def twice(self, *a, **kw):
        result = original(self, *a, **kw)
        kw["client"].post(self._endpoint(), headers={}, json={})
        return result
    monkeypatch.setattr(entry.ServiceAdapter, "summarize_text", twice)
    calls = []
    result = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: calls.append(1) or native_response()))
    assert result["posts"] == len(calls) == 1 and result["stopped_on_error"]


def test_live_guard_and_mock_workspace_guard_before_writes(entry, monkeypatch):
    monkeypatch.delenv("CODEX_ACCEPTANCE_CALLER", raising=False)
    with pytest.raises(RuntimeError, match="root"):
        entry.run(caller="root")
    monkeypatch.setattr(entry, "PROJECT", ROOT.parent)
    with pytest.raises(RuntimeError, match="isolated"):
        entry.run(transport=object())
    assert not entry.RESULTS.exists()


@pytest.mark.parametrize("owned", ["REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "RESULTS", "TRACKER"])
def test_mock_owned_containment_reuses_audited_guard(entry, monkeypatch, owned):
    monkeypatch.setattr(entry, owned, ROOT / "escaped")
    with pytest.raises(RuntimeError, match="isolated"):
        entry.run(transport=object())


def test_offline_check_and_cli_help_plan_never_load_runtime(entry, monkeypatch, capsys):
    entry.freeze()
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Offline path read dotenv"))
    assert entry.check()["dotenv_read"] is False
    entry.main(["--phase", "phase-9", "--plan"])
    assert json.loads(capsys.readouterr().out)["phase_post_cap"] == 1
    with pytest.raises(SystemExit) as caught:
        entry.main(["--help"])
    assert caught.value.code == 0


@pytest.mark.parametrize("fault", ["object", "message_status", "refusal", "two_messages"])
def test_true_native_response_shape_is_not_replaced_with_chat_stop(entry, fault):
    ready(entry)
    body = native_response().json()
    message = body["output"][1]
    if fault == "object":
        body["object"] = "chat.completion"
    elif fault == "message_status":
        message["status"] = "incomplete"
    elif fault == "refusal":
        message["content"] = [{"type": "refusal", "refusal": "No"}]
    else:
        body["output"].append(message)
    result = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: httpx.Response(
        200, request=httpx.Request("POST", "https://offline.invalid"), json=body)))
    assert result["posts"] == 1 and result["stopped_on_error"]
    assert entry.verify_results()["stopped_on_error"]


def test_only_fresh_phase9_and_asset_inventory():
    module = load_entry()
    with pytest.raises(ValueError):
        module.select_phase("phase-8")
    names = {p.relative_to(ROOT).as_posix() for p in module.candidate_assets()}
    assert "backend/tests/test_native_merge_evaluation.py" in names
    assert "docs/superpowers/plans/2026-10-15-native-merge-check.md" in names
    assert "docs/acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-9-native-merge-tool.md" in names
