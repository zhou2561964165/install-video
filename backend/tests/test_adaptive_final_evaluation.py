"""Only new final-phase budget boundaries; prior guard regressions remain immutable."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_adaptive_repair_evaluation import entry as repair_entry, response

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-09-adaptive-summary-final/scripts/evaluate.py"
PRIOR_SCRIPT = ROOT / "docs/acceptance-reports/2026-10-09-adaptive-summary-repair/scripts/evaluate.py"


@pytest.fixture
def entry(repair_entry, tmp_path, monkeypatch):
    old = repair_entry
    prior_script = old.REPORT / "scripts/evaluate.py"
    prior_script.parent.mkdir(parents=True)
    prior_script.write_bytes(PRIOR_SCRIPT.read_bytes())
    helper_snapshot = tmp_path / "helper.py"
    helper_snapshot.write_bytes(old.HELPER.read_bytes())
    prior_assets = old.asset_paths
    monkeypatch.setattr(old, "asset_paths", lambda: prior_assets() + [prior_script, helper_snapshot])
    old.freeze()
    old.check()
    old.run(transport=SimpleNamespace(post=lambda *a, **k: response()))
    spec = importlib.util.spec_from_file_location("adaptive_final_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for key in ("PROJECT", "CORPUS", "GROUP", "LONG_TRACKER", "SHORT_TRACKER", "SHARED_LOCK",
                "OLD_FINAL", "OLD_REPAIRED", "LONG_REPORT", "SHORT_REPORT"):
        monkeypatch.setattr(module, key, getattr(old, key))
    monkeypatch.setattr(module, "REPORT", tmp_path / "final-report")
    monkeypatch.setattr(module, "RESULTS", tmp_path / "final-report/results")
    monkeypatch.setattr(module, "TRACKER", tmp_path / "final-tracker.json")
    # First baseline imports use these new globals after final-phase implementation.
    monkeypatch.setattr(module, "REPAIR_REPORT", old.REPORT, raising=False)
    monkeypatch.setattr(module, "REPAIR_TRACKER", old.TRACKER, raising=False)
    monkeypatch.setattr(module, "REPAIR_RUNNER", prior_script, raising=False)
    monkeypatch.setattr(module, "HELPER", helper_snapshot)
    monkeypatch.setattr(module, "load_repair_verifier", lambda: old, raising=False)
    monkeypatch.setattr(module, "runtime", old.runtime)
    monkeypatch.setattr(module, "asset_paths", lambda: prior_assets() + [prior_script, helper_snapshot,
        old.TRACKER, *[p for p in old.RESULTS.rglob("*") if p.is_file()]])
    module.prior_bytes = {p: p.read_bytes() for p in [prior_script, old.TRACKER,
        *[p for p in old.RESULTS.rglob("*") if p.is_file()]]}
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def test_final_plan_includes_closed_repair_and_exact_hard_ceiling(entry, monkeypatch):
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Offline plan read environment"))
    plan = entry.plan()
    assert plan["phase"] == "adaptive-transcript-repair-final"
    assert plan["prior_posts"] == 24
    assert plan["maximum_posts"] == 2
    assert plan["maximum_work_posts"] == plan["hard_ceiling"] == 26


def test_two_requests_durably_reserve_25_26_verify_26_and_preserve_prior_assets(entry):
    ready(entry)
    reservations = []

    def post(*args, **kwargs):
        tracker = entry.read(entry.TRACKER)
        ledger = entry.read(entry.RESULTS / "request-ledger.json")
        reservations.append(tracker["reserved_posts"])
        assert tracker["reserved_posts"] == 24 + len(ledger["requests"])
        assert ledger["requests"][-1]["status"] == "reserved"
        return response()

    entry.run(transport=SimpleNamespace(post=post))
    assert reservations == [25, 26]
    assert entry.verify_results()["work_posts"] == 26
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert all(p.read_bytes() == raw for p, raw in entry.prior_bytes.items())
    with pytest.raises(RuntimeError, match="reopen|started"):
        entry.run(transport=SimpleNamespace(post=post))


def test_third_request_refused_before_transport_and_does_not_exceed_26(entry, monkeypatch):
    ready(entry)
    settings, original, _ = entry.runtime()

    class DoubleRequest(original):
        @staticmethod
        def summarize_text(source, *, title, output_language, client):
            summary = original.summarize_text(source, title=title, output_language=output_language, client=client)
            if title == "en-medium":
                original.summarize_text(source, title=title, output_language=output_language, client=client)
            return summary

    monkeypatch.setattr(entry, "runtime", lambda: (settings, DoubleRequest, "https://offline.invalid/chat/completions"))
    sent = []

    def post(*args, **kwargs):
        sent.append(entry.read(entry.TRACKER)["reserved_posts"])
        return response()

    index = entry.run(transport=SimpleNamespace(post=post))
    assert sent == [25, 26]
    assert index["stopped_on_error"] is True and index["posts"] == 2
    assert entry.verify_results()["work_posts"] == 26


@pytest.mark.parametrize("change", ["open_tracker", "ledger_path", "prior_snapshot", "runner_bytes"])
def test_final_allocation_rejects_changed_closed_repair_identity(entry, change):
    if change in {"open_tracker", "ledger_path"}:
        value = entry.read(entry.REPAIR_TRACKER)
        value["status" if change == "open_tracker" else "ledger"] = (
            "running" if change == "open_tracker" else str(entry.PROJECT / "foreign-ledger.json"))
        entry.io.durable(entry.REPAIR_TRACKER, value)
    elif change == "prior_snapshot":
        value = entry.read(entry.REPAIR_REPORT / "results/provenance.json")
        first = next(iter(value["snapshots"].values()))
        (entry.REPAIR_REPORT / "results" / first["file"]).write_bytes(b"tampered prior snapshot")
    else:
        entry.REPAIR_RUNNER.write_bytes(b"changed prior runner")
    with pytest.raises(RuntimeError, match="repair|Historical|snapshot|closed|frozen"):
        entry.freeze()
    assert not entry.RESULTS.exists()
