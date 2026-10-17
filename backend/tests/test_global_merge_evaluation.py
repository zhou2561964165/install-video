"""Hermetic phase-10 wrapper: preserve history, mature accounting and narrow interfaces.

Skills and UI three-tier tokens apply; protect env/accounts/models/UI; yt-dlp
stays in its service and scene stays read-only. No real HTTP or dotenv.
"""
import importlib.util
import json
from types import SimpleNamespace

import pytest

from test_native_merge_evaluation import ROOT, native_response
from test_native_merge_evaluation import entry as native_fixture

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/global_merge_evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Global merge wrapper missing"
    spec = importlib.util.spec_from_file_location("global_merge_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def entry(tmp_path, monkeypatch):
    prior = native_fixture.__wrapped__(tmp_path, monkeypatch)
    prior.freeze()
    prior.check()
    assert prior.run(transport=SimpleNamespace(post=lambda *a, **kw: native_response()))["posts"] == 1
    # The fixture's omitted earlier closed phases account for eleven reservations.
    group = prior.read(prior.GROUP)
    group["reserved_posts"] = 15
    prior.engine.durable(prior.GROUP, group)
    module = load_entry()
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, name, getattr(prior, name))
    module.select_phase("phase-10")
    monkeypatch.setattr(module.base.parent, "candidate_assets", prior.prior.candidate_assets)
    monkeypatch.setattr(module.base.parent.engine, "history_paths", prior.engine.history_paths)
    monkeypatch.setattr(module.base.engine, "history_paths", prior.engine.history_paths)
    monkeypatch.setattr(module, "candidate_assets", prior.prior.candidate_assets)
    monkeypatch.setattr(module.base, "_live_runtime", prior._live_runtime)
    module.prior = prior
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def test_plan_is_new_cap1_only_phase8_leaves_and_offline(entry, monkeypatch):
    monkeypatch.setattr(entry.base, "_live_runtime", lambda: pytest.fail("Offline plan read env"))
    plan = entry.plan()
    assert plan["phase"] == "phase-10" and plan["work_reserved_posts"] == 15
    assert plan["planned_posts"] == plan["phase_post_cap"] == 1
    assert plan["format_posts"] == plan["semantic_posts"] == 0
    assert plan["config"]["llm_model"] == "deepseek-v4-pro"
    sample = plan["samples"][0]
    assert [len(n["key_points"]) for n in sample["notes"]] == [11, 9]
    assert sample["parent_group_row"]["phase"] == "phase-8"
    assert all("phase-9" not in p and "response-03" not in p for p in sample["leaf_evidence"]["paths"].values())
    assert plan["network"] is plan["dotenv_read"] is False
    assert not entry.RESULTS.exists()


def test_single_merge_preserves_old_bytes_preallocates_and_replays(entry, monkeypatch):
    old = {p: p.read_bytes() for prior in (entry.prior, entry.prior.prior)
        for p in prior.RESULTS.rglob("*") if p.is_file()}
    ready(entry)
    calls = []

    def post(url, **kw):
        calls.append(kw["json"])
        assert url.endswith("/responses")
        assert entry.read(entry.GROUP)["reserved_posts"] == 16
        assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][-1]["status"] == "reserved"
        return native_response()

    result = entry.run(transport=SimpleNamespace(post=post))
    assert result["posts"] == len(calls) == 1 and not result["stopped_on_error"]
    payload = calls[0]
    assert payload["reasoning"] == {"effort": "none"} and payload["max_output_tokens"] == 8192
    assert payload["text"]["format"]["schema"]["properties"]["key_points"]["maxItems"] == 14
    supplied = payload["input"][-1]["content"]
    assert "Organize themes across all section notes" in supplied
    assert "Leaf 1 condition 10." in supplied and "Leaf 2 condition 8." in supplied
    assert "Native condition" not in supplied and "Leaf 3" not in supplied
    assert "0100 Source-specific condition" in supplied and "Ending condition and consequence." in supplied
    assert all(p.read_bytes() == raw for p, raw in old.items())
    (entry.PROJECT / "backend/app/services/llm_service.py").write_text("live candidate drift", encoding="utf-8")
    monkeypatch.setattr(entry.base, "_live_runtime", lambda: pytest.fail("Replay read env"))
    assert entry.verify_results()["posts"] == 1
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Reopened phase")))


