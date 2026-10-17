"""Hermetic direct diagnostic; skills/tokens and narrow interfaces apply.

Protect UI/env/accounts/models/history; yt-dlp stays in its service and scene
stays read-only. Synthetic transport only, no provider or dotenv access.
"""
import importlib.util
import json
from types import SimpleNamespace

import httpx
import pytest

from test_global_merge_evaluation import entry as global_fixture
from test_native_merge_evaluation import ROOT, native_response

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/direct_source_evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Direct source diagnostic missing"
    spec = importlib.util.spec_from_file_location("direct_source_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def entry(tmp_path, monkeypatch):
    prior = global_fixture.__wrapped__(tmp_path, monkeypatch)
    prior.freeze()
    prior.check()
    assert prior.run(transport=SimpleNamespace(post=lambda *a, **kw: native_response()))["posts"] == 1
    module = load_entry()
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, name, getattr(prior, name))
    module.select_phase("phase-11")
    monkeypatch.setattr(module.engine, "history_paths", prior.base.engine.history_paths)
    monkeypatch.setattr(module, "candidate_assets", prior.candidate_assets)
    monkeypatch.setattr(module, "_live_runtime", prior.base._live_runtime)
    module.prior = prior
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def test_offline_plan_has_only_direct_full_source_and_parent_metadata(entry, monkeypatch):
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Plan read env"))
    plan = entry.plan()
    assert plan["phase"] == "phase-11" and plan["work_reserved_posts"] == 16
    assert plan["planned_posts"] == plan["phase_post_cap"] == 1
    assert plan["format_posts"] == plan["semantic_posts"] == 0
    sample = plan["samples"][0]
    assert "notes" not in sample and "leaf_evidence" not in sample
    assert sample["parent_group_row"]["phase"] == "phase-10"
    assert sample["parent_group_row"]["reserved_posts"] == 1
    assert all("phase-8" not in p and "phase-9" not in p for p in sample["parent_evidence"]["paths"].values())
    assert plan["network"] is plan["dotenv_read"] is False
    assert not entry.RESULTS.exists()


def test_one_direct_payload_is_exact_full_normalized_source_and_replays(entry, monkeypatch):
    old = {p: p.read_bytes() for p in entry.prior.RESULTS.rglob("*") if p.is_file()}
    ready(entry)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    sample = frozen["sample_plan"][0]
    source = entry.engine.cleaned((entry.CORPUS / sample["file"]).read_text(encoding="utf-8"))
    assert entry.io.digest(source) == sample["cleaned_sha256"]
    assert len(source) == sample["cleaned_chars"]
    assert [s["stage"] for s in frozen["stages"]["en-long"]] == ["merge"]
    assert sample["request_path"] == "direct_source"
    calls = []

    def post(url, **kw):
        calls.append(kw["json"])
        assert url.endswith("/responses")
        assert entry.read(entry.GROUP)["reserved_posts"] == 17
        assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][-1]["status"] == "reserved"
        return native_response()

    result = entry.run(transport=SimpleNamespace(post=post))
    assert result["posts"] == len(calls) == 1 and not result["stopped_on_error"]
    payload = calls[0]
    assert payload["max_output_tokens"] == 8192 and payload["reasoning"] == {"effort": "none"}
    assert payload["text"]["format"]["schema"]["properties"]["key_points"]["maxItems"] == 14
    supplied = payload["input"][-1]["content"]
    assert supplied.endswith(source) and source.endswith("Ending condition and consequence.")
    assert "Leaf 1 condition" not in supplied and "Native condition" not in supplied
    assert "Organize themes across all section notes" not in supplied
    assert entry.read(entry.RESULTS / "en-long.json")["result"]["key_points"] == [f"Native condition {i}." for i in range(14)]
    assert all(p.read_bytes() == raw for p, raw in old.items())
    (entry.prior.RESULTS / "en-long.json").write_text("live parent drift", encoding="utf-8")
    (entry.PROJECT / "backend/app/services/llm_service.py").write_text("live candidate drift", encoding="utf-8")
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Replay read env"))
    verified = entry.verify_results()
    assert verified["posts"] == 1 and verified["semantic_quality_verified"] is False


