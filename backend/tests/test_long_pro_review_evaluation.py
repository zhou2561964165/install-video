"""An explicit model comparison: same draft, source, stages and durable counts."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test_long_fidelity_evaluation import ROOT, response
from test_long_review_evaluation import entry as previous_fixture, execute

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/pro_review_evaluate.py"


@pytest.fixture
def entry(tmp_path, monkeypatch):
    prior = previous_fixture.__wrapped__(tmp_path, monkeypatch)
    execute(prior)
    spec = importlib.util.spec_from_file_location("pro_review_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for key in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, key, getattr(prior, key))
    module.select_phase("phase-4")
    for key, value in module.CONFIG.items():
        setattr(prior.test_settings, key, value)
    monkeypatch.setattr(module, "_live_runtime", lambda: (prior.test_settings, prior.test_service, prior.test_service._endpoint()))
    monkeypatch.setattr(module.parent_reader, "candidate_assets", prior.candidate_assets)
    target = tmp_path / SCRIPT.name
    target.write_bytes(SCRIPT.read_bytes())
    monkeypatch.setattr(module, "candidate_assets", lambda: [*prior.candidate_assets(), target])
    module.prior = prior
    module.test_settings, module.test_service = prior.test_settings, prior.test_service
    return module


def run(entry, bad_model=False):
    entry.freeze()
    entry.check()
    captured = []
    def provider(*args, **kwargs):
        captured.append(kwargs["json"])
        assert entry.read(entry.GROUP)["reserved_posts"] == 6 + len(captured)
        body = response(8).json()
        body["model"] = "wrong-model" if bad_model else "deepseek-v4-pro"
        if len(captured) == 1:
            body["choices"][0]["message"]["content"] = '{"feedback":"Keep the instance scope."}'
        return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json=body)
    return entry.run(transport=SimpleNamespace(post=provider)), captured


def test_explicit_model_plan_preserves_real_parent_identity_and_cumulative_posts(entry, monkeypatch):
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Offline plan read env"))
    plan = entry.plan()
    assert plan["work_reserved_posts"] == 6 and plan["planned_posts"] == 2
    assert plan["config"]["llm_model"] == "deepseek-v4-pro"
    assert plan["samples"][0]["parent_model"] == "offline-model"
    assert plan["samples"][0]["draft_evidence"]["phase"] == "phase-3"


def test_same_draft_two_declared_pro_requests_no_default_change_or_old_byte_change(entry):
    old = {p: p.read_bytes() for p in entry.prior.RESULTS.rglob("*") if p.is_file()}
    index, calls = run(entry)
    assert index["posts"] == 2 and not index["stopped_on_error"]
    assert all(body["model"] == "deepseek-v4-pro" for body in calls)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    assert frozen["model_comparison"] == {"parent_model": "offline-model", "candidate_model": "deepseek-v4-pro",
        "mode": "explicit_comparison_no_fallback_no_default_change"}
    data = [json.loads(body["messages"][1]["content"].split("Evidence and draft:\n", 1)[1]) for body in calls]
    assert data[0]["draft"] == data[1]["draft"] == {"key_points": ["Condition 6."], "summary": "Overview 6"}
    assert data[0]["original_transcript"] == data[1]["original_transcript"]
    assert entry.verify_results()["work_posts"] == 8
    assert all(path.read_bytes() == original for path, original in old.items())


def test_unlisted_model_cannot_allocate_or_send(entry):
    entry.test_settings.llm_model = "unlisted-model"
    with pytest.raises(RuntimeError):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_model_mismatch_is_reserved_once_and_stops_without_fallback(entry):
    index, calls = run(entry, bad_model=True)
    assert index["posts"] == 1 and index["stopped_on_error"] and len(calls) == 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 7
    assert entry.verify_results()["stopped_on_error"]


def test_runtime_model_drift_after_freeze_stops_before_first_reservation(entry):
    entry.freeze()
    entry.check()
    entry.test_settings.llm_model = "changed-model"
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Drift sent a POST")))
    assert entry.read(entry.RESULTS / "result-index.json")["posts"] == 0
    assert entry.read(entry.GROUP)["reserved_posts"] == 6


def test_runtime_model_drift_after_review_stops_before_second_reservation(entry):
    entry.freeze()
    entry.check()
    calls = []
    def provider(*args, **kwargs):
        calls.append(kwargs["json"])
        body = response(7).json()
        body["model"] = "deepseek-v4-pro"
        body["choices"][0]["message"]["content"] = '{"feedback":"Keep the scope."}'
        entry.test_settings.llm_model = "changed-model"
        return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json=body)
    index = entry.run(transport=SimpleNamespace(post=provider))
    assert index["posts"] == 1 and index["stopped_on_error"] and len(calls) == 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 7
