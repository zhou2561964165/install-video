"""Capacity continuation uses paid synthetic leaves, never a provider or dotenv.

Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only through ytdlp_service; scene remains read-only.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-12-summary-content-capacity-repair/scripts/evaluate.py"
PARENT_TEST = ROOT / "backend/tests/test_summary_local_repair_evaluation.py"
spec = importlib.util.spec_from_file_location("capacity_parent_fixture", PARENT_TEST)
parent_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent_tests)
source = parent_tests.source


@pytest.fixture
def entry(tmp_path, monkeypatch):
    assert SCRIPT.exists(), "Capacity entry is missing"
    parent = parent_tests.entry.__wrapped__(tmp_path, monkeypatch)
    group = parent.read(parent.GROUP)
    group.update(reserved_posts=5, phases=[{
        "phase": "summary-thinking-single-1", "status": "closed", "reserved_posts": 5}])
    parent.io.durable(parent.GROUP, group)
    source.ready(parent)
    calls = []
    def response(*a, **kw):
        calls.append(1)
        if len(calls) == 5:
            return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"),
                json={"model": "offline-model", "choices": [{"finish_reason": "length",
                    "message": {"content": "", "reasoning_content": "DO-NOT-SAVE"}}]})
        return source.response(len(calls))
    assert parent.run(transport=SimpleNamespace(post=response))["stopped_on_error"]
    assert parent.verify_results()["work_posts"] == 10
    spec = importlib.util.spec_from_file_location("capacity_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = tmp_path / "capacity-report"
    for name, value in {"PROJECT": tmp_path, "REPORT": report, "RESULTS": report / "results",
            "CORPUS": parent.CORPUS, "GROUP": tmp_path / "capacity-group.json",
            "TRACKER": tmp_path / "phase-3.json", "SHARED_LOCK": parent.SHARED_LOCK,
            "PARENT_GROUP": parent.GROUP, "PARENT_REPORT": parent.REPORT,
            "PARENT_TRACKER": parent.TRACKER}.items():
        monkeypatch.setattr(module, name, value)
    group = parent.read(parent.GROUP)
    module.io.exclusive(module.GROUP, group | {"status": "active", "hard_ceiling": 13,
        "parent_posts": 10, "budget_adjustment": {"from": 10, "to": 13},
        "continuation_parent": {"path": str(parent.GROUP),
            "sha256": module.io.digest(parent.GROUP.read_bytes()), "parent_posts": 10}})
    settings, service = parent.test_settings, parent.test_service
    for key, value in module.CONFIG.items():
        setattr(settings, key, value)
    monkeypatch.setattr(module, "runtime", lambda: (settings, module.ServiceProxy(service), service._endpoint()))
    monkeypatch.setattr(module, "asset_paths", lambda: sorted(set(parent.asset_paths()
        + module.parent_asset_paths())))
    module.test_parent, module.test_settings, module.test_service = parent, settings, service
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def test_three_posts_skip_paid_leaves_and_close_at_thirteen(entry, monkeypatch):
    original_group = entry.PARENT_GROUP.read_bytes()
    ready(entry)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    assert [s["expected_posts"] for s in frozen["sample_plan"]] == [1, 1, 1]
    long = frozen["sample_plan"][-1]
    assert long["source_input_mode"] == "reused_leaf_notes" and len(long["chunks"]) == 2
    assert frozen["stages"]["en-long"][0]["stage"] == "merge_reused"
    seen = []
    def post(*a, **kw):
        seen.append(kw["json"])
        ordinal = len(seen)
        assert entry.read(entry.GROUP)["reserved_posts"] == 10 + ordinal
        assert entry.read(entry.TRACKER)["reserved_posts"] == ordinal
        assert len(entry.read(entry.RESULTS / "request-ledger.json")["requests"]) == ordinal
        return source.response(ordinal)
    index = entry.run(transport=SimpleNamespace(post=post))
    assert len(seen) == index["posts"] == 3 and not index["stopped_on_error"]
    assert seen[-1] == frozen["stages"]["en-long"][0]["payload"]
    assert seen[-1]["messages"][1]["content"].endswith(frozen["reused_notes"])
    assert all(payload["max_tokens"] <= 24576 for payload in seen)
    group = entry.read(entry.GROUP)
    assert group["reserved_posts"] == 13 and group["status"] == "closed"
    assert entry.PARENT_GROUP.read_bytes() == original_group
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Verify read dotenv"))
    assert entry.verify_results()["work_posts"] == 13
    with pytest.raises(RuntimeError, match="never reopen"):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Reopened")))


@pytest.mark.parametrize("name", ["group", "raw", "payload", "notes", "source"])
def test_parent_or_notes_drift_blocks_before_http(entry, name):
    ready(entry)
    paths = {"group": entry.PARENT_GROUP, "raw": entry.PARENT_REPORT / "results/response-03.json",
        "payload": entry.PARENT_REPORT / "results/payload-04.json",
        "notes": entry.PARENT_REPORT / "results/payload-05.json",
        "source": entry.CORPUS / "en-long.txt"}
    paths[name].write_text("changed")
    calls = []
    with pytest.raises((RuntimeError, ValueError)):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: calls.append(1)))
    assert calls == [] and entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 10


def test_parent_failure_after_post_stops_without_refund(entry):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        entry.PARENT_GROUP.write_text("changed")
        return source.response()
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == [1] and index["stopped_on_error"]
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 11


@pytest.mark.parametrize("mutation", ["notes_value", "notes_context", "raw_model", "raw_finish", "phase_prefix"])
def test_rebound_parent_hashes_still_require_exact_leaf_chain(entry, mutation):
    parent = entry.test_parent
    if mutation == "phase_prefix":
        group = entry.read(entry.GROUP)
        group["phases"][0]["phase"] = "wrong-phase"
        entry.io.durable(entry.GROUP, group)
    else:
        name = "payload-05.json" if mutation.startswith("notes") else "response-03.json"
        path = parent.RESULTS / name
        value = entry.read(path)
        if mutation.startswith("notes"):
            frozen = entry.read(parent.RESULTS / "provenance.json")
            prefix = frozen["stages"]["en-long"][-1]["payload"]["messages"][1]["content"]
            notes = json.loads(value["messages"][1]["content"][len(prefix):])
            notes[0]["summary" if mutation == "notes_value" else "source_context"] = "changed"
            value["messages"][1]["content"] = prefix + json.dumps(notes, ensure_ascii=False)
        else:
            value["model" if mutation == "raw_model" else "finish_reason"] = "changed"
        entry.io.durable(path, value)
        ledger_path = parent.RESULTS / "request-ledger.json"
        ledger = entry.read(ledger_path)
        ledger["requests"][4 if name.startswith("payload") else 2][
            "payload_sha256" if name.startswith("payload") else "response_sha256"] = entry.io.digest(path.read_bytes())
        entry.io.durable(ledger_path, ledger)
        receipt_path = parent.RESULTS / "closed-receipt.json"
        receipt = entry.read(receipt_path)
        receipt["ledger_sha256"] = entry.io.digest(ledger_path.read_bytes())
        entry.io.durable(receipt_path, receipt)
        receipt_hash = entry.io.digest(receipt_path.read_bytes())
        tracker = entry.read(parent.TRACKER)
        tracker["closed_receipt_sha256"] = receipt_hash
        entry.io.durable(parent.TRACKER, tracker)
        parent_group = entry.read(parent.GROUP)
        parent_group["phases"][-1]["closed_receipt_sha256"] = receipt_hash
        entry.io.durable(parent.GROUP, parent_group)
        group = entry.read(entry.GROUP)
        group["continuation_parent"]["sha256"] = entry.io.digest(parent.GROUP.read_bytes())
        group["phases"] = parent_group["phases"]
        entry.io.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="Parent|Continuation"):
        entry.freeze()
    assert not entry.RESULTS.exists()


@pytest.mark.parametrize("failure", ["http", "reserve", "overflow"])
def test_error_preserves_preallocation_and_refuses_over_thirteen(entry, monkeypatch, failure):
    ready(entry)
    if failure == "overflow":
        group = entry.read(entry.GROUP)
        group["reserved_posts"] = 13
        entry.io.durable(entry.GROUP, group)
    if failure == "reserve":
        original = entry.durable
        fired = []
        def broken(path, value):
            if path == entry.GROUP and value.get("reserved_posts") == 11 and not fired:
                fired.append(True)
                raise OSError("synthetic disk failure")
            return original(path, value)
        monkeypatch.setattr(entry, "durable", broken)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        raise httpx.ConnectError("DO-NOT-SAVE")
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == ([1] if failure == "http" else []) and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == (13 if failure == "overflow" else 11)
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.verify_results()["stopped_on_error"]


def test_frozen_decoder_survives_live_drift_and_omits_reasoning(entry, monkeypatch):
    ready(entry)
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: parent_tests.malformed_response(1)))
    assert not index["stopped_on_error"] and index["posts"] == 3
    (entry.PROJECT / "backend/app/services/summary_json.py").write_text("raise RuntimeError('changed')")
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Verify read dotenv"))
    assert entry.verify_results()["posts"] == 3
    assert "DO-NOT-SAVE" not in (entry.RESULTS / "response-03.json").read_text()


def test_plan_offline_reports_reuse_and_config(entry, monkeypatch):
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Plan read dotenv"))
    plan = entry.plan()
    assert plan["normal_posts"] == plan["maximum_posts"] == 3
    assert plan["hard_ceiling"] == 13 and plan["work_reserved_posts"] == 10
    assert plan["historical_posts"] == 25  # isolated fixture has 17 + 8, never +10
    assert plan["reused_parent_posts"] == [3, 4]
    assert plan["config"]["llm_summary_max_output_tokens"] == 16384
    assert plan["config"]["llm_summary_output_token_ceiling"] == 24576
    assert plan["config"]["llm_summary_point_ceiling"] == 14


def test_actual_inventory_freezes_parent_evidence_and_all_criteria_not_mutable_budget():
    spec = importlib.util.spec_from_file_location("capacity_inventory", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assets = set(module.inventory_paths())
    assert module.GROUP not in assets and module.PARENT_GROUP in assets
    assert set(module.parent_asset_paths()) <= assets
    assert SCRIPT in assets and Path(__file__) in assets
    assert {ROOT / "docs/acceptance-reports" / name for name in (
        "2026-10-11-summary-content-resume/scripts/evaluate.py",
        "2026-10-11-summary-content-local-repair/scripts/evaluate.py",
        "2026-10-11-summary-content-resume/review-criteria.md",
        "2026-10-11-summary-content-local-repair/review-criteria.md",
        "2026-10-12-summary-content-capacity-repair/review-criteria.md",
        "2026-10-09-summary-quality-repaired/rubric.json",
        "2026-10-09-adaptive-short-medium/review-criteria.md",
        "2026-10-09-adaptive-summary-final/review-criteria.md",
        "2026-10-09-adaptive-summary/report.md",
    )} <= assets
    assert all(path.exists() and not path.name.startswith(".env") for path in assets)