@pytest.mark.parametrize("name", ["request-ledger.json", "closed-receipt.json", "result-index.json", "provenance.json", "en-long.json", "tracker"])
def test_parent_drift_blocks_before_reservation(entry, name):
    ready(entry)
    path = entry.prior.TRACKER if name == "tracker" else entry.prior.RESULTS / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Drift paid")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 16


@pytest.mark.parametrize("fault", ["count", "missing", "open"])
def test_phase10_closed_and_existing_count16_required(entry, fault):
    entry.bind()
    group = entry.read(entry.GROUP)
    if fault == "count":
        group["reserved_posts"] = 15
    elif fault == "missing":
        group["phases"] = [r for r in group["phases"] if r["phase"] != "phase-10"]
    else:
        next(r for r in group["phases"] if r["phase"] == "phase-10")["status"] = "running"
    entry.engine.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_over_input_limit_is_rejected_without_truncation_or_allocation(entry):
    manifest = entry.read(entry.CORPUS / "manifest.json")
    sample = manifest["samples"][0]
    path = entry.CORPUS / sample["file"]
    path.write_text("Full source " * 6000, encoding="utf-8")
    sample["sha256"] = entry.io.digest(path.read_bytes())
    (entry.CORPUS / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="input|60000"):
        entry.freeze()
    assert not entry.RESULTS.exists()


def drift_source_identity(entry, fault):
    path = entry.CORPUS / "manifest.json"
    manifest = entry.read(path)
    sample = manifest["samples"][0]
    if fault in {"source", "captions"}:
        field, checksum = ("file", "sha256") if fault == "source" else ("raw_path", "raw_sha256")
        source = entry.CORPUS / sample[field]
        source.write_bytes(source.read_bytes() + b"\nChanged authorized input identity.")
        sample[checksum] = entry.io.digest(source.read_bytes())
    else:
        sample[fault] += " changed"
    path.write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize("fault", ["source", "captions", "license", "title", "attribution"])
def test_synchronized_source_manifest_drift_rejected_before_allocation(entry, fault):
    drift_source_identity(entry, fault)
    with pytest.raises(RuntimeError, match="phase-10.*source identity"):
        entry.freeze()
    assert not entry.RESULTS.exists() and not entry.TRACKER.exists()
    assert entry.read(entry.GROUP)["reserved_posts"] == 16


def test_synchronized_drift_after_freeze_refused_before_post(entry):
    ready(entry)
    drift_source_identity(entry, "source")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Changed source paid")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 16
    assert entry.read(entry.RESULTS / "request-ledger.json")["requests"] == []


def test_snapshot_replay_rejects_synchronized_manifest_identity_drift(entry):
    ready(entry)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    sample = frozen["sample_plan"][0]
    name = (entry.CORPUS / "manifest.json").relative_to(entry.PROJECT).as_posix()
    path = entry.engine.snapshot_path(frozen, name)
    manifest = entry.read(path)
    sample["license"] = manifest["samples"][0]["license"] = "Changed license"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    sample["manifest_sha256"] = frozen["snapshots"][name]["sha256"] = entry.io.digest(path.read_bytes())
    with pytest.raises(RuntimeError, match="phase-10.*source identity"):
        entry.frozen_sources(frozen)


def test_second_call_refused_without_second_reservation(entry, monkeypatch):
    ready(entry)
    original = entry.ServiceAdapter.summarize_text
    def twice(self, *a, **kw):
        result = original(self, *a, **kw)
        kw["client"].post(self._endpoint(), headers={}, json={})
        return result
    monkeypatch.setattr(entry.ServiceAdapter, "summarize_text", twice)
    calls = []
    result = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: calls.append(1) or native_response()))
    assert result["posts"] == len(calls) == 1 and result["stopped_on_error"]
    assert entry.verify_results()["stopped_on_error"]


