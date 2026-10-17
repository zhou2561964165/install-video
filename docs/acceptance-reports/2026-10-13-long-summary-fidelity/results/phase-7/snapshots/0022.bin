"""Hermetic phase-7 subject/scope checks; no live provider or old evidence writes.

Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only ytdlp_service; scene read-only. All allocation is in owned pytest temp.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test_long_fidelity_evaluation import ROOT
from test_long_pro_review_evaluation import entry as pro_fixture, run as pro_run
from test_long_structured_checks_evaluation import provider_response

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/subject_scope_checks_evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Phase-7 subject scope checks runner is missing"
    spec = importlib.util.spec_from_file_location("subject_scope_checks_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase_seven_only_and_independent_configuration():
    module = load_entry()
    assert module.PHASE == "phase-7" and module.PHASE_POST_CAP == 2
    for phase in ("phase-1", "phase-4", "phase-5", "phase-6", "../phase-7", "phase-8"):
        with pytest.raises(ValueError):
            module.select_phase(phase)
    assert module.CONFIG["llm_summary_fidelity_mode"] == "subject_checks"
    assert module.CONFIG["llm_summary_subject_checks_max_output_tokens"] == 8192
    assert module.CONFIG["llm_summary_review_max_output_tokens"] == 4096


def test_asset_inventory_contains_new_schema_config_tests_and_reviews():
    assets = {Path(path).resolve() for path in load_entry().candidate_assets()}
    required = {
        SCRIPT, Path(__file__).resolve(),
        ROOT / "backend/app/config.py", ROOT / "backend/app/services/summary_review.py",
        ROOT / "backend/app/services/llm_service.py",
        ROOT / "backend/tests/test_summary_subject_checks.py",
        ROOT / "docs/superpowers/specs/2026-10-14-subject-scope-relation-checks.md",
        ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-7-subject-checks-production-final.md",
        ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-7-subject-checks-tool-final.md",
    }
    assert required <= assets


@pytest.fixture
def entry(tmp_path, monkeypatch):
    prior = pro_fixture.__wrapped__(tmp_path, monkeypatch)
    pro_run(prior)
    module = load_entry()
    for key in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, key, getattr(prior, key))
    module.select_phase("phase-7")
    for key, value in module.CONFIG.items():
        setattr(prior.test_settings, key, value)
    monkeypatch.setattr(module, "_live_runtime", lambda: (
        prior.test_settings, prior.test_service, prior.test_service._endpoint()))
    monkeypatch.setattr(module.parent_reader, "candidate_assets", prior.candidate_assets)
    monkeypatch.setattr(module.parent_reader.parent_reader, "candidate_assets", prior.parent_reader.candidate_assets)
    copies = []
    for original in (SCRIPT, Path(__file__)):
        target = tmp_path / original.name
        target.write_bytes(original.read_bytes())
        copies.append(target)
    monkeypatch.setattr(module, "candidate_assets", lambda: [*prior.candidate_assets(), *copies])
    module.prior, module.test_settings, module.test_service = prior, prior.test_settings, prior.test_service
    return module


def valid_checks():
    return {
        "target_0": {"assessment": "uncertain", "scope_relation": "uncertain", "source_subject": None,
            "draft_subject": None, "source_quote": "Repeated premise.", "finding": "Synthetic source scope."},
        "target_1": {"assessment": "needs_correction", "scope_relation": "draft_broader", "source_subject": "Ending condition",
            "draft_subject": "Condition", "source_quote": "Ending condition and consequence.", "finding": "Synthetic local condition."},
    }


def execute(entry, provider=None):
    entry.freeze()
    entry.check()
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        assert entry.read(entry.GROUP)["reserved_posts"] == 8 + len(calls)
        assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][-1]["status"] == "reserved"
        return provider_response(json.dumps(valid_checks()) if len(calls) == 1 else
            json.dumps({"summary": "Overview 10", "key_points": ["Condition 10."]}), responses="text" in kwargs["json"])
    return entry.run(transport=SimpleNamespace(post=provider or post)), calls


def test_plan_binds_closed_phase_four_without_env_or_allocation(entry, monkeypatch):
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Plan read runtime"))
    plan = entry.plan()
    assert plan["network"] is False and plan["dotenv_read"] is False
    assert plan["budget_mode"] == "uncapped" and plan["hard_ceiling"] is None
    assert plan["phase_post_cap"] == plan["planned_posts"] == 2
    assert plan["work_reserved_posts"] == 8
    sample = plan["samples"][0]
    assert sample["draft"] == entry.read(entry.prior.RESULTS / "en-long.json")["result"]
    binding = sample["draft_evidence"]
    assert binding["phase"] == "phase-4"
    for key in ("source", "raw", "product", "receipt"):
        assert entry.io.digest((entry.PROJECT / binding["paths"][key]).read_bytes()) == binding["sha256"][key]
    assert not entry.RESULTS.exists() and not entry.TRACKER.exists()
    assert not any("phase-6" in path for path in binding["paths"].values())


def test_freeze_full_schema_bounded_tokens_and_actual_feedback(entry):
    old = {path: path.read_bytes() for path in entry.prior.RESULTS.rglob("*") if path.is_file()}
    index, calls = execute(entry)
    assert index["posts"] == 2 and not index["stopped_on_error"]
    assert calls[0][0].endswith("/responses") and calls[1][0].endswith("/chat/completions")
    first = calls[0][1]
    schema = first["text"]["format"]["schema"]
    assert set(schema["required"]) == set(schema["properties"]) == {"target_0", "target_1"}
    fields = schema["$defs"]["SubjectCheck"]
    assert set(fields["required"]) == set(fields["properties"]) == {
        "assessment", "scope_relation", "source_subject", "draft_subject", "source_quote", "finding"}
    assert first["text"]["format"]["name"] == "video_summary_subject_checks"
    assert "strict" not in first["text"]["format"]
    assert first["max_output_tokens"] == 1152 and "max_tokens" not in first
    frozen = entry.read(entry.RESULTS / "provenance.json")
    assert entry.review_module(frozen).subject_checks_output_tokens(14) == 7808
    evidence = json.loads(calls[1][1]["messages"][1]["content"].split("Evidence and draft:\n", 1)[1])
    for value in ("Ending condition", "Condition", "draft_broader", "Synthetic local condition."):
        assert value in evidence["review_feedback"]
    assert "Freeze-only" not in evidence["review_feedback"]
    assert entry.verify_results()["semantic_quality_verified"] is False
    assert all(path.read_bytes() == raw for path, raw in old.items())
    assert "DO-NOT-SAVE" not in "".join(path.read_text(encoding="utf-8") for path in entry.RESULTS.glob("*.json"))


def test_offline_check_repeatable_and_cap_receipt_tamper_rejected(entry):
    entry.freeze()
    first = entry.check()
    assert first == entry.check() and first["phase_post_cap"] == 2
    receipt = entry.read(entry.RESULTS / "offline-check.json")
    receipt["phase_post_cap"] = 2.0
    entry.engine.durable(entry.RESULTS / "offline-check.json", receipt)
    with pytest.raises(RuntimeError):
        entry.check()
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail("Tamper sent POST")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 8


@pytest.mark.parametrize("fault", ["cap", "mode", "limit", "schema", "endpoint", "tokens", "target_count", "source", "phase"])
def test_frozen_profile_schema_parent_binding_tamper_refused(entry, fault):
    entry.freeze()
    frozen = entry.read(entry.RESULTS / "provenance.json")
    changed = json.loads(json.dumps(frozen))
    stage = changed["stages"]["en-long"][0]
    if fault == "cap": changed["phase_post_cap"] = True
    elif fault == "mode": changed["config"]["llm_summary_fidelity_mode"] = "checks"
    elif fault == "limit": changed["config"]["llm_summary_subject_checks_max_output_tokens"] = 1000
    elif fault == "schema": stage["payload"]["text"]["format"]["schema"]["properties"].pop("target_1")
    elif fault == "source": changed["sample_plan"][0]["draft_evidence"]["sha256"]["source"] = "0" * 64
    elif fault == "phase": changed["sample_plan"][0]["draft_evidence"]["phase"] = "phase-6"
    else: stage[{"tokens": "max_output_tokens"}.get(fault, fault)] = "wrong"
    with pytest.raises(RuntimeError):
        entry.frozen_sources(changed)
    assert entry.read(entry.GROUP)["reserved_posts"] == 8


def test_insufficient_subject_budget_stops_before_allocation(entry, monkeypatch):
    monkeypatch.setitem(entry.CONFIG, "llm_summary_subject_checks_max_output_tokens", 1000)
    entry.test_settings.llm_summary_subject_checks_max_output_tokens = 1000
    with pytest.raises(Exception):
        entry.freeze()
    assert not entry.RESULTS.exists() and entry.read(entry.GROUP)["reserved_posts"] == 8


def test_parent_raw_byte_drift_rejected_without_payment(entry):
    entry.freeze()
    entry.check()
    parent = entry.prior.RESULTS / "response-02.json"
    parent.write_bytes(parent.read_bytes() + b" ")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail("Parent drift sent POST")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 8
    assert entry.verify_results()["posts"] == 0


@pytest.mark.parametrize("fault", ["missing", "foreign_quote", "foreign_subject", "duplicate", "incomplete", "network"])
def test_invalid_first_response_stops_after_single_reservation(entry, fault):
    checks = valid_checks()
    if fault == "missing": checks["target_1"].pop("source_subject")
    elif fault == "foreign_quote": checks["target_1"]["source_quote"] = "Absent excerpt."
    elif fault == "foreign_subject": checks["target_1"]["draft_subject"] = "Foreign subject"
    content = json.dumps(checks)
    if fault == "duplicate": content = '{"target_0": {},' + content[1:]
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["json"])
        if fault == "network": raise httpx.ConnectError("Synthetic offline failure")
        return provider_response(content, responses=True, status="incomplete" if fault == "incomplete" else "completed")
    index, _ = execute(entry, post)
    assert index["posts"] == len(calls) == 1 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 9
    assert entry.verify_results()["stopped_on_error"]


def test_real_workspace_mock_run_and_missing_root_declaration_refused(monkeypatch):
    module = load_entry()
    monkeypatch.delenv("CODEX_ACCEPTANCE_CALLER", raising=False)
    with pytest.raises(RuntimeError, match="root"):
        module.run()
    with pytest.raises(RuntimeError, match="isolated"):
        module.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail("Live workspace mock run")))
    monkeypatch.setenv("CODEX_ACCEPTANCE_CALLER", "root")
    with pytest.raises(RuntimeError, match="root"):
        module.run(caller="worker")


def test_injected_transport_rejects_real_workspace_ancestor_without_state_access(monkeypatch):
    module = load_entry()
    monkeypatch.setattr(module, "PROJECT", ROOT.parent)
    # Exercise only the guard: a RED test must never reach a real shared lock.
    with pytest.raises(RuntimeError, match="isolated"):
        module.caller_guard(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail("Ancestor POST")), caller=None)


def test_root_gate_checked_before_any_offline_state_read(entry, monkeypatch):
    monkeypatch.setenv("CODEX_ACCEPTANCE_CALLER", "worker")
    monkeypatch.setattr(entry, "read", lambda *a: pytest.fail("Unauthorized real run touched state"))
    with pytest.raises(RuntimeError, match="root"):
        entry.run(caller="root")


def test_injected_transport_requires_every_owned_path_inside_isolated_project(entry, monkeypatch):
    monkeypatch.setattr(entry, "GROUP", ROOT / ".planning/forbidden-live-accounting.json")
    with pytest.raises(RuntimeError, match="isolated"):
        entry.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail("Escaping mock state")))
