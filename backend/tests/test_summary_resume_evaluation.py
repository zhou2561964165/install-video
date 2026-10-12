"""Resume guards reuse the mature isolated fixture; no provider or dotenv calls.

Engineering: skills first, UI three-layer tokens, narrow interfaces, yt-dlp
only through ytdlp_service, and scene remains read-only.
"""
import importlib.util
import importlib.metadata
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-11-summary-content-resume/scripts/evaluate.py"
PRIOR = ROOT / "backend/tests/test_source_first_evaluation.py"
spec = importlib.util.spec_from_file_location("resume_fixture_source", PRIOR)
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


@pytest.fixture
def entry(tmp_path, monkeypatch):
    # Keep corpus preparation, product runtime injection, and synthetic HTTP
    # exactly in the existing fixture rather than creating another engine.
    monkeypatch.syspath_prepend(str(ROOT / "backend"))
    monkeypatch.setattr(source, "SCRIPT", SCRIPT)
    module = source.entry.__wrapped__(tmp_path, monkeypatch)
    parent = tmp_path / "closed-parent.json"
    module.io.exclusive(parent, {"status": "closed", "reserved_posts": 17})
    archive = tmp_path / "closed-framework.zip"
    receipts, ledgers = [], []
    with zipfile.ZipFile(archive, "w") as out:
        for name, posts, parent_posts in (("probe", 1, 17), ("refine", 7, 18)):
            receipt, ledger = name + "/closed-receipt.json", name + "/request-ledger.json"
            receipts.append(receipt)
            ledgers.append(ledger)
            out.writestr(receipt, json.dumps({"status": "closed", "posts": posts,
                "parent_posts": parent_posts}))
            out.writestr(ledger, json.dumps({"status": "closed", "requests": [{}] * posts}))
    group = module.read(module.GROUP)
    group["historical_parents"] = [
        {"path": str(parent), "sha256": module.io.digest(parent.read_bytes()), "posts": 17, "status": "closed"},
        {"path": str(archive), "sha256": module.io.digest(archive.read_bytes()), "posts": 8,
            "status": "closed", "receipt_members": receipts, "ledger_members": ledgers}]
    module.io.durable(module.GROUP, group)
    module.test_parent, module.test_archive = parent, archive
    return module


# Run existing budget, crash recovery, drift, raw sanitization and source guards
# against the adapter, not against a duplicated synthetic implementation.
for name in dir(source):
    if name.startswith("test_"):
        function = getattr(source, name)
        function.__module__ = __name__
        globals()[name] = function


def test_new_entry_redirects_paths_and_preserves_old_phase():
    assert SCRIPT.exists(), "Resume acceptance entry is missing"
    before = (ROOT / "docs/acceptance-reports/2026-10-10-source-first-summary-live/scripts/evaluate.py").read_bytes()
    spec = importlib.util.spec_from_file_location("resume_path_guard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.GROUP == ROOT / ".planning/2026-10-11-summary-content-resume/budget-group.json"
    assert module.TRACKER == module.GROUP.with_name("phase-1.json")
    assert module.SHARED_LOCK == ROOT / "docs/acceptance-reports/2026-10-05-grounded-summary/results/.http-session-lock"
    assert module.REPORT == SCRIPT.parents[1]
    assert module.base.GROUP != module.GROUP  # Import alone cannot repoint old phase.
    assert before == (ROOT / "docs/acceptance-reports/2026-10-10-source-first-summary-live/scripts/evaluate.py").read_bytes()


def test_candidate_freezes_thinking_single_without_extra_calls(entry):
    source.ready(entry)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    assert frozen["config"]["llm_summary_generation_mode"] == "single"
    assert frozen["config"]["llm_summary_format_retries"] == 0
    assert frozen["config"]["llm_summary_semantic_retries"] == 0
    assert frozen["config"]["llm_summary_max_extra_calls"] == 0
    for stages in frozen["stages"].values():
        for record in stages:
            assert record["payload"]["thinking"] == {"type": "enabled"}
            assert record["payload"]["response_format"] == {"type": "json_object"}
            assert record["payload"]["max_tokens"] <= 16384
    assert entry.plan()["historical_posts"] == 25
    assert entry.plan()["work_reserved_posts"] == 0


@pytest.mark.parametrize("dependency", ["langchain-core", "langsmith"])
def test_imported_runtime_dependency_drift_blocks_before_http(entry, monkeypatch, dependency):
    source.ready(entry)
    original = importlib.metadata.version
    monkeypatch.setattr(importlib.metadata, "version", lambda name:
        "changed-library" if name == dependency else original(name))
    calls = []
    with pytest.raises(RuntimeError, match="codec|configuration"):
        entry.run(transport=SimpleNamespace(post=lambda *a, **k: calls.append(1) or source.response()))
    assert calls == [] and entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 0


@pytest.mark.parametrize("action", ["plan", "freeze", "check", "run", "verify_results"])
def test_parent_hash_drift_blocks_every_boundary_without_http(entry, monkeypatch, action):
    if action in {"check", "run", "verify_results"}:
        source.ready(entry)
    if action == "verify_results":
        entry.run(transport=SimpleNamespace(post=lambda *a, **k: source.response()))
    entry.test_parent.write_text('{"status":"closed","reserved_posts":16}')
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Parent drift reached runtime"))
    with pytest.raises(RuntimeError, match="Historical"):
        getattr(entry, action)()
    if action == "run":
        assert entry.read(entry.TRACKER)["status"] == "closed"
        assert entry.read(entry.GROUP)["reserved_posts"] == 0


@pytest.mark.parametrize("mutation", ["hash_rebind", "record_drop"])
def test_frozen_parent_inventory_cannot_be_rebound(entry, mutation):
    source.ready(entry)
    group = entry.read(entry.GROUP)
    if mutation == "hash_rebind":
        entry.test_parent.write_text('{"status":"closed","reserved_posts":17,"changed":true}')
        group["historical_parents"][0]["sha256"] = entry.io.digest(entry.test_parent.read_bytes())
    else:
        group["historical_parents"].pop()
    entry.io.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="Historical"):
        entry.check()


