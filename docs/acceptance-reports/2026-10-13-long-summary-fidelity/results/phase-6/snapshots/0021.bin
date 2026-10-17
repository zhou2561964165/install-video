"""New uncapped acceptance: hermetic real pipeline, synthetic transport only.

Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only through ytdlp_service; scene remains read-only. No provider or dotenv.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Uncapped fidelity entry is missing"
    spec = importlib.util.spec_from_file_location("long_fidelity_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entry_exists_and_phase_id_does_not_escape_owned_paths():
    module = load_entry()
    with pytest.raises(ValueError):
        module.select_phase("../old")


@pytest.fixture
def entry(tmp_path, monkeypatch):
    module = load_entry()
    for name, path in {"PROJECT": tmp_path, "REPORT": tmp_path / "report",
            "CORPUS": tmp_path / "corpus", "GROUP": tmp_path / "planning/call-group.json",
            "SHARED_LOCK": tmp_path / "http.lock"}.items():
        monkeypatch.setattr(module, name, path)
    module.select_phase("phase-1")
    module.CORPUS.mkdir()
    text = "Repeated premise.\nRepeated premise.\n" + "\n".join(
        f"{i:04d} Source-specific condition and exact outcome " + "x" * 50 for i in range(340))
    text += "\nRepeated premise.\nEnding condition and consequence."
    path = module.CORPUS / "en-long.txt"
    path.write_text(text, encoding="utf-8")
    raw = module.CORPUS / "en-long.vtt"
    raw.write_text("WEBVTT\n" + text, encoding="utf-8")
    module.io.exclusive(module.CORPUS / "manifest.json", {"samples": [{
        "id": "en-long", "file": path.name, "raw_path": raw.name,
        "title": "Exact source", "sha256": module.io.digest(path.read_bytes()),
        "raw_sha256": module.io.digest(raw.read_bytes()), "license": "CC BY-NC-SA 4.0",
        "attribution": "MIT OCW"}]})
    services = tmp_path / "backend/app/services"
    services.mkdir(parents=True)
    files = []
    for name in ("summary_output.py", "summary_json.py", "llm_service.py"):
        target = services / name
        target.write_bytes((ROOT / "backend/app/services" / name).read_bytes())
        files.append(target)
    asset = tmp_path / "source.py"
    asset.write_text("frozen = True\n", encoding="utf-8")
    parent = tmp_path / "old-group.json"
    module.io.exclusive(parent, {"status": "closed", "reserved_posts": 16, "phases": []})
    monkeypatch.setattr(module, "history_paths", lambda: [parent])
    monkeypatch.setattr(module, "asset_paths", lambda: [asset, parent, *files, *module.CORPUS.iterdir()])
    from app.services import llm_service as service
    from app.config import Settings
    settings = Settings()
    for key, value in module.CONFIG.items():
        setattr(settings, key, value)
    settings.llm_provider, settings.llm_model = "offline", "offline-model"
    settings.llm_api_key, settings.llm_base_url = "", "https://offline.invalid"
    settings.llm_timeout_seconds = 1
    monkeypatch.setattr(service, "settings", settings)
    monkeypatch.setattr(module, "runtime", lambda: (settings, service, service._endpoint()))
    module.test_asset, module.test_parent = asset, parent
    module.test_service, module.test_settings = service, settings
    return module


def response(n=1):
    return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json={
        "model": "offline-model", "private": "DO-NOT-SAVE",
        "usage": {"total_tokens": 3, "secret": "DO-NOT-SAVE"},
        "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"summary": f" Overview {n} ", "key_points": [f" Condition {n}. "]}),
            "reasoning_content": "DO-NOT-SAVE"}}]})


def ready(entry):
    entry.freeze()
    entry.check()


def execute(entry):
    calls = []
    result = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: calls.append(kw["json"]) or response(len(calls))))
    return result, calls


def test_plan_is_offline_and_retains_nonadjacent_source_repetition(entry, monkeypatch):
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Plan read dotenv"))
    plan = entry.plan()
    assert plan["budget_mode"] == "uncapped" and plan["hard_ceiling"] is None
    assert plan["planned_posts"] == 3 and len(plan["samples"][0]["chunks"]) == 2
    assert entry.cleaned("A\nA\nB\nA") == "A\nB\nA"
    assert not entry.GROUP.exists()


def test_each_attempt_preallocated_full_source_merge_and_closed_frozen_verify(entry, monkeypatch):
    old = entry.test_parent.read_bytes()
    ready(entry)
    seen = []
    def post(*a, **kw):
        seen.append(kw["json"])
        assert entry.read(entry.GROUP)["reserved_posts"] == len(seen)
        ledger = entry.read(entry.RESULTS / "request-ledger.json")
        assert ledger["requests"][-1]["status"] == "reserved"
        assert entry.read(entry.TRACKER)["reserved_posts"] == len(seen)
        return response(len(seen))
    index = entry.run(transport=SimpleNamespace(post=post))
    assert index["posts"] == 3 and not index["stopped_on_error"]
    assert "Output language: source" in seen[0]["messages"][1]["content"]
    merge = seen[-1]["messages"][1]["content"]
    assert "Condition 1." in merge and "Condition 2." in merge
    assert "0100 Source-specific condition" in merge
    assert "Ending condition and consequence." in merge
    assert "DO-NOT-SAVE" not in "".join(p.read_text(encoding="utf-8") for p in entry.RESULTS.glob("*.json"))
    assert entry.test_parent.read_bytes() == old
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Verify read dotenv"))
    (entry.PROJECT / "backend/app/services/summary_json.py").write_text("raise RuntimeError('live changed')")
    assert entry.verify_results()["posts"] == 3
    assert entry.verify_results()["semantic_quality_verified"] is False
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=post))


def test_new_phase_retains_unbounded_actual_cumulative_calls(entry):
    ready(entry)
    execute(entry)
    entry.select_phase("phase-2")
    ready(entry)
    execute(entry)
    assert entry.read(entry.GROUP)["reserved_posts"] == 6
    assert [p["reserved_posts"] for p in entry.read(entry.GROUP)["phases"]] == [3, 3]
    assert entry.verify_results()["work_posts"] == 6


def test_total_accounting_can_cross_old_sixteen_without_a_hidden_ceiling(entry):
    for ordinal in range(1, 7):
        entry.select_phase(f"phase-{ordinal}")
        ready(entry)
        execute(entry)
    assert entry.read(entry.GROUP)["reserved_posts"] == 18
    assert entry.verify_results()["work_posts"] == 18


def test_freeze_refuses_runtime_profile_mismatch_without_allocating_phase(entry):
    entry.test_settings.llm_summary_notes_language = "output"
    with pytest.raises(RuntimeError, match="profile|configuration"):
        entry.freeze()
    assert not entry.RESULTS.exists() and not entry.TRACKER.exists()


def test_next_phase_refuses_forged_closed_prior_count(entry):
    ready(entry)
    execute(entry)
    group = entry.read(entry.GROUP)
    group["phases"][0]["reserved_posts"] = 0
    entry.io.durable(entry.GROUP, group)
    entry.select_phase("phase-2")
    with pytest.raises(RuntimeError, match="closed|receipt|accounting"):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_historical_parent_drift_after_first_post_stops_without_refund(entry):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        entry.test_parent.write_text("changed")
        return response()
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == [1] and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 1
    assert entry.verify_results()["stopped_on_error"]


def test_merge_boundary_fallback_is_bound_to_actual_notes_capacity(entry):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(kw["json"])
        if len(calls) < 3:
            value = response(len(calls)).json()
            value["choices"][0]["message"]["content"] = json.dumps({
                "summary": f"Part {len(calls)} " + "large note " * 1800,
                "key_points": [f"Exact point {len(calls)}"]})
            return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json=value)
        return response(3)
    index = entry.run(transport=SimpleNamespace(post=post))
    assert not index["stopped_on_error"] and len(calls) == 3
    merge = calls[-1]["messages"][1]["content"]
    assert "[... omitted middle ...]" in merge
    assert "0100 Source-specific condition" not in merge
    assert entry.verify_results()["posts"] == 3


def test_frozen_merge_source_cannot_be_rebound_to_invented_text(entry):
    entry.freeze()
    path = entry.RESULTS / "provenance.json"
    frozen = entry.read(path)
    frozen["stages"]["en-long"][-1]["source_parts"] = ["invented part one", "invented part two"]
    entry.io.durable(path, frozen)
    digest = entry.io.digest(path.read_bytes())
    tracker = entry.read(entry.TRACKER)
    tracker["provenance_sha256"] = digest
    entry.io.durable(entry.TRACKER, tracker)
    group = entry.read(entry.GROUP)
    group["phases"][-1]["provenance_sha256"] = digest
    entry.io.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="source|Source"):
        entry.check()


def test_closed_verify_uses_frozen_merge_helpers_after_live_change(entry, monkeypatch):
    ready(entry)
    execute(entry)
    (entry.PROJECT / "backend/app/services/llm_service.py").write_text("raise RuntimeError('live changed')")
    monkeypatch.setattr(entry.test_service, "_summary_merge_contexts", lambda *a: pytest.fail("Verify used live merge helper"))
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Verify read dotenv"))
    assert entry.verify_results()["posts"] == 3


def test_cli_plan_uses_explicit_phase_without_reading_runtime(entry, monkeypatch, capsys):
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Plan read dotenv"))
    entry.main(["--phase", "phase-2", "--plan"])
    value = json.loads(capsys.readouterr().out)
    assert value["phase"] == "phase-2" and value["dotenv_read"] is False
    assert value["budget_mode"] == "uncapped" and value["planned_posts"] == 3
    assert not entry.GROUP.exists() and not entry.RESULTS.exists()


@pytest.mark.parametrize("boundary", ["snapshot", "provenance", "tracker", "first_group", "existing_group"])
def test_failed_freeze_allocation_cannot_be_skipped_by_selecting_next_phase(entry, monkeypatch, boundary):
    if boundary == "existing_group":
        ready(entry)
        execute(entry)
        entry.select_phase("phase-2")
    broken_phase, broken_results, broken_tracker = entry.PHASE, entry.RESULTS, entry.TRACKER
    if boundary == "snapshot":
        original = Path.open
        def broken_open(path, mode="r", *args, **kwargs):
            if mode == "xb" and path.suffix == ".bin":
                raise OSError("synthetic snapshot failure")
            return original(path, mode, *args, **kwargs)
        monkeypatch.setattr(Path, "open", broken_open)
    elif boundary == "existing_group":
        original = entry.durable
        def broken_durable(path, value):
            if path == entry.GROUP and value["phases"][-1]["phase"] == broken_phase:
                raise OSError("synthetic group registration failure")
            return original(path, value)
        monkeypatch.setattr(entry, "durable", broken_durable)
    else:
        original = entry.io.exclusive
        def broken_exclusive(path, value):
            if (boundary == "provenance" and path.name == "provenance.json"
                    or boundary == "tracker" and path == broken_tracker
                    or boundary == "first_group" and path == entry.GROUP):
                raise OSError("synthetic allocation failure")
            return original(path, value)
        monkeypatch.setattr(entry.io, "exclusive", broken_exclusive)
    with pytest.raises(OSError):
        entry.freeze()
    assert broken_results.is_dir()
    if boundary in {"first_group", "existing_group"}:
        assert broken_tracker.exists()
    entry.select_phase("phase-3" if broken_phase == "phase-2" else "phase-2")
    with pytest.raises(RuntimeError, match="allocation|allocated|unclosed"):
        entry.freeze()
    assert broken_results.is_dir() and not entry.RESULTS.exists()


@pytest.mark.parametrize("writing", [False, True])
def test_unregistered_tracker_remnant_blocks_new_allocation(entry, writing):
    old_tracker = entry.TRACKER.with_name(entry.TRACKER.name + ".writing") if writing else entry.TRACKER
    entry.io.exclusive(old_tracker, {"phase": "phase-1", "status": "frozen"})
    entry.select_phase("phase-2")
    with pytest.raises(RuntimeError, match="allocation|allocated|unclosed"):
        entry.freeze()
    assert old_tracker.exists() and not entry.RESULTS.exists()


@pytest.mark.parametrize("drift", ["profile", "versions", "cleaned", "chunks"])
def test_closed_verify_does_not_use_current_profile_versions_or_preparation(entry, monkeypatch, drift):
    ready(entry)
    execute(entry)
    if drift == "profile":
        monkeypatch.setattr(entry, "CONFIG", entry.CONFIG | {"llm_summary_output_token_ceiling": 32768})
    elif drift == "versions":
        monkeypatch.setattr(entry, "versions", lambda: {"httpx": "future", "langchain-core": "future"})
    elif drift == "cleaned":
        monkeypatch.setattr(entry, "cleaned", lambda *args: pytest.fail("Closed verify used current cleaned"))
    else:
        monkeypatch.setattr(entry.base, "chunks", lambda *args: pytest.fail("Closed verify used current chunks"))
    assert entry.verify_results()["posts"] == 3


def test_live_check_still_rejects_profile_drift(entry, monkeypatch):
    entry.freeze()
    monkeypatch.setattr(entry, "CONFIG", entry.CONFIG | {"llm_summary_output_token_ceiling": 32768})
    with pytest.raises(RuntimeError, match="configuration"):
        entry.check()


@pytest.mark.parametrize("field,value", [
    ("llm_summary_source_context_mode", "boundary"),
    ("llm_summary_notes_language", "output"),
    ("llm_summary_format_retries", 1),
    ("llm_summary_semantic_retries", 1),
    ("llm_summary_max_extra_calls", 1),
])
def test_new_candidate_setting_drift_after_first_response_blocks_next_leaf_preallocation(entry, field, value):
    ready(entry)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    assert frozen["runtime_config"][field] == entry.CONFIG[field]
    assert "llm_api_key" not in frozen["runtime_config"] and "llm_base_url" not in frozen["runtime_config"]
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        setattr(entry.test_settings, field, value)
        return response()
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == [1] and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 1
    assert len(entry.read(entry.RESULTS / "request-ledger.json")["requests"]) == 1
    assert entry.verify_results()["stopped_on_error"]


def test_live_check_rejects_package_version_drift_before_run(entry, monkeypatch):
    entry.freeze()
    monkeypatch.setattr(entry, "versions", lambda: {"httpx": "future"})
    with pytest.raises(RuntimeError, match="configuration"):
        entry.check()


@pytest.mark.parametrize("kind", ["http", "reserve"])
def test_error_keeps_preallocation_and_stops(entry, monkeypatch, kind):
    ready(entry)
    calls = []
    if kind == "reserve":
        original, failed = entry.durable, []
        def broken(path, value):
            if path == entry.GROUP and value.get("reserved_posts") == 1 and not failed:
                failed.append(True)
                raise OSError("DO-NOT-SAVE")
            return original(path, value)
        monkeypatch.setattr(entry, "durable", broken)
    def post(*a, **kw):
        calls.append(1)
        raise httpx.ConnectError("DO-NOT-SAVE")
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == ([1] if kind == "http" else [])
    assert index["posts"] == 1 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 1
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.verify_results()["stopped_on_error"]


@pytest.mark.parametrize("kind", ["source", "code", "parent", "version"])
def test_live_drift_before_first_send_closes_without_transport(entry, monkeypatch, kind):
    ready(entry)
    if kind == "source":
        (entry.CORPUS / "en-long.txt").write_text("changed")
    elif kind == "code":
        entry.test_asset.write_text("changed")
    elif kind == "parent":
        entry.test_parent.write_text("changed")
    else:
        original = entry.versions
        monkeypatch.setattr(entry, "versions", lambda: original() | {"httpx": "changed"})
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Drift reached HTTP")))
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 0


def test_shared_lock_blocks_existing_caller_without_removing_lock(entry):
    entry.SHARED_LOCK.mkdir()
    with pytest.raises(FileExistsError):
        entry.freeze()
    assert entry.SHARED_LOCK.is_dir() and not entry.RESULTS.exists()


def test_extra_stage_is_refused_before_transport_and_not_a_total_budget(entry, monkeypatch):
    ready(entry)
    original = entry.test_service.summarize_text
    def twice(text, **kw):
        value = original(text, **kw)
        original(text, **kw)
        return value
    monkeypatch.setattr(entry.test_service, "summarize_text", twice)
    index, calls = execute(entry)
    assert len(calls) == 3 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["hard_ceiling"] is None


def rebind(entry):
    receipt_path = entry.RESULTS / "closed-receipt.json"
    receipt = entry.read(receipt_path)
    for field, name in (("ledger_sha256", "request-ledger.json"), ("index_sha256", "result-index.json")):
        receipt[field] = entry.io.digest((entry.RESULTS / name).read_bytes())
    entry.io.durable(receipt_path, receipt)
    digest = entry.io.digest(receipt_path.read_bytes())
    tracker = entry.read(entry.TRACKER)
    tracker["closed_receipt_sha256"] = digest
    entry.io.durable(entry.TRACKER, tracker)
    group = entry.read(entry.GROUP)
    group["phases"][-1]["closed_receipt_sha256"] = digest
    entry.io.durable(entry.GROUP, group)


@pytest.mark.parametrize("extra", [False, True])
def test_success_missing_or_extra_source_rejected_even_after_hash_rebind(entry, extra):
    ready(entry)
    execute(entry)
    path = entry.RESULTS / "result-index.json"
    index = entry.read(path)
    index["samples"] = index["samples"] * 2 if extra else []
    entry.io.durable(path, index)
    rebind(entry)
    with pytest.raises(RuntimeError):
        entry.verify_results()


def test_last_raw_result_mismatch_rejected_after_rebinding_hashes(entry):
    ready(entry)
    execute(entry)
    result_path = entry.RESULTS / "en-long.json"
    result = entry.read(result_path)
    result["result"]["summary"] = "Overview 1"
    entry.io.durable(result_path, result)
    digest = entry.io.digest(result_path.read_bytes())
    index_path = entry.RESULTS / "result-index.json"
    index = entry.read(index_path)
    index["samples"][0]["result_sha256"] = digest
    entry.io.durable(index_path, index)
    ledger_path = entry.RESULTS / "request-ledger.json"
    ledger = entry.read(ledger_path)
    for row in ledger["requests"]:
        row["result_sha256"] = digest
    entry.io.durable(ledger_path, ledger)
    rebind(entry)
    with pytest.raises(RuntimeError, match="last raw"):
        entry.verify_results()
