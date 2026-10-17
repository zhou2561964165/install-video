"""Phase-5 complete checks+revision, synthetic provider and owned temp evidence.

Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only through ytdlp_service; scene read-only. No real model, dotenv or old edits.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test_long_fidelity_evaluation import ROOT, response, rebind
from test_long_pro_review_evaluation import entry as pro_fixture, run as pro_run

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/checks_evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Bound complete-checks acceptance entry is missing"
    spec = importlib.util.spec_from_file_location("complete_checks_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_new_phase_five_is_allowed():
    module = load_entry()
    for phase in ("phase-4", "phase-6", "../phase-5"):
        with pytest.raises(ValueError):
            module.select_phase(phase)


@pytest.fixture
def entry(tmp_path, monkeypatch):
    prior = pro_fixture.__wrapped__(tmp_path, monkeypatch)
    pro_run(prior)
    module = load_entry()
    for key in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, key, getattr(prior, key))
    module.select_phase("phase-5")
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
    return {"checks": [
        {"target": 0, "draft_quote": "Overview 8", "source_quote": "Repeated premise.", "finding": "Synthetic finding on overview."},
        {"target": 1, "draft_quote": "Condition 8.", "source_quote": "Ending condition and consequence.", "finding": "Synthetic finding on point."},
    ]}


def provider_response(content, *, model="deepseek-v4-pro"):
    body = response(10).json()
    body["model"] = model
    body["choices"][0]["message"]["content"] = content
    return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json=body)


def execute(entry, post=None):
    entry.freeze()
    entry.check()
    calls = []
    def provider(*args, **kwargs):
        calls.append(kwargs["json"])
        assert entry.read(entry.GROUP)["reserved_posts"] == 8 + len(calls)
        assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][-1]["status"] == "reserved"
        return provider_response(json.dumps(valid_checks()) if len(calls) == 1 else
            json.dumps({"summary": "Overview 10", "key_points": ["Condition 10."]}))
    return entry.run(transport=SimpleNamespace(post=post or provider)), calls


def test_valid_complete_checks_feedback_over_capacity_stops_before_second_reservation(entry):
    calls = []
    value = valid_checks()
    value["checks"][1]["finding"] = "A necessary scope qualification. " * 3000
    def provider(*args, **kwargs):
        calls.append(kwargs["json"])
        return provider_response(json.dumps(value))
    index, _ = execute(entry, provider)
    assert index["posts"] == 1 and index["stopped_on_error"] and len(calls) == 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 9
    assert len(entry.read(entry.RESULTS / "request-ledger.json")["requests"]) == 1


def test_plan_binds_phase_four_source_and_pro_draft_without_env_or_allocation(entry, monkeypatch):
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Offline plan read env"))
    plan = entry.plan()
    assert plan["work_reserved_posts"] == 8 and plan["planned_posts"] == 2
    assert plan["hard_ceiling"] is None and plan["config"]["llm_summary_fidelity_mode"] == "checks"
    assert plan["config"]["llm_model"] == "deepseek-v4-pro"
    assert plan["samples"][0]["draft_evidence"]["phase"] == "phase-4"
    assert plan["samples"][0]["draft"]["summary"] == "Overview 8"
    assert not entry.RESULTS.exists()


def test_frozen_checks_target_count_and_actual_draft_prompt_are_verified(entry):
    entry.freeze()
    path = entry.RESULTS / "provenance.json"
    frozen = entry.read(path)
    first = frozen["stages"]["en-long"][0]
    assert first.get("target_count") == 2
    entry.frozen_sources(frozen)
    first["target_count"] = 3
    with pytest.raises(RuntimeError, match="target|prompt"):
        entry.frozen_sources(frozen)
    first["target_count"] = 2
    first["payload"]["messages"][0]["content"] = "A partial review request omitting a draft target."
    with pytest.raises(RuntimeError, match="target|prompt"):
        entry.frozen_sources(frozen)


def test_all_checks_dynamic_actual_feedback_two_posts_and_no_semantic_certificate(entry):
    old = {p: p.read_bytes() for p in entry.prior.RESULTS.rglob("*") if p.is_file()}
    index, calls = execute(entry)
    assert index["posts"] == 2 and not index["stopped_on_error"]
    evidence = [json.loads(payload["messages"][1]["content"].split("Evidence and draft:\n", 1)[1]) for payload in calls]
    assert evidence[0]["draft"] == evidence[1]["draft"] == {"key_points": ["Condition 8."], "summary": "Overview 8"}
    assert evidence[0]["original_transcript"] == evidence[1]["original_transcript"]
    assert "0100 Source-specific condition" in evidence[1]["original_transcript"]
    assert "Synthetic finding on overview." in evidence[1]["review_feedback"]
    assert "Synthetic finding on point." in evidence[1]["review_feedback"]
    assert "Freeze-only" not in evidence[1]["review_feedback"]
    verified = entry.verify_results()
    assert verified["work_posts"] == 10 and verified["semantic_quality_verified"] is False
    assert all(p.read_bytes() == value for p, value in old.items())
    assert "DO-NOT-SAVE" not in "".join(p.read_text(encoding="utf-8") for p in entry.RESULTS.glob("*.json"))
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Closed phase reopened")))


@pytest.mark.parametrize("kind", ["missing", "duplicate", "wrong_target", "boolean_target", "draft_quote", "source_quote", "duplicate_json"])
def test_invalid_checks_stop_after_exactly_one_reserved_post_without_fallback(entry, kind):
    checks = valid_checks()
    if kind == "missing":
        checks["checks"].pop()
    elif kind == "duplicate":
        checks["checks"][1]["target"] = 0
    elif kind == "wrong_target":
        checks["checks"][1]["target"] = 2
    elif kind == "boolean_target":
        checks["checks"][1]["target"] = True
    elif kind == "draft_quote":
        checks["checks"][1]["draft_quote"] = "Invented unrelated assertion"
    elif kind == "source_quote":
        checks["checks"][1]["source_quote"] = "This quote was never in the source"
    content = json.dumps(checks) if kind != "duplicate_json" else '{"checks":[],"checks":' + json.dumps(valid_checks()["checks"]) + '}'
    calls = []
    index, _ = execute(entry, post=lambda *a, **kw: calls.append(kw["json"]) or provider_response(content))
    assert len(calls) == 1 and index["posts"] == 1 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 9
    assert entry.verify_results()["stopped_on_error"]


@pytest.mark.parametrize("filename", ["response-01.json", "payload-01.json"])
def test_first_packet_byte_drift_stops_before_second_payment(entry, monkeypatch, filename):
    original, changed = entry.expected_payload, []
    def drifted(frozen, sample, sample_post, ledger, codec):
        if sample_post == 2 and not changed:
            changed.append(1)
            path = entry.RESULTS / filename
            path.write_bytes(path.read_bytes() + b" ")
        return original(frozen, sample, sample_post, ledger, codec)
    monkeypatch.setattr(entry, "expected_payload", drifted)
    index, calls = execute(entry)
    assert len(calls) == 1 and index["posts"] == 1 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 9


@pytest.mark.parametrize("field,value", [("llm_model", "wrong-model"), ("llm_provider", "wrong-provider"), ("llm_summary_fidelity_mode", "review")])
def test_model_provider_mode_drift_refused_without_new_reservation(entry, field, value):
    entry.freeze()
    entry.check()
    setattr(entry.test_settings, field, value)
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Drift sent POST")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 8
    assert entry.read(entry.TRACKER)["status"] == "closed"


@pytest.mark.parametrize("name", ["response-02.json", "en-long.json", "closed-receipt.json"])
def test_parent_source_draft_evidence_drift_refused_before_post(entry, name):
    entry.freeze()
    entry.check()
    path = entry.prior.RESULTS / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Parent drift sent POST")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 8
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.verify_results()["stopped_on_error"]


@pytest.mark.parametrize("kind", ["config", "parser", "source_helper"])
def test_closed_checks_verify_uses_frozen_parser_and_own_bound_draft(entry, monkeypatch, kind):
    execute(entry)
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Closed verify read env"))
    if kind == "config":
        monkeypatch.setattr(entry, "CONFIG", {})
    elif kind == "parser":
        (entry.PROJECT / "backend/app/services/summary_review.py").write_text("raise RuntimeError('future parser')\n", encoding="utf-8")
    else:
        (entry.PROJECT / "backend/app/services/llm_service.py").write_text("raise RuntimeError('future source')\n", encoding="utf-8")
        (entry.prior.RESULTS / "response-02.json").write_text("future parent raw", encoding="utf-8")
    assert entry.verify_results()["work_posts"] == 10


@pytest.mark.parametrize("kind", ["directory", "tracker", "writing", "lock"])
def test_orphan_and_shared_lock_preserved_without_auto_recovery(entry, kind):
    if kind == "directory":
        path = entry.REPORT / "results/phase-9"
        path.mkdir()
    elif kind == "lock":
        path = entry.SHARED_LOCK
        path.mkdir()
    else:
        path = entry.GROUP.with_name("phase-9.json" + (".writing" if kind == "writing" else ""))
        entry.io.exclusive(path, {"status": "frozen"})
    with pytest.raises((RuntimeError, FileExistsError)):
        entry.freeze()
    assert path.exists() and not entry.RESULTS.exists()


@pytest.mark.parametrize("fault", ["http", "reserve"])
def test_error_attempt_not_refunded_or_retried(entry, monkeypatch, fault):
    entry.freeze()
    entry.check()
    if fault == "reserve":
        original, failed = entry.engine.durable, []
        def broken(path, value):
            if path == entry.GROUP and value.get("reserved_posts") == 9 and not failed:
                failed.append(1)
                raise OSError("DO-NOT-SAVE")
            return original(path, value)
        monkeypatch.setattr(entry.engine, "durable", broken)
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        raise httpx.ConnectError("DO-NOT-SAVE")
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == ([1] if fault == "http" else [])
    assert index["posts"] == 1 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 9
    assert entry.verify_results()["stopped_on_error"]


def test_final_result_still_must_equal_last_raw_after_rebinding_hashes(entry):
    execute(entry)
    path = entry.RESULTS / "en-long.json"
    product = entry.read(path)
    product["result"]["summary"] = "Different final public text"
    entry.io.durable(path, product)
    digest = entry.io.digest(path.read_bytes())
    index_path, ledger_path = entry.RESULTS / "result-index.json", entry.RESULTS / "request-ledger.json"
    index, ledger = entry.read(index_path), entry.read(ledger_path)
    index["samples"][0]["result_sha256"] = digest
    for row in ledger["requests"]:
        row["result_sha256"] = digest
    entry.io.durable(index_path, index)
    entry.io.durable(ledger_path, ledger)
    rebind(entry)
    with pytest.raises(RuntimeError, match="last raw"):
        entry.verify_results()
