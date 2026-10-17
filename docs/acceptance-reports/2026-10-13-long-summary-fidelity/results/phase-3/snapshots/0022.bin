"""One frozen source+closed draft refinement; synthetic transport, no dotenv.

Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only through ytdlp_service; scene remains read-only. Existing evidence is kept.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test_long_fidelity_evaluation import ROOT, execute, ready, response
from test_long_fidelity_evaluation import entry as source_fixture

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/refine_evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Frozen draft refinement entry is missing"
    spec = importlib.util.spec_from_file_location("refine_fidelity_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entry_accepts_only_its_new_phase():
    module = load_entry()
    for phase in ("phase-1", "phase-3", "../phase-2"):
        with pytest.raises(ValueError):
            module.select_phase(phase)


@pytest.fixture
def entry(tmp_path, monkeypatch):
    prior = source_fixture.__wrapped__(tmp_path, monkeypatch)
    ready(prior)
    execute(prior)
    module = load_entry()
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, name, getattr(prior, name))
    module.select_phase("phase-2")
    for key, value in module.CONFIG.items():
        setattr(prior.test_settings, key, value)
    monkeypatch.setattr(module, "_live_runtime", lambda: (
        prior.test_settings, prior.test_service, prior.test_service._endpoint()))
    # Assets stay owned by tmp_path, including hermetic copies of the two files.
    copies = []
    for original in (SCRIPT, Path(__file__)):
        target = tmp_path / original.name
        target.write_bytes(original.read_bytes())
        copies.append(target)
    monkeypatch.setattr(module, "candidate_assets", lambda: [*prior.asset_paths(), *copies])
    module.prior = prior
    module.test_settings = prior.test_settings
    module.test_service = prior.test_service
    return module


def run_one(entry, post=None):
    entry.freeze()
    entry.check()
    calls = []
    def default_post(*args, **kwargs):
        calls.append(kwargs["json"])
        assert entry.read(entry.GROUP)["reserved_posts"] == 4
        assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][-1]["status"] == "reserved"
        return response(4)
    index = entry.run(transport=SimpleNamespace(post=post or default_post))
    return index, calls


def test_offline_plan_binds_exact_closed_draft_without_runtime(entry, monkeypatch):
    old = (entry.prior.RESULTS / "en-long.json").read_bytes()
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Offline plan read dotenv"))
    plan = entry.plan()
    assert plan["planned_posts"] == 1 and plan["work_reserved_posts"] == 3
    assert plan["hard_ceiling"] is None and plan["samples"][0]["draft"]["summary"] == "Overview 3"
    assert not entry.RESULTS.exists()
    assert (entry.prior.RESULTS / "en-long.json").read_bytes() == old


def test_one_refinement_preallocates_cumulative_four_and_retains_full_source(entry):
    old_files = {p: p.read_bytes() for p in entry.prior.RESULTS.rglob("*") if p.is_file()}
    index, calls = run_one(entry)
    assert index["posts"] == 1 and not index["stopped_on_error"]
    prompt = json.dumps(calls[0], ensure_ascii=False)
    assert "0100 Source-specific condition" in prompt
    assert "Ending condition and consequence." in prompt and "Overview 3" in prompt and "Condition 3." in prompt
    assert entry.verify_results()["work_posts"] == 4
    assert entry.verify_results()["semantic_quality_verified"] is False
    assert all(path.read_bytes() == data for path, data in old_files.items())
    assert "DO-NOT-SAVE" not in "".join(p.read_text(encoding="utf-8") for p in entry.RESULTS.glob("*.json"))
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Reopened closed phase")))


@pytest.mark.parametrize("name", ["response-03.json", "en-long.json", "closed-receipt.json", "request-ledger.json"])
def test_closed_draft_drift_after_freeze_stops_before_first_reservation(entry, name):
    entry.freeze()
    entry.check()
    path = entry.prior.RESULTS / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Draft drift reached transport")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 3
    assert entry.read(entry.TRACKER)["status"] == "closed"


def test_failed_prior_sample_refused_without_new_allocation(entry):
    path = entry.prior.RESULTS / "en-long.json"
    value = entry.read(path)
    value["success"] = False
    entry.engine.io.durable(path, value)
    with pytest.raises(RuntimeError):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_incomplete_original_and_draft_capacity_refused_before_allocation(entry, monkeypatch):
    monkeypatch.setattr(entry, "CONFIG", entry.CONFIG | {"llm_max_input_chars": 100})
    entry.test_settings.llm_max_input_chars = 100
    with pytest.raises(entry.test_service.LLMServiceError) as error:
        entry.freeze()
    assert error.value.error_type == "llm_input_too_large"
    assert not entry.RESULTS.exists()


@pytest.mark.parametrize("fault", ["http", "reserve"])
def test_error_retains_attempt_without_retry_or_refund(entry, monkeypatch, fault):
    entry.freeze()
    entry.check()
    calls = []
    if fault == "reserve":
        original, failed = entry.engine.durable, []
        def broken(path, value):
            if path == entry.GROUP and value.get("reserved_posts") == 4 and not failed:
                failed.append(1)
                raise OSError("DO-NOT-SAVE")
            return original(path, value)
        monkeypatch.setattr(entry.engine, "durable", broken)
    def post(*args, **kwargs):
        calls.append(1)
        raise httpx.ConnectError("DO-NOT-SAVE")
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == ([1] if fault == "http" else [])
    assert index["posts"] == 1 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 4
    assert entry.verify_results()["stopped_on_error"]


def test_more_than_one_refinement_cannot_send_or_preallocate_again(entry, monkeypatch):
    original = entry.test_service.refine_summary
    def twice(*args, **kwargs):
        value = original(*args, **kwargs)
        original(*args, **kwargs)
        return value
    monkeypatch.setattr(entry.test_service, "refine_summary", twice)
    index, calls = run_one(entry)
    assert len(calls) == 1 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 4


@pytest.mark.parametrize("drift", ["profile", "versions", "preparation", "code"])
def test_closed_refinement_verify_uses_frozen_assets(entry, monkeypatch, drift):
    run_one(entry)
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Closed verify read dotenv"))
    if drift == "profile":
        monkeypatch.setattr(entry, "CONFIG", {})
    elif drift == "versions":
        monkeypatch.setattr(entry.engine, "versions", lambda: {"future": "9"})
    elif drift == "preparation":
        monkeypatch.setattr(entry.test_service, "_summary_input", lambda *a: pytest.fail("Closed used live preparation"))
    else:
        (entry.PROJECT / "backend/app/services/llm_service.py").write_text("raise RuntimeError('live changed')")
    assert entry.verify_results()["posts"] == 1


@pytest.mark.parametrize("kind", ["directory", "tracker", "writing"])
def test_orphan_phase_directory_and_tracker_writing_block_freeze(entry, kind):
    if kind == "directory":
        orphan = entry.REPORT / "results/phase-9"
        orphan.mkdir()
    else:
        orphan = entry.GROUP.with_name("phase-9.json" + (".writing" if kind == "writing" else ""))
        entry.io.exclusive(orphan, {"status": "frozen"})
    with pytest.raises(RuntimeError, match="allocation|unclosed"):
        entry.freeze()
    assert orphan.exists() and not entry.RESULTS.exists()


def test_shared_lock_blocks_without_removal(entry):
    entry.SHARED_LOCK.mkdir()
    with pytest.raises(FileExistsError):
        entry.freeze()
    assert entry.SHARED_LOCK.is_dir() and not entry.RESULTS.exists()


def test_static_frozen_payload_contains_exact_original_and_draft(entry):
    entry.freeze()
    frozen = entry.read(entry.RESULTS / "provenance.json")
    payload = frozen["stages"]["en-long"][0]["payload"]
    evidence = json.loads(payload["messages"][1]["content"].split("Evidence and draft:\n", 1)[1])
    raw_text = (entry.CORPUS / "en-long.txt").read_text(encoding="utf-8")
    expected_text = raw_text.replace("Repeated premise.\nRepeated premise.\n", "Repeated premise.\n", 1)
    assert evidence == {"original_transcript": expected_text,
        "draft": {"key_points": ["Condition 3."], "summary": "Overview 3"}}
    assert payload["max_tokens"] > 0


def test_closed_verify_retains_parent_snapshot_when_parent_live_raw_changes(entry):
    run_one(entry)
    path = entry.prior.RESULTS / "response-03.json"
    path.write_text("changed", encoding="utf-8")
    assert entry.verify_results()["posts"] == 1


def test_live_profile_drift_refuses_before_any_reservation(entry):
    entry.freeze()
    entry.check()
    entry.test_settings.llm_summary_fidelity_mode = "off"
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Profile drift sent POST")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 3
    assert entry.verify_results()["posts"] == 0


def test_last_public_result_cannot_be_rebound_to_a_different_raw(entry):
    from test_long_fidelity_evaluation import rebind
    run_one(entry)
    path = entry.RESULTS / "en-long.json"
    result = entry.read(path)
    result["result"]["summary"] = "Unrelated final result"
    entry.io.durable(path, result)
    digest = entry.io.digest(path.read_bytes())
    index_path, ledger_path = entry.RESULTS / "result-index.json", entry.RESULTS / "request-ledger.json"
    index, ledger = entry.read(index_path), entry.read(ledger_path)
    index["samples"][0]["result_sha256"] = digest
    ledger["requests"][0]["result_sha256"] = digest
    entry.io.durable(index_path, index)
    entry.io.durable(ledger_path, ledger)
    rebind(entry)
    with pytest.raises(RuntimeError, match="last raw"):
        entry.verify_results()
