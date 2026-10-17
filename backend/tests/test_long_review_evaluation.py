"""Two-stage closed-draft acceptance with synthetic HTTP and owned temp files."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test_long_fidelity_evaluation import ROOT, response
from test_long_refine_evaluation import entry as previous_fixture, run_one

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/review_evaluate.py"


def load_entry():
    spec = importlib.util.spec_from_file_location("source_review_acceptance_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def entry(tmp_path, monkeypatch):
    prior = previous_fixture.__wrapped__(tmp_path, monkeypatch)
    run_one(prior)
    module = load_entry()
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, name, getattr(prior, name))
    module.select_phase("phase-3")
    for key, value in module.CONFIG.items():
        setattr(prior.test_settings, key, value)
    monkeypatch.setattr(module, "_live_runtime", lambda: (prior.test_settings, prior.test_service, prior.test_service._endpoint()))
    feedback_source = tmp_path / "backend/app/services/summary_review.py"
    feedback_source.write_bytes((ROOT / "backend/app/services/summary_review.py").read_bytes())
    copies = []
    for original in (SCRIPT, Path(__file__)):
        copied = tmp_path / original.name
        copied.write_bytes(original.read_bytes())
        copies.append(copied)
    monkeypatch.setattr(module, "candidate_assets", lambda: [*prior.prior.asset_paths(), feedback_source, *copies])
    # The parent verifier has its own private module; its historical fake binding is owned by tmp_path too.
    monkeypatch.setattr(module.parent_reader, "candidate_assets", prior.candidate_assets)
    module.prior, module.test_settings, module.test_service = prior, prior.test_settings, prior.test_service
    return module


def feedback_response(content='{"feedback":"Keep the example scope."}'):
    body = response(5).json()
    body["choices"][0]["message"]["content"] = content
    return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json=body)


def execute(entry, post=None):
    entry.freeze()
    entry.check()
    captured = []
    def provider(*args, **kwargs):
        captured.append(kwargs["json"])
        assert entry.read(entry.GROUP)["reserved_posts"] == 4 + len(captured)
        assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][-1]["status"] == "reserved"
        return feedback_response() if len(captured) == 1 else response(6)
    return entry.run(transport=SimpleNamespace(post=post or provider)), captured


def test_plan_is_offline_and_binds_phase2_exact_raw_draft(entry, monkeypatch):
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Plan read dotenv"))
    planned = entry.plan()
    assert planned["planned_posts"] == 2 and planned["work_reserved_posts"] == 4
    assert planned["samples"][0]["draft"]["summary"] == "Overview 4"
    assert planned["config"]["llm_summary_thinking_mode"] == "auto"
    assert planned["config"]["llm_summary_max_output_tokens"] == 4096
    assert not entry.RESULTS.exists()


def test_review_then_revision_preserves_source_parent_and_uses_actual_feedback(entry):
    previous = {path: path.read_bytes() for path in entry.prior.RESULTS.rglob("*") if path.is_file()}
    index, calls = execute(entry)
    assert index["posts"] == 2 and not index["stopped_on_error"]
    data = [json.loads(call["messages"][1]["content"].split("Evidence and draft:\n", 1)[1]) for call in calls]
    assert data[0]["original_transcript"] == data[1]["original_transcript"]
    assert "0100 Source-specific condition" in data[0]["original_transcript"]
    assert data[0]["draft"] == data[1]["draft"] == {"summary": "Overview 4", "key_points": ["Condition 4."]}
    assert data[1]["review_feedback"] == "Keep the example scope."
    assert [row["stage"] for row in entry.read(entry.RESULTS / "request-ledger.json")["requests"]] == ["review", "refine"]
    assert entry.verify_results()["work_posts"] == 6
    assert all(path.read_bytes() == raw for path, raw in previous.items())


@pytest.mark.parametrize("raw", ['not JSON', '{"feedback":""}', '{"feedback":42}', '{"feedback":"A","extra":1}',
                                '{"feedback":"A","feedback":"B"}'])
def test_invalid_feedback_is_charged_once_and_prevents_revision(entry, raw):
    calls = []
    def provider(*args, **kwargs):
        calls.append(kwargs["json"])
        return feedback_response(raw)
    index, _ = execute(entry, provider)
    assert index["posts"] == 1 and index["stopped_on_error"] and len(calls) == 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 5
    assert entry.verify_results()["stopped_on_error"]


@pytest.mark.parametrize("file", ["response-01.json", "en-long.json", "request-ledger.json", "closed-receipt.json"])
def test_parent_drift_before_send_never_preallocates_and_closes_current_phase(entry, file):
    entry.freeze()
    entry.check()
    target = entry.prior.RESULTS / file
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Parent drift sent a POST")))
    index = entry.read(entry.RESULTS / "result-index.json")
    assert index["posts"] == 0 and index["stopped_on_error"]
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 4


def test_closed_verifier_uses_its_frozen_feedback_parser_and_future_config(entry, monkeypatch):
    index, _ = execute(entry)
    assert not index["stopped_on_error"]
    monkeypatch.setattr(entry, "CONFIG", {})
    (entry.PROJECT / "backend/app/services/summary_review.py").write_text("raise RuntimeError('future parser')\n", encoding="utf-8")
    (entry.prior.RESULTS / "response-01.json").write_text("future live raw\n", encoding="utf-8")
    assert entry.verify_results()["work_posts"] == 6


def test_no_third_request_or_reopen(entry):
    execute(entry)
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Reopened closed phase")))


def test_capacity_failure_after_feedback_never_preallocates_second_post(entry):
    calls = []
    def provider(*args, **kwargs):
        calls.append(kwargs["json"])
        return feedback_response(json.dumps({"feedback": "necessary condition " * 4000}))
    index, _ = execute(entry, provider)
    assert index["posts"] == 1 and index["stopped_on_error"] and len(calls) == 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 5


def test_first_raw_byte_drift_even_with_identical_feedback_blocks_second_reservation(entry, monkeypatch):
    original = entry.feedback_from_raw
    touched = []
    def changed(frozen, ordinal):
        if not touched:
            touched.append(1)
            path = entry.RESULTS / "response-01.json"
            path.write_bytes(path.read_bytes() + b" ")
        return original(frozen, ordinal)
    monkeypatch.setattr(entry, "feedback_from_raw", changed)
    index, calls = execute(entry)
    assert index["posts"] == 1 and index["stopped_on_error"] and len(calls) == 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 5


def test_shared_lock_blocks_without_removing_another_owner(entry):
    entry.SHARED_LOCK.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        entry.freeze()
    assert entry.SHARED_LOCK.exists() and not entry.RESULTS.exists()