def test_parent_drift_after_http_stops_and_seals_without_refund(entry):
    source.ready(entry)
    calls = []
    def post(*a, **k):
        calls.append(1)
        entry.test_parent.write_text("changed")
        return source.response()
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == [1] and index["posts"] == 1 and index["stopped_on_error"]
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 1


def test_zip_checks_use_the_same_bytes_as_the_verified_hash(entry, monkeypatch):
    original = Path.read_bytes
    changed = []
    def read_once(path):
        raw = original(path)
        if path == entry.test_archive and not changed:
            changed.append(True)
            path.write_bytes(b"changed after verified read")
        return raw
    monkeypatch.setattr(Path, "read_bytes", read_once)
    assert entry.historical_state(entry.read(entry.GROUP))["historical_posts"] == 25
    with pytest.raises(RuntimeError, match="Historical"):
        entry.plan()


@pytest.mark.parametrize("kind", ["status", "posts", "archive_chain", "archive_open"])
def test_parent_accounting_must_be_closed_and_exact(entry, kind):
    group = entry.read(entry.GROUP)
    row = group["historical_parents"][0]
    if kind in {"status", "posts"}:
        entry.io.durable(entry.test_parent, {"status": "active" if kind == "status" else "closed",
            "reserved_posts": 16 if kind == "posts" else 17})
        row["sha256"] = entry.io.digest(entry.test_parent.read_bytes())
    else:
        with zipfile.ZipFile(entry.test_archive, "r") as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        target = "refine/closed-receipt.json" if kind == "archive_chain" else "refine/request-ledger.json"
        value = json.loads(members[target])
        value["parent_posts" if kind == "archive_chain" else "status"] = 19 if kind == "archive_chain" else "running"
        members[target] = json.dumps(value)
        with zipfile.ZipFile(entry.test_archive, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        group["historical_parents"][1]["sha256"] = entry.io.digest(entry.test_archive.read_bytes())
    entry.io.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="Historical"):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_redirect_is_one_reserved_error_without_followup(entry):
    source.ready(entry)
    calls = []
    def post(*a, **k):
        calls.append(1)
        return httpx.Response(302, request=httpx.Request("POST", "https://offline.invalid"),
            headers={"Location": "https://other.invalid?token=DO-NOT-SAVE"},
            json={"model": "offline-model", "error": "DO-NOT-SAVE"})
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == [1] and index["stopped_on_error"] and index["posts"] == 1
    assert "DO-NOT-SAVE" not in (entry.RESULTS / "response-01.json").read_text()
    assert entry.verify_results()["posts"] == 1


def test_help_and_plan_do_not_read_runtime(entry, monkeypatch, capsys):
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Offline command read dotenv"))
    with pytest.raises(SystemExit) as exit:
        entry.main(["--help"])
    assert exit.value.code == 0
    capsys.readouterr()
    entry.main([])
    assert json.loads(capsys.readouterr().out)["dotenv_read"] is False


def test_asset_inventory_covers_adapter_tests_and_runtime_without_private_files(entry, monkeypatch):
    monkeypatch.setattr(entry, "PROJECT", ROOT)
    monkeypatch.setattr(entry, "REPORT", SCRIPT.parents[1])
    monkeypatch.setattr(entry, "CORPUS", ROOT / "docs/acceptance-reports/2026-10-04-natural-subtitle-quality/corpus")
    assets = entry.inventory_paths()
    assert SCRIPT in assets and ROOT / "backend/tests/test_summary_resume_evaluation.py" in assets
    assert entry.ADAPTER in assets and entry.HELPER in assets
    assert ROOT / "uv.lock" in assets and ROOT / "backend/app/config.py" in assets
    assert {ROOT / "docs/acceptance-reports" / name for name in (
        "2026-10-09-summary-quality-repaired/rubric.json",
        "2026-10-09-adaptive-short-medium/review-criteria.md",
        "2026-10-09-adaptive-summary-final/review-criteria.md",
        "2026-10-09-adaptive-summary/report.md",
    )} <= set(assets)
    assert set((ROOT / "backend/app/services").glob("summary_*.py")) <= set(assets)
    assert all(not path.name.startswith(".env") and path.suffix != ".db" for path in assets)
