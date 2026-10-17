"""Hermetic mixed Responses/checks then frozen Chat revision acceptance.

Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only ytdlp_service; scene read-only. Synthetic transport and owned temp only.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test_long_fidelity_evaluation import ROOT, response
from test_long_pro_review_evaluation import entry as pro_fixture, run as pro_run

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/structured_checks_evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Mixed structured checks acceptance entry is missing"
    spec = importlib.util.spec_from_file_location("structured_checks_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_new_phase_six_is_allowed():
    entry = load_entry()
    for phase in ("phase-4", "phase-5", "../phase-6", "phase-7"):
        with pytest.raises(ValueError):
            entry.select_phase(phase)


def test_frozen_assets_include_scope_and_revision_regressions():
    entry = load_entry()
    assets = {Path(path).resolve() for path in entry.candidate_assets()}
    required = {
        ROOT / "backend/tests/test_summary_scope_guidance.py",
        ROOT / "backend/tests/test_summary_source_revision.py",
    }
    assert required <= assets


def test_phase_cap_is_explicit_in_plan_freeze_and_offline_receipt(entry):
    plan = entry.plan()
    assert plan["budget_mode"] == "uncapped" and plan["hard_ceiling"] is None
    assert type(plan["phase_post_cap"]) is int
    assert plan["phase_post_cap"] == plan["planned_posts"] == 2
    entry.freeze()
    frozen = entry.read(entry.RESULTS / "provenance.json")
    assert frozen["phase_post_cap"] == frozen["planned_posts"] == 2
    for invalid in (None, 3, True):
        changed = json.loads(json.dumps(frozen))
        if invalid is None:
            changed.pop("phase_post_cap")
        else:
            changed["phase_post_cap"] = invalid
        with pytest.raises(RuntimeError):
            entry.frozen_sources(changed)
    first_check = entry.check()
    second_check = entry.check()
    assert first_check == second_check
    receipt_path = entry.RESULTS / "offline-check.json"
    receipt = entry.read(receipt_path)
    assert type(receipt["phase_post_cap"]) is int and receipt["phase_post_cap"] == 2
    receipt["phase_post_cap"] = 2.0
    entry.engine.durable(receipt_path, receipt)
    with pytest.raises(RuntimeError):
        entry.check()
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Malformed receipt sent POST")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 8


@pytest.fixture
def entry(tmp_path, monkeypatch):
    prior = pro_fixture.__wrapped__(tmp_path, monkeypatch)
    pro_run(prior)
    module = load_entry()
    for key in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, key, getattr(prior, key))
    module.select_phase("phase-6")
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
        "target_0": {"assessment": "supported", "source_quote": "Repeated premise.", "finding": "Synthetic source scope."},
        "target_1": {"assessment": "needs_correction", "source_quote": "Ending condition and consequence.", "finding": "Synthetic local condition."},
    }


def provider_response(content, *, responses=False, model="deepseek-v4-pro", status="completed"):
    if responses:
        body = {"object": "response", "status": status, "model": model,
            "private": "DO-NOT-SAVE", "usage": {"input_tokens": 9, "output_tokens": 3, "total_tokens": 12,
                "output_tokens_details": {"reasoning_tokens": 1, "secret": "DO-NOT-SAVE"}},
            "output": [{"type": "reasoning", "content": "DO-NOT-SAVE"},
                {"type": "message", "role": "assistant", "status": status,
                    "content": [{"type": "output_text", "text": content}]}]}
    else:
        body = response(10).json()
        body["model"] = model
        body["choices"][0]["message"]["content"] = content
    return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json=body)


def execute(entry, post=None):
    entry.freeze()
    entry.check()
    calls = []
    def provider(url, **kwargs):
        calls.append((url, kwargs["json"]))
        assert entry.read(entry.GROUP)["reserved_posts"] == 8 + len(calls)
        assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][-1]["status"] == "reserved"
        return provider_response(json.dumps(valid_checks()) if len(calls) == 1 else
            json.dumps({"summary": "Overview 10", "key_points": ["Condition 10."]}), responses="text" in kwargs["json"])
    return entry.run(transport=SimpleNamespace(post=post or provider)), calls


def test_mixed_endpoints_exact_schema_actual_feedback_and_safe_tokens(entry):
    old = {path: path.read_bytes() for path in entry.prior.RESULTS.rglob("*") if path.is_file()}
    index, calls = execute(entry)
    assert index["posts"] == 2 and not index["stopped_on_error"]
    assert calls[0][0].endswith("/responses") and calls[1][0].endswith("/chat/completions")
    schema = calls[0][1]["text"]["format"]["schema"]
    assert set(schema["properties"]) == set(schema["required"]) == {"target_0", "target_1"}
    assert "strict" not in calls[0][1]["text"]["format"]
    assert calls[0][1]["max_output_tokens"] == 640 and "max_tokens" not in calls[0][1]
    evidence = json.loads(calls[1][1]["messages"][1]["content"].split("Evidence and draft:\n", 1)[1])
    assert "Synthetic local condition." in evidence["review_feedback"]
    assert "Freeze-only" not in evidence["review_feedback"]
    ledger = entry.read(entry.RESULTS / "request-ledger.json")
    assert [row["endpoint"] for row in ledger["requests"]] == [url for url, _ in calls]
    assert [row["max_output_tokens"] for row in ledger["requests"]] == [640, calls[1][1]["max_tokens"]]
    assert ledger["requests"][0]["usage"]["total_tokens"] == 12
    assert entry.verify_results()["semantic_quality_verified"] is False
    assert all(path.read_bytes() == value for path, value in old.items())
    assert "DO-NOT-SAVE" not in "".join(path.read_text(encoding="utf-8") for path in entry.RESULTS.glob("*.json"))


@pytest.mark.parametrize("filename", ["payload-01.json", "response-01.json"])
def test_prior_packet_byte_drift_stops_before_second_reservation(entry, monkeypatch, filename):
    original, changed = entry.expected_payload, []
    def expected(frozen, sample, sample_post, ledger, codec):
        if sample_post == 2 and not changed:
            changed.append(1)
            path = entry.RESULTS / filename
            path.write_bytes(path.read_bytes() + b" ")
        return original(frozen, sample, sample_post, ledger, codec)
    monkeypatch.setattr(entry, "expected_payload", expected)
    index, calls = execute(entry)
    assert len(calls) == 1 and index["posts"] == 1 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 9


def test_prepared_check_validates_schema_endpoint_budget_and_target_count(entry):
    entry.freeze()
    frozen = entry.read(entry.RESULTS / "provenance.json")
    for field in ("target_count", "endpoint", "max_output_tokens"):
        changed = json.loads(json.dumps(frozen))
        changed["stages"]["en-long"][0][field] = "unexpected"
        with pytest.raises(RuntimeError):
            entry.frozen_sources(changed)
    changed = json.loads(json.dumps(frozen))
    changed["stages"]["en-long"][0]["payload"]["text"]["format"]["strict"] = True
    with pytest.raises(RuntimeError):
        entry.frozen_sources(changed)
    changed = json.loads(json.dumps(frozen))
    changed["stages"]["en-long"][0]["payload"]["text"]["format"]["schema"]["properties"].pop("target_1")
    with pytest.raises(RuntimeError):
        entry.frozen_sources(changed)
    assert entry.check()["network"] is False
    assert entry.read(entry.GROUP)["reserved_posts"] == 8


@pytest.mark.parametrize("fault", ["missing", "foreign_quote", "invalid_assessment", "duplicate_json", "incomplete"])
def test_bad_first_response_is_one_paid_attempt_no_revision_or_fallback(entry, fault):
    checks = valid_checks()
    if fault == "missing":
        checks.pop("target_1")
    elif fault == "foreign_quote":
        checks["target_1"]["source_quote"] = "An excerpt not present in this source."
    elif fault == "invalid_assessment":
        checks["target_1"]["assessment"] = "guaranteed"
    content = json.dumps(checks)
    if fault == "duplicate_json":
        content = '{"target_0": {},' + content[1:]
    calls = []
    def provider(url, **kwargs):
        calls.append(kwargs["json"])
        return provider_response(content, responses=True, status="incomplete" if fault == "incomplete" else "completed")
    index, _ = execute(entry, provider)
    assert index["posts"] == 1 and index["stopped_on_error"] and len(calls) == 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 9
    assert entry.verify_results()["stopped_on_error"]


def test_wrong_actual_endpoint_is_refused_before_first_payment(entry, monkeypatch):
    entry.freeze()
    entry.check()
    original = entry.test_service._endpoint
    def endpoint(**kwargs):
        if kwargs.get("responses"):
            return original(**kwargs) + "/unplanned"
        return original(**kwargs)
    monkeypatch.setattr(entry.test_service, "_endpoint", endpoint)
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Wrong endpoint sent POST")))
    assert index["posts"] == 0 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 8


def test_parent_raw_drift_stops_without_payment_and_closed_verify_uses_snapshot(entry):
    entry.freeze()
    entry.check()
    parent = entry.prior.RESULTS / "response-02.json"
    parent.write_bytes(parent.read_bytes() + b" ")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Parent drift sent POST")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 8
    assert entry.verify_results()["posts"] == 0


def test_complete_actual_feedback_capacity_checked_before_second_reservation(entry, monkeypatch):
    calls = []
    original = entry.feedback_from_raw
    def feedback(frozen, ordinal):
        return original(frozen, ordinal) + "Necessary source qualification. " * 4000
    monkeypatch.setattr(entry, "feedback_from_raw", feedback)
    index, calls = execute(entry)
    assert len(calls) == 1 and index["posts"] == 1 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 9


def test_closed_verify_uses_frozen_parser_prompt_and_config(entry, monkeypatch):
    execute(entry)
    path = entry.PROJECT / "backend/app/services/summary_review.py"
    path.write_text("raise RuntimeError('future parser must not be imported')", encoding="utf-8")
    entry.test_settings.llm_model = "future-model"
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Closed verify read live env"))
    assert entry.verify_results()["posts"] == 2


def test_provider_error_has_no_retry_and_numeric_only_receipt(entry):
    calls = []
    def provider(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(503, request=httpx.Request("POST", url), json={
            "model": "deepseek-v4-pro", "error": {"message": "DO-NOT-SAVE"},
            "status": "failed", "usage": {"total_tokens": 4, "input_tokens": True, "secret": "DO-NOT-SAVE"}})
    index, _ = execute(entry, provider)
    assert len(calls) == 1 and index["stopped_on_error"]
    raw = entry.read(entry.RESULTS / "response-01.json")
    assert raw["usage"] == {"total_tokens": 4} and raw["response_status"] == "failed"
    assert "DO-NOT-SAVE" not in json.dumps(raw)
    assert entry.verify_results()["posts"] == 1


def test_second_stage_responses_is_used_when_explicitly_frozen(entry, monkeypatch):
    monkeypatch.setitem(entry.CONFIG, "llm_summary_response_format", "json_schema")
    entry.test_settings.llm_summary_response_format = "json_schema"
    index, calls = execute(entry)
    assert index["posts"] == 2 and not index["stopped_on_error"]
    assert all(url.endswith("/responses") for url, _ in calls)
    assert calls[1][1]["text"]["format"]["name"] == "video_summary"
    assert "max_output_tokens" in calls[1][1] and "max_tokens" not in calls[1][1]
    assert entry.verify_results()["posts"] == 2
