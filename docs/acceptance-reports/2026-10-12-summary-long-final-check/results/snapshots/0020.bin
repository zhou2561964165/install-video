"""Full long-source acceptance, isolated synthetic transport and finite budget.

Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only through ytdlp_service; scene remains read-only. No provider or dotenv.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-12-summary-long-final-check/scripts/evaluate.py"
PARENT_TEST = ROOT / "backend/tests/test_summary_capacity_evaluation.py"
spec = importlib.util.spec_from_file_location("long_final_parent_fixture", PARENT_TEST)
parent_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent_tests)
source = parent_tests.source


@pytest.fixture
def entry(tmp_path, monkeypatch):
    assert SCRIPT.exists(), "Final long entry is missing"
    parent = parent_tests.entry.__wrapped__(tmp_path, monkeypatch)
    parent_tests.ready(parent)
    parent.run(transport=SimpleNamespace(post=lambda *a, **kw: source.response()))
    assert parent.verify_results()["work_posts"] == 13
    spec = importlib.util.spec_from_file_location("long_final_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = tmp_path / "long-final-report"
    for name, value in {"PROJECT": tmp_path, "REPORT": report, "RESULTS": report / "results",
            "CORPUS": parent.CORPUS, "GROUP": tmp_path / "long-final-group.json",
            "TRACKER": tmp_path / "phase-4.json", "SHARED_LOCK": parent.SHARED_LOCK,
            "PARENT_GROUP": parent.GROUP, "PARENT_REPORT": parent.REPORT,
            "PARENT_TRACKER": parent.TRACKER}.items():
        monkeypatch.setattr(module, name, value)
    group = parent.read(parent.GROUP)
    module.io.exclusive(module.GROUP, group | {"status": "active", "hard_ceiling": 16,
        "parent_posts": 13, "budget_adjustment": {"from": 13, "to": 16},
        "continuation_parent": {"path": str(parent.GROUP),
            "sha256": module.io.digest(parent.GROUP.read_bytes()), "parent_posts": 13}})
    monkeypatch.setattr(module, "runtime", lambda: (parent.test_settings, parent.test_service, parent.test_service._endpoint()))
    monkeypatch.setattr(module, "asset_paths", lambda: sorted(set(parent.asset_paths()
        + module.parent_asset_paths())))
    module.test_parent, module.test_settings, module.test_service = parent, parent.test_settings, parent.test_service
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def test_fresh_full_source_three_posts_close_at_sixteen(entry, monkeypatch):
    parent_bytes = entry.PARENT_GROUP.read_bytes()
    ready(entry)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    assert len(frozen["sample_plan"]) == 1
    long = frozen["sample_plan"][0]
    assert long["id"] == "en-long" and long["expected_posts"] == 3 and len(long["chunks"]) == 2
    assert "reused_notes" not in frozen and "reused_leaf_notes" not in str(frozen)
    assert [stage["stage"] for stage in frozen["stages"]["en-long"]] == ["extract", "extract", "merge"]
    seen = []
    def post(*a, **kw):
        seen.append(kw["json"])
        ordinal = len(seen)
        assert entry.read(entry.GROUP)["reserved_posts"] == 13 + ordinal
        assert entry.read(entry.TRACKER)["reserved_posts"] == ordinal
        return source.response(100 + ordinal)
    index = entry.run(transport=SimpleNamespace(post=post))
    assert len(seen) == index["posts"] == 3 and not index["stopped_on_error"]
    assert seen[0] == frozen["stages"]["en-long"][0]["payload"]
    assert seen[1] == frozen["stages"]["en-long"][1]["payload"]
    merge = seen[2]["messages"][1]["content"]
    assert "Condition 101." in merge and "Condition 102." in merge
    assert "Condition 3." not in merge and "Condition 4." not in merge
    assert entry.PARENT_GROUP.read_bytes() == parent_bytes
    assert entry.read(entry.GROUP)["reserved_posts"] == 16
    assert entry.read(entry.GROUP)["status"] == "closed"
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Verify read dotenv"))
    assert entry.verify_results()["work_posts"] == 16
    assert entry.verify_results()["semantic_quality_verified"] is False


def test_fourth_request_refused_before_transport(entry, monkeypatch):
    ready(entry)
    original = entry.test_service.summarize_text
    def extra(source_text, **kw):
        result = original(source_text, **kw)
        original(source_text, **kw)
        return result
    monkeypatch.setattr(entry.test_service, "summarize_text", extra)
    calls = []
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **kw:
        calls.append(1) or source.response(len(calls))))
    assert len(calls) == index["posts"] == 3 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 16
    assert entry.verify_results()["stopped_on_error"]


@pytest.mark.parametrize("kind", ["parent", "source", "normalizer", "version"])
def test_drift_blocks_before_any_new_http_and_seals(entry, monkeypatch, kind):
    ready(entry)
    if kind == "parent":
        entry.PARENT_GROUP.write_text("changed")
    elif kind == "source":
        (entry.CORPUS / "en-long.txt").write_text("changed")
    elif kind == "normalizer":
        (entry.PROJECT / "backend/app/services/summary_json.py").write_text("changed")
    else:
        original = entry.versions
        monkeypatch.setattr(entry, "versions", lambda: original() | {"httpx": "changed"})
    calls = []
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: calls.append(1)))
    assert calls == [] and entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 13


def test_parent_drift_after_first_post_stops_without_refund(entry):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        entry.PARENT_GROUP.write_text("changed")
        return source.response()
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == [1] and index["stopped_on_error"]
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 14


@pytest.mark.parametrize("kind", ["receipt", "prefix", "count"])
def test_parent_chain_refuses_rebound_or_forged_evidence_before_freeze(entry, kind):
    if kind == "receipt":
        (entry.PARENT_REPORT / "results/closed-receipt.json").write_text("changed")
    else:
        group = entry.read(entry.GROUP)
        if kind == "prefix":
            group["phases"][0]["phase"] = "wrong"
        else:
            group["reserved_posts"] = 0
        entry.io.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="Parent|Continuation"):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_frozen_normalizer_and_last_raw_binding_survive_live_change(entry, monkeypatch):
    ready(entry)
    calls = []
    entry.run(transport=SimpleNamespace(post=lambda *a, **kw:
        calls.append(1) or parent_tests.parent_tests.malformed_response(len(calls))))
    (entry.PROJECT / "backend/app/services/summary_json.py").write_text("raise RuntimeError('changed')")
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Verify read dotenv"))
    assert entry.verify_results()["posts"] == 3
    assert entry.read(entry.RESULTS / "en-long.json")["result"]["summary"] == "Complete overview 3"
    assert "DO-NOT-SAVE" not in (entry.RESULTS / "response-03.json").read_text()


@pytest.mark.parametrize("kind", ["http", "reservation"])
def test_failures_keep_preallocated_attempt_and_close(entry, monkeypatch, kind):
    ready(entry)
    if kind == "reservation":
        original, fired = entry.durable, []
        def broken(path, value):
            if path == entry.GROUP and value.get("reserved_posts") == 14 and not fired:
                fired.append(True)
                raise OSError("synthetic disk failure")
            return original(path, value)
        monkeypatch.setattr(entry, "durable", broken)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        raise httpx.ConnectError("DO-NOT-SAVE")
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == ([1] if kind == "http" else []) and index["posts"] == 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 14
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.verify_results()["stopped_on_error"]


def test_plan_offline_single_true_long_source(entry, monkeypatch):
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Plan read dotenv"))
    plan = entry.plan()
    assert plan["normal_posts"] == plan["maximum_posts"] == 3
    assert plan["hard_ceiling"] == 16 and plan["work_reserved_posts"] == 13
    assert [s["id"] for s in plan["samples"]] == ["en-long"]
    assert plan["historical_posts"] == 25  # isolated fixture historical17+8, not +13
    assert plan["config"]["llm_summary_max_output_tokens"] == 16384
    assert plan["config"]["llm_summary_output_token_ceiling"] == 24576
    assert plan["config"]["llm_summary_point_ceiling"] == 14


def test_inventory_preserves_parent_thirteen_and_excludes_reused_wire_and_mutable_budget():
    spec = importlib.util.spec_from_file_location("long_final_inventory", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assets = set(module.inventory_paths())
    assert module.GROUP not in assets and module.PARENT_GROUP in assets
    assert set(module.parent_asset_paths()) <= assets
    assert SCRIPT in assets and Path(__file__) in assets
    assert {ROOT / "docs/acceptance-reports" / name for name in (
        "2026-10-11-summary-content-resume/review-criteria.md",
        "2026-10-11-summary-content-local-repair/review-criteria.md",
        "2026-10-12-summary-content-capacity-repair/review-criteria.md",
        "2026-10-12-summary-long-final-check/review-criteria.md",
        "2026-10-09-summary-quality-repaired/rubric.json",
    )} <= assets
    assert not any(path.name in {"payload-03.json", "payload-04.json", "payload-05.json"} for path in assets)
    assert all(path.exists() and not path.name.startswith(".env") for path in assets)


def rebind_closed_hashes(entry):
    receipt_path = entry.RESULTS / "closed-receipt.json"
    receipt = entry.read(receipt_path)
    receipt.update(index_sha256=entry.io.digest((entry.RESULTS / "result-index.json").read_bytes()),
        ledger_sha256=entry.io.digest((entry.RESULTS / "request-ledger.json").read_bytes()))
    entry.io.durable(receipt_path, receipt)
    checksum = entry.io.digest(receipt_path.read_bytes())
    tracker = entry.read(entry.TRACKER)
    tracker["closed_receipt_sha256"] = checksum
    entry.io.durable(entry.TRACKER, tracker)
    group = entry.read(entry.GROUP)
    group["phases"][-1]["closed_receipt_sha256"] = checksum
    entry.io.durable(entry.GROUP, group)


@pytest.mark.parametrize("extra", [False, True])
def test_verifier_rejects_success_with_missing_or_extra_source_after_hash_rebind(entry, extra):
    ready(entry)
    entry.run(transport=SimpleNamespace(post=lambda *a, **kw: source.response()))
    path = entry.RESULTS / "result-index.json"
    index = entry.read(path)
    index["samples"] = index["samples"] * 2 if extra else []
    entry.io.durable(path, index)
    rebind_closed_hashes(entry)
    with pytest.raises(RuntimeError, match="Successful phase|receipt/index"):
        entry.verify_results()


def test_verifier_preserves_last_raw_semantics_after_result_hash_rebind(entry):
    ready(entry)
    calls = []
    entry.run(transport=SimpleNamespace(post=lambda *a, **kw:
        calls.append(1) or source.response(len(calls))))
    path = entry.RESULTS / "en-long.json"
    result = entry.read(path)
    result["result"]["summary"] = "Overview 1"
    entry.io.durable(path, result)
    checksum = entry.io.digest(path.read_bytes())
    index_path = entry.RESULTS / "result-index.json"
    index = entry.read(index_path)
    index["samples"][0]["result_sha256"] = checksum
    entry.io.durable(index_path, index)
    ledger_path = entry.RESULTS / "request-ledger.json"
    ledger = entry.read(ledger_path)
    for row in ledger["requests"]:
        row["result_sha256"] = checksum
    entry.io.durable(ledger_path, ledger)
    rebind_closed_hashes(entry)
    with pytest.raises(RuntimeError, match="last raw"):
        entry.verify_results()


@pytest.mark.parametrize("kind", ["missing", "ambiguous"])
def test_verifier_ast_guard_requires_exactly_one_comparison(entry, monkeypatch, kind):
    original = entry.inspect.getsource(entry._base_verify)
    assert entry.VERIFY_ADAPTATION["matched_comparisons"] == 1
    assert entry.VERIFY_ADAPTATION["ast_before_sha256"] != entry.VERIFY_ADAPTATION["ast_after_sha256"]
    changed = (original.replace("len(samples) != 3", "len(samples) != 9") if kind == "missing"
        else original + "    if len(samples) != 3:\n        pass\n")
    monkeypatch.setattr(entry.inspect, "getsource", lambda fn: changed)
    with pytest.raises(RuntimeError, match="exactly one"):
        entry.build_verifier()
