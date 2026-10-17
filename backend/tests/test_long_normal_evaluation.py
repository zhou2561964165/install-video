"""Hermetic normal-profile acceptance; skills/tokens/narrow interfaces apply.

No real HTTP, dotenv or historical mutation. yt-dlp stays in its service and
scene is read-only; UI changes require both design skills and three token tiers.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test_long_fidelity_evaluation import ROOT, response
from test_long_fidelity_evaluation import entry as source_fixture

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/normal_evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Normal generation adapter is missing"
    spec = importlib.util.spec_from_file_location("normal_generation_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_profile_is_explicit_normal_and_does_not_override_provider_model():
    module = load_entry()
    assert "llm_model" not in module.CONFIG and "llm_provider" not in module.CONFIG
    expected = {"llm_summary_fidelity_mode": "off", "llm_summary_thinking_mode": "auto",
        "llm_summary_response_format": "auto", "llm_summary_max_output_tokens": 4096,
        "llm_summary_output_token_ceiling": 8192, "llm_summary_generation_mode": "single",
        "llm_summary_strategy": "legacy", "llm_summary_length_mode": "adaptive",
        "llm_summary_format_retries": 0, "llm_summary_semantic_retries": 0,
        "llm_summary_max_extra_calls": 0}
    assert {key: module.CONFIG[key] for key in expected} == expected


@pytest.fixture
def entry(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "backend"))
    module = load_entry()
    prior = source_fixture.__wrapped__(tmp_path, monkeypatch)
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, name, getattr(prior, name))
    module.select_phase("phase-8")
    monkeypatch.setattr(module.engine, "history_paths", prior.history_paths)
    monkeypatch.setattr(module, "candidate_assets", prior.asset_paths)
    for key, value in module.CONFIG.items():
        setattr(prior.test_settings, key, value)
    monkeypatch.setattr(module, "_live_runtime", lambda: (
        prior.test_settings, prior.test_service, prior.test_service._endpoint()))
    module.test_settings, module.test_service = prior.test_settings, prior.test_service
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def test_plan_offline_finite_single_seen_source(entry, monkeypatch):
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Plan read env"))
    plan = entry.plan()
    assert plan["phase_post_cap"] == plan["planned_posts"] == 3
    assert [s["id"] for s in plan["samples"]] == ["en-long"]
    assert plan["samples"][0]["expected_posts"] == 3
    assert plan["dotenv_read"] is False and not entry.RESULTS.exists()


def test_arity_change_refused_before_freeze_allocation(entry, monkeypatch):
    original = entry._samples
    def extra_stage():
        samples = original()
        samples[0]["expected_posts"] = 4
        return samples
    monkeypatch.setattr(entry, "_samples", extra_stage)
    with pytest.raises(RuntimeError, match="cap 3"):
        entry.freeze()
    assert not entry.RESULTS.exists() and not entry.GROUP.exists()


def test_check_uses_frozen_assets_without_runtime(entry, monkeypatch):
    entry.freeze()
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Check read env"))
    assert entry.check()["dotenv_read"] is False


def test_asset_inventory_includes_new_entry_tests_plan_and_reviews():
    module = load_entry()
    names = {p.relative_to(ROOT).as_posix() for p in module.candidate_assets()}
    assert {SCRIPT.relative_to(ROOT).as_posix(), "backend/tests/test_long_normal_evaluation.py",
        "backend/tests/test_summary_scope_guidance.py",
        "docs/superpowers/plans/2026-10-15-normal-long-generation.md",
        "docs/acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-7-subject-checks-production-final.md",
        "docs/acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-8-normal-generation-tool.md"} <= names


def test_three_posts_preallocated_production_source_notes_and_full_merge(entry, monkeypatch):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(kw["json"])
        assert entry.read(entry.GROUP)["reserved_posts"] == len(calls)
        assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][-1]["status"] == "reserved"
        return response(len(calls))
    result = entry.run(transport=SimpleNamespace(post=post))
    assert result["posts"] == 3 and not result["stopped_on_error"]
    assert "Output language: source" in calls[0]["messages"][1]["content"]
    assert "grammatical subject" in calls[0]["messages"][0]["content"]
    merged = calls[2]["messages"][1]["content"]
    assert "Condition 1." in merged and "Condition 2." in merged
    assert "0100 Source-specific condition" in merged and "Ending condition and consequence." in merged
    assert "Evidence and draft:" not in merged
    assert all(p["model"] == "offline-model" for p in calls)
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Verify read env"))
    assert entry.verify_results()["posts"] == 3
    assert entry.verify_results()["semantic_quality_verified"] is False


@pytest.mark.parametrize("name", ["payload-01.json", "response-01.json"])
def test_prior_packet_drift_blocks_next_independent_leaf(entry, name):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        if name.startswith("payload"):
            p = entry.RESULTS / name
            p.write_bytes(p.read_bytes() + b" ")
        else:
            # Response bytes are persisted after transport returns; mutate at the
            # next payload boundary before the wrapper checks all previous raw.
            original = entry.expected_payload
            def tamper(*args):
                p = entry.RESULTS / name
                p.write_bytes(p.read_bytes() + b" ")
                return original(*args)
            entry.engine.expected_payload = tamper
        return response()
    result = entry.run(transport=SimpleNamespace(post=post))
    assert calls == [1] and result["posts"] == 1 and result["stopped_on_error"]


@pytest.mark.parametrize("caller,audit", [(None, None), ("root", None), (None, "root"), ("worker", "root")])
def test_live_caller_rejected_before_any_state_write(entry, monkeypatch, caller, audit):
    if audit is None:
        monkeypatch.delenv("CODEX_ACCEPTANCE_CALLER", raising=False)
    else:
        monkeypatch.setenv("CODEX_ACCEPTANCE_CALLER", audit)
    with pytest.raises(RuntimeError, match="root"):
        entry.run(caller=caller)
    assert not entry.RESULTS.exists() and not entry.GROUP.exists() and not entry.SHARED_LOCK.exists()


def test_live_dual_declaration_allows_delegation_without_env_read(entry, monkeypatch):
    monkeypatch.setenv("CODEX_ACCEPTANCE_CALLER", "root")
    monkeypatch.setattr(entry.engine, "run", lambda **kw: {"delegated": True})
    assert entry.run(caller="root") == {"delegated": True}


def test_mock_guard_rejects_real_workspace_ancestor_and_owned_escape(entry, monkeypatch):
    for unsafe in (ROOT, ROOT.parent, ROOT / "tmp", Path("E:/not-system-temp")):
        monkeypatch.setattr(entry, "PROJECT", unsafe)
        with pytest.raises(RuntimeError, match="isolated"):
            entry.caller_guard(transport=object(), caller=None)
    monkeypatch.setattr(entry, "PROJECT", entry.REPORT.parent)
    monkeypatch.setattr(entry, "SHARED_LOCK", ROOT / "escaped.lock")
    with pytest.raises(RuntimeError, match="isolated"):
        entry.caller_guard(transport=object(), caller=None)


@pytest.mark.parametrize("owned", ["REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "RESULTS", "TRACKER"])
def test_every_mock_owned_path_must_be_inside_temp_project(entry, monkeypatch, owned):
    monkeypatch.setattr(entry, owned, ROOT / "escape")
    with pytest.raises(RuntimeError, match="isolated"):
        entry.caller_guard(transport=object(), caller=None)


@pytest.mark.parametrize("phase", ["phase-1", "phase-7", "../phase-8", "phase-0"])
def test_phase_cannot_reopen_old_or_escape(phase):
    with pytest.raises(ValueError):
        load_entry().select_phase(phase)


def test_provider_error_counts_once_and_cannot_reopen(entry):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        raise httpx.ConnectError("offline failure")
    result = entry.run(transport=SimpleNamespace(post=post))
    assert calls == [1] and result["posts"] == 1 and result["stopped_on_error"]
    assert entry.verify_results()["posts"] == 1
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=post))


def test_fourth_stage_rejected_before_reservation(entry, monkeypatch):
    ready(entry)
    original = entry.test_service.summarize_text
    def extra(*a, **kw):
        result = original(*a, **kw)
        kw["client"].post(entry.test_service._endpoint(), headers={}, json={})
        return result
    monkeypatch.setattr(entry.test_service, "summarize_text", extra)
    calls = []
    result = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: calls.append(1) or response(len(calls))))
    assert len(calls) == result["posts"] == 3 and result["stopped_on_error"]


def test_cli_plan_help_do_not_load_runtime(entry, monkeypatch, capsys):
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Offline CLI read env"))
    entry.main(["--phase", "phase-8", "--plan"])
    assert json.loads(capsys.readouterr().out)["phase_post_cap"] == 3
    with pytest.raises(SystemExit) as caught:
        entry.main(["--help"])
    assert caught.value.code == 0