@pytest.mark.parametrize("fault", ["incomplete", "overpoints", "network"])
def test_errors_count_once_and_never_retry_or_reopen(entry, fault):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        if fault == "network":
            raise httpx.ConnectError("offline")
        return native_response(status="incomplete" if fault == "incomplete" else "completed", count=15 if fault == "overpoints" else 14)
    result = entry.run(transport=SimpleNamespace(post=post))
    assert result["posts"] == len(calls) == 1 and result["stopped_on_error"]
    assert entry.verify_results()["stopped_on_error"]
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=post))


def test_root_mock_guard_precedes_any_writes(entry, monkeypatch):
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
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Offline read env"))
    assert entry.check()["dotenv_read"] is False
    entry.main(["--phase", "phase-11", "--plan"])
    assert json.loads(capsys.readouterr().out)["phase_post_cap"] == 1


def test_candidate_inventory_and_only_fresh_phase11():
    module = load_entry()
    for phase in ("phase-10", "phase-12", "../phase-11"):
        with pytest.raises(ValueError):
            module.select_phase(phase)
    names = {p.relative_to(ROOT).as_posix() for p in module.candidate_assets()}
    assert {SCRIPT.relative_to(ROOT).as_posix(), "backend/tests/test_direct_source_evaluation.py",
        "docs/superpowers/plans/2026-10-15-full-source-direct-diagnostic.md",
        "docs/acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-11-direct-source-tool.md"} <= names


def test_authorized_mit_normalized_source_is_complete_34894_chars(monkeypatch):
    module = load_entry()
    manifest = module.read(module.CORPUS / "manifest.json")
    sample = next(row for row in manifest["samples"] if row["id"] == "en-long")
    path = module.CORPUS / sample["file"]
    raw = path.read_bytes()
    source = module.engine.cleaned(raw.decode("utf-8"))
    assert module.io.digest(raw) == sample["sha256"]
    assert len(source) == 34894
    assert source.endswith("how do you tell the computer\nto do one thing or another?\nAll right.")
    monkeypatch.syspath_prepend(str(ROOT / "backend"))
    from app.config import Settings
    from app.services import llm_service as service
    settings = Settings()
    for key, value in module.CONFIG.items():
        setattr(settings, key, value)
    settings.llm_provider, settings.llm_base_url = "offline", "https://offline.invalid"
    monkeypatch.setattr(service, "settings", settings)
    normalized = service._summary_input(raw.decode("utf-8"))
    assert normalized == source
    adapter = module.ServiceAdapter(service, {"cleaned_chars": len(source), "cleaned_sha256": module.io.digest(source)})
    payload = module.engine.capture_request(adapter, source, sample, merge=True, source_chars=len(source))
    assert payload["input"][-1]["content"].endswith("Transcript:\n" + source)
    assert payload["max_output_tokens"] == 8192
    assert payload["text"]["format"]["schema"]["properties"]["key_points"]["maxItems"] == 14


def test_adapter_capture_and_run_use_merge_false_and_exact_source_chars():
    module = load_entry()
    text = "Start\nFull final condition."
    calls = []
    service = SimpleNamespace(_summary_input=lambda raw: text,
        _summary_request=lambda content, **options: calls.append((content, options)) or "unchanged result")
    adapter = module.ServiceAdapter(service, {"cleaned_chars": len(text), "cleaned_sha256": module.io.digest(text)})
    assert adapter.merge_content("raw") == (text, len(text))
    assert adapter._summary_request(text, merge=True, source_chars=len(text)) == "unchanged result"
    assert adapter.summarize_text("raw", title="Source", output_language="zh-CN") == "unchanged result"
    assert [content for content, options in calls] == [text, text]
    assert all(options["merge"] is False and options["source_chars"] == len(text) for content, options in calls)
