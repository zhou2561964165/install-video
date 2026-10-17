"""Hermetic phase-12 capacity contrast; no dotenv/provider access.

Skills first, narrow interfaces, protect prior evidence/env/UI/models/accounts.
UI uses design skills/tokens; yt-dlp stays in its service, scene read-only.
"""
import importlib.util
import json
from types import SimpleNamespace

import httpx
import pytest

from test_direct_source_evaluation import entry as direct_fixture
from test_native_merge_evaluation import ROOT, native_response

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/direct_source_capacity_evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Capacity diagnostic missing"
    spec = importlib.util.spec_from_file_location("capacity_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def entry(tmp_path, monkeypatch):
    prior = direct_fixture.__wrapped__(tmp_path, monkeypatch)
    prior.freeze()
    prior.check()
    assert prior.run(transport=SimpleNamespace(post=lambda *a, **kw: native_response()))["posts"] == 1
    module = load_entry()
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, name, getattr(prior, name))
    module.select_phase("phase-12")
    monkeypatch.setattr(module.engine, "history_paths", prior.engine.history_paths)
    monkeypatch.setattr(module, "candidate_assets", prior.candidate_assets)
    settings, service, ignored = prior._live_runtime()
    for key, value in module.CONFIG.items():
        setattr(settings, key, value)
    monkeypatch.setattr(module, "_live_runtime", lambda: (settings, service, service._endpoint()))
    module.prior = prior
    module.bind()
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def test_plan_offline_cap1_and_only_ceiling_configuration_changes(entry, monkeypatch):
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Plan read dotenv"))
    plan = entry.plan()
    assert plan["phase"] == "phase-12" and plan["work_reserved_posts"] == 17
    assert plan["planned_posts"] == plan["phase_post_cap"] == 1
    assert plan["format_posts"] == plan["semantic_posts"] == 0
    assert plan["config"] == entry.prior.CONFIG | {"llm_summary_point_ceiling": 15}
    sample = plan["samples"][0]
    assert "notes" not in sample and "leaf_evidence" not in sample
    assert sample["parent_group_row"]["phase"] == "phase-10"
    assert sample["comparison_group_row"]["phase"] == "phase-11"
    assert plan["dotenv_read"] is plan["network"] is False
    assert not entry.RESULTS.exists()


def test_one_full_source_capacity_request_preallocated_and_replayed(entry, monkeypatch):
    old = {p: p.read_bytes() for phase in (entry.prior, entry.prior.prior)
        for p in phase.RESULTS.rglob("*") if p.is_file()}
    ready(entry)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    previous = entry.read(entry.prior.RESULTS / "provenance.json")
    assert frozen["parent_posts"] == 17
    stage = frozen["stages"]["en-long"][0]
    assert stage["max_points"] == 15
    payload = stage["payload"]
    assert payload["text"]["format"]["schema"]["properties"]["key_points"]["maxItems"] == 15
    assert payload["max_output_tokens"] == 8192 and payload["reasoning"] == {"effort": "none"}
    text = entry.engine.cleaned((entry.CORPUS / "en-long.txt").read_text(encoding="utf-8"))
    assert payload["input"][-1]["content"].endswith("Transcript:\n" + text)
    assert "Native condition" not in json.dumps(payload) and "Leaf 1 condition" not in json.dumps(payload)
    # Generated numerical budget wording and schema are the only wire changes.
    entry.assert_capacity_payload(payload, previous["stages"]["en-long"][0]["payload"])
    calls = []
    def post(url, **kw):
        calls.append(kw["json"])
        assert url.endswith("/responses")
        assert entry.read(entry.GROUP)["reserved_posts"] == 18
        assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][-1]["status"] == "reserved"
        return native_response(count=15)
    result = entry.run(transport=SimpleNamespace(post=post))
    assert result["posts"] == len(calls) == 1 and not result["stopped_on_error"]
    assert len(entry.read(entry.RESULTS / "en-long.json")["result"]["key_points"]) == 15
    assert all(p.read_bytes() == raw for p, raw in old.items())
    (entry.prior.RESULTS / "en-long.json").write_text("live comparison drift", encoding="utf-8")
    (entry.PROJECT / "backend/app/services/llm_service.py").write_text("live code drift", encoding="utf-8")
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Replay read env"))
    assert entry.verify_results()["semantic_quality_verified"] is False
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=post))


@pytest.mark.parametrize("phase", ["phase-10", "phase-11"])
@pytest.mark.parametrize("filename", ["provenance.json", "request-ledger.json", "closed-receipt.json", "result-index.json", "en-long.json", "payload-01.json", "response-01.json", "tracker"])
def test_prior_closed_evidence_drift_refused_before_send(entry, phase, filename):
    ready(entry)
    prior = entry.prior if phase == "phase-11" else entry.prior.prior
    path = prior.TRACKER if filename == "tracker" else prior.RESULTS / filename
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Drift paid")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 17


@pytest.mark.parametrize("fault", ["count", "phase10", "phase11", "open"])
def test_parent_count17_and_both_closed_phases_required_before_allocation(entry, fault):
    group = entry.read(entry.GROUP)
    if fault == "count":
        group["reserved_posts"] = 16
    elif fault == "open":
        next(r for r in group["phases"] if r["phase"] == "phase-11")["status"] = "running"
    else:
        group["phases"] = [r for r in group["phases"] if r["phase"] != fault.replace("phase", "phase-")]
    entry.engine.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError):
        entry.freeze()
    assert not entry.RESULTS.exists()