@pytest.mark.parametrize("parent,name", [("leaf", "response-01.json"), ("leaf", "response-02.json"),
    ("contrast", "request-ledger.json"), ("contrast", "closed-receipt.json")])
def test_parent_drift_is_refused_before_any_reservation(entry, parent, name):
    ready(entry)
    prior = entry.prior.prior if parent == "leaf" else entry.prior
    path = prior.RESULTS / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Drift sent HTTP")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 15
    assert entry.read(entry.TRACKER)["status"] == ("closed" if parent == "leaf" else "frozen")
    if parent == "leaf":
        assert entry.verify_results()["posts"] == 0


def test_missing_closed_phase9_or_wrong_cumulative_count_cannot_allocate(entry):
    group = entry.read(entry.GROUP)
    group["reserved_posts"] = 14
    entry.prior.engine.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="15"):
        entry.freeze()
    assert not entry.RESULTS.exists()
    group["reserved_posts"] = 15
    group["phases"] = [r for r in group["phases"] if r["phase"] != "phase-9"]
    entry.prior.engine.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="phase-9"):
        entry.plan()


def test_second_request_refused_without_another_send(entry, monkeypatch):
    ready(entry)
    original = entry.base.ServiceAdapter.summarize_text

    def twice(self, *a, **kw):
        result = original(self, *a, **kw)
        kw["client"].post(self._endpoint(), headers={}, json={})
        return result

    monkeypatch.setattr(entry.base.ServiceAdapter, "summarize_text", twice)
    calls = []
    result = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: calls.append(1) or native_response()))
    assert result["posts"] == len(calls) == 1 and result["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 16
    assert entry.verify_results()["stopped_on_error"]


def test_incomplete_counts_once_and_stops(entry):
    ready(entry)
    calls = []
    result = entry.run(transport=SimpleNamespace(post=lambda *a, **kw:
        calls.append(1) or native_response(status="incomplete")))
    assert result["posts"] == len(calls) == 1 and result["stopped_on_error"]
    assert entry.verify_results()["stopped_on_error"]


def test_root_audit_is_required_and_ancestor_mock_project_rejected(entry, monkeypatch):
    monkeypatch.delenv("CODEX_ACCEPTANCE_CALLER", raising=False)
    with pytest.raises(RuntimeError, match="root"):
        entry.run(caller="root")
    monkeypatch.setattr(entry, "PROJECT", ROOT.parent)
    with pytest.raises(RuntimeError, match="isolated"):
        entry.run(transport=object())
    assert not entry.RESULTS.exists()


@pytest.mark.parametrize("owned", ["REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "RESULTS", "TRACKER"])
def test_mock_owned_paths_cannot_escape(entry, monkeypatch, owned):
    monkeypatch.setattr(entry, owned, ROOT / "escaped")
    with pytest.raises(RuntimeError, match="isolated"):
        entry.run(transport=object())


def test_offline_check_and_cli_plan_do_not_read_env(entry, monkeypatch, capsys):
    entry.freeze()
    monkeypatch.setattr(entry.base, "_live_runtime", lambda: pytest.fail("Offline operation read env"))
    assert entry.check()["dotenv_read"] is False
    entry.main(["--phase", "phase-10", "--plan"])
    assert json.loads(capsys.readouterr().out)["phase_post_cap"] == 1


def test_only_new_phase10_and_candidate_inventory():
    entry = load_entry()
    for phase in ("phase-8", "phase-9", "../phase-10"):
        with pytest.raises(ValueError):
            entry.select_phase(phase)
    names = {p.relative_to(ROOT).as_posix() for p in entry.candidate_assets()}
    assert {SCRIPT.relative_to(ROOT).as_posix(), "backend/tests/test_global_merge_evaluation.py",
        "backend/tests/test_summary_scope_guidance.py", "backend/app/services/llm_service.py",
        "docs/superpowers/plans/2026-10-15-global-merge-prompt.md",
        "docs/acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-10-global-merge-tool.md",
        *(f"docs/acceptance-reports/2026-10-13-long-summary-fidelity/phase-{phase}-{kind}.md"
          for phase in (8, 9) for kind in ("report", "content-diagnosis"))} <= names