@pytest.mark.parametrize("fault", ["network", "incomplete", "overpoints"])
def test_one_failed_attempt_closes_without_retry(entry, fault):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        if fault == "network":
            raise httpx.ConnectError("offline")
        return native_response(status="incomplete" if fault == "incomplete" else "completed", count=16 if fault == "overpoints" else 15)
    result = entry.run(transport=SimpleNamespace(post=post))
    assert result["posts"] == len(calls) == 1 and result["stopped_on_error"]
    assert entry.verify_results()["stopped_on_error"]
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=post))


def test_second_post_refused_before_reservation(entry, monkeypatch):
    ready(entry)
    original = entry.ServiceAdapter.summarize_text
    def twice(self, *args, **kw):
        result = original(self, *args, **kw)
        kw["client"].post(self._endpoint(), headers={}, json={})
        return result
    monkeypatch.setattr(entry.ServiceAdapter, "summarize_text", twice)
    calls = []
    result = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: calls.append(1) or native_response(count=15)))
    assert result["posts"] == len(calls) == 1 and result["stopped_on_error"]
    assert entry.verify_results()["stopped_on_error"]


@pytest.mark.parametrize("filename", ["response-01.json", "payload-01.json", "en-long.json"])
def test_comparison_raw_payload_or_product_drift_before_freeze_cannot_allocate(entry, filename):
    path = entry.prior.RESULTS / filename
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RuntimeError, match="binding"):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_root_mock_guard_precedes_writes_and_owned_paths_cannot_escape(entry, monkeypatch):
    monkeypatch.delenv("CODEX_ACCEPTANCE_CALLER", raising=False)
    with pytest.raises(RuntimeError, match="root"):
        entry.run(caller="root")
    monkeypatch.setattr(entry, "PROJECT", ROOT.parent)
    with pytest.raises(RuntimeError, match="isolated"):
        entry.run(transport=object())
    assert not entry.RESULTS.exists()


@pytest.mark.parametrize("owned", ["REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "RESULTS", "TRACKER"])
def test_owned_mock_paths_must_remain_in_system_temp_project(entry, monkeypatch, owned):
    monkeypatch.setattr(entry, owned, ROOT / "escaped")
    with pytest.raises(RuntimeError, match="isolated"):
        entry.run(transport=object())


def test_synchronized_source_identity_drift_and_source_limit_reject_before_allocation(entry):
    path = entry.CORPUS / "manifest.json"
    manifest = entry.read(path)
    source = entry.CORPUS / manifest["samples"][0]["file"]
    source.write_text("Full source " * 6000, encoding="utf-8")
    manifest["samples"][0]["sha256"] = entry.io.digest(source.read_bytes())
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="input"):
        entry.freeze()
    assert not entry.RESULTS.exists()


@pytest.mark.parametrize("field", ["instructions", "source", "temperature"])
def test_single_variable_projection_refuses_nonbudget_wire_drift(entry, field):
    ready(entry)
    payload = entry.read(entry.RESULTS / "provenance.json")["stages"]["en-long"][0]["payload"]
    previous = entry.read(entry.prior.RESULTS / "payload-01.json")
    if field == "source":
        payload["input"][-1]["content"] += " unauthorized source"
    elif field == "instructions":
        payload["instructions"] += " unauthorized guidance"
    else:
        payload["temperature"] = 0.9
    with pytest.raises(RuntimeError, match="Only adaptive capacity"):
        entry.assert_capacity_payload(payload, previous)


def test_offline_check_cli_and_inventory(entry, monkeypatch, capsys):
    entry.freeze()
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Offline read env"))
    assert entry.check()["dotenv_read"] is False
    entry.main(["--phase", "phase-12", "--plan"])
    assert json.loads(capsys.readouterr().out)["phase_post_cap"] == 1
    module = load_entry()
    for phase in ("phase-11", "phase-13", "../phase-12"):
        with pytest.raises(ValueError):
            module.select_phase(phase)
    names = {p.relative_to(ROOT).as_posix() for p in module.candidate_assets()}
    assert {SCRIPT.relative_to(ROOT).as_posix(), "backend/tests/test_direct_source_capacity_evaluation.py",
        "docs/superpowers/plans/2026-10-15-direct-source-capacity-check.md",
        "docs/acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-12-capacity-tool.md"} <= names


def test_real_mit_source_budget_is15_with_only_candidate_ceiling_change(monkeypatch):
    module = load_entry()
    monkeypatch.syspath_prepend(str(ROOT / "backend"))
    from app.config import Settings
    from app.services import llm_service as service
    settings = Settings()
    for key, value in module.CONFIG.items():
        setattr(settings, key, value)
    settings.llm_provider, settings.llm_base_url = "offline", "https://offline.invalid"
    monkeypatch.setattr(service, "settings", settings)
    manifest = module.read(module.CORPUS / "manifest.json")
    sample = next(r for r in manifest["samples"] if r["id"] == "en-long")
    text = service._summary_input((module.CORPUS / sample["file"]).read_text(encoding="utf-8"))
    assert len(text) == 34894
    budget = service._summary_budget(len(text))
    assert budget.max_points == 15 and budget.max_tokens == 8192
    adapter = module.ServiceAdapter(service, {"cleaned_chars": len(text), "cleaned_sha256": module.io.digest(text)})
    payload = module.engine.capture_request(adapter, text, sample, merge=True, source_chars=len(text))
    assert payload["text"]["format"]["schema"]["properties"]["key_points"]["maxItems"] == 15
