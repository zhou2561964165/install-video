"""Normal product-profile full suites, hermetic transport and owned temp evidence.

Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp only
through ytdlp_service; scene read-only. No real provider, dotenv or old mutation.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test_long_fidelity_evaluation import ROOT, response
from test_long_refine_evaluation import entry as draft_fixture, run_one

SCRIPT = ROOT / "docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/full_evaluate.py"


def load_entry():
    assert SCRIPT.exists(), "Normal full-suite acceptance entry is missing"
    spec = importlib.util.spec_from_file_location("full_fidelity_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase_and_suite_cannot_reopen_prior_or_escape_paths():
    module = load_entry()
    for phase in ("phase-1", "phase-2", "../phase-3", "phase-0"):
        with pytest.raises(ValueError):
            module.select_phase(phase)
    with pytest.raises(ValueError):
        module.select_suite("all")


@pytest.fixture
def entry(tmp_path, monkeypatch):
    prior = draft_fixture.__wrapped__(tmp_path, monkeypatch)
    run_one(prior)
    module = load_entry()
    for name in ("PROJECT", "REPORT", "GROUP", "SHARED_LOCK"):
        monkeypatch.setattr(module, name, getattr(prior, name))
    monkeypatch.setattr(module, "CORPUS", tmp_path)
    monkeypatch.setattr(module, "OLD_CORPUS", prior.CORPUS)
    new_corpus = tmp_path / "new-corpus"
    new_corpus.mkdir()
    monkeypatch.setattr(module, "NEW_CORPUS", new_corpus)
    module.select_phase("phase-3")
    module.select_suite("long")
    old_manifest = prior.read(prior.CORPUS / "manifest.json")
    for sid in ("zh-short", "en-medium"):
        text, raw = prior.CORPUS / (sid + ".txt"), prior.CORPUS / (sid + ".vtt")
        text.write_text(sid + " exact mechanism and condition.\n", encoding="utf-8")
        raw.write_text("WEBVTT\n" + text.read_text(encoding="utf-8"), encoding="utf-8")
        old_manifest["samples"].append({"id": sid, "file": text.name, "raw_path": raw.name,
            "sha256": prior.io.digest(text.read_bytes()), "raw_sha256": prior.io.digest(raw.read_bytes()),
            "title": sid, "license": "CC BY-NC-SA 4.0", "attribution": "MIT OCW"})
    prior.io.durable(prior.CORPUS / "manifest.json", old_manifest)
    text, raw = new_corpus / "en-long-unseen.txt", new_corpus / "en-long-unseen.vtt"
    text.write_text((prior.CORPUS / "en-long.txt").read_text(encoding="utf-8").replace(
        "Source-specific condition", "Unseen-source condition"), encoding="utf-8")
    raw.write_text("WEBVTT\n" + text.read_text(encoding="utf-8"), encoding="utf-8")
    prior.io.exclusive(new_corpus / "manifest.json", {"samples": [{"id": "en-long-unseen",
        "file": text.name, "raw_path": raw.name, "sha256": prior.io.digest(text.read_bytes()),
        "raw_sha256": prior.io.digest(raw.read_bytes()), "title": "Unseen source",
        "license": "CC BY-NC-SA 4.0", "attribution": "MIT OCW"}]})
    criteria = prior.REPORT / "unseen-review-criteria.md"
    criteria.write_text("Frozen independent source rubric before generation.\n", encoding="utf-8")
    monkeypatch.setattr(module, "CRITERIA_SHA256", prior.io.digest(criteria.read_bytes()))
    for key, value in module.CONFIG.items():
        setattr(prior.test_settings, key, value)
    monkeypatch.setattr(module, "_live_runtime", lambda: (
        prior.test_settings, prior.test_service, prior.test_service._endpoint()))
    copies = []
    feedback_file = tmp_path / "backend/app/services/summary_review.py"
    feedback_file.write_bytes((ROOT / "backend/app/services/summary_review.py").read_bytes())
    copies.append(feedback_file)
    for original in (SCRIPT, Path(__file__)):
        target = tmp_path / original.name
        target.write_bytes(original.read_bytes())
        copies.append(target)
    monkeypatch.setattr(module, "candidate_assets", lambda: [*prior.prior.asset_paths(), criteria, *copies,
        *(p for p in new_corpus.iterdir() if p.is_file())])
    module.prior, module.test_service, module.test_settings = prior, prior.test_service, prior.test_settings
    return module


def execute(entry, post=None):
    entry.freeze()
    entry.check()
    calls = []
    def default_post(*args, **kwargs):
        calls.append(kwargs["json"])
        assert entry.read(entry.GROUP)["reserved_posts"] == 4 + len(calls)
        ledger = entry.read(entry.RESULTS / "request-ledger.json")
        assert ledger["requests"][-1]["status"] == "reserved"
        result = response(len(calls))
        if len(calls) in (4, 9) and entry.SUITE == "long":
            body = result.json()
            body["choices"][0]["message"]["content"] = json.dumps({"feedback": f"Source finding {len(calls)}."})
            return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json=body)
        return result
    return entry.run(transport=SimpleNamespace(post=post or default_post)), calls


def test_offline_plan_uses_two_long_corpora_and_preserves_normal_profile(entry, monkeypatch):
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Offline plan read env"))
    planned = entry.plan()
    assert planned["planned_posts"] == 10 and planned["work_reserved_posts"] == 4
    assert [s["id"] for s in planned["samples"]] == ["en-long", "en-long-unseen"]
    assert [s["expected_posts"] for s in planned["samples"]] == [5, 5]
    assert planned["config"]["llm_summary_max_output_tokens"] == 4096
    assert planned["config"]["llm_summary_output_token_ceiling"] == 8192
    assert planned["config"]["llm_summary_thinking_mode"] == "auto"
    assert planned["config"]["llm_summary_response_format"] == "auto"
    assert planned["hard_ceiling"] is None and not entry.RESULTS.exists()


def test_full_long_suite_has_fresh_leaves_merge_dynamic_raw_draft_and_refine(entry):
    old = {p: p.read_bytes() for p in entry.prior.RESULTS.rglob("*") if p.is_file()}
    index, calls = execute(entry)
    assert index["posts"] == 10 and not index["stopped_on_error"]
    for offset, source_fragment in ((0, "0100 Source-specific condition"), (5, "0100 Unseen-source condition")):
        merge = calls[offset + 2]["messages"][1]["content"]
        assert f"Condition {offset + 1}." in merge and f"Condition {offset + 2}." in merge
        assert source_fragment in merge
        review = json.loads(calls[offset + 3]["messages"][1]["content"].split("Evidence and draft:\n", 1)[1])
        final = json.loads(calls[offset + 4]["messages"][1]["content"].split("Evidence and draft:\n", 1)[1])
        assert source_fragment in final["original_transcript"]
        assert final["draft"] == {"key_points": [f"Condition {offset + 3}."], "summary": f"Overview {offset + 3}"}
        assert review["draft"] == final["draft"] and final["review_feedback"] == f"Source finding {offset + 4}."
    assert all(p.read_bytes() == data for p, data in old.items())
    assert entry.verify_results()["work_posts"] == 14
    assert entry.verify_results()["semantic_quality_verified"] is False


@pytest.mark.parametrize("filename", ["response-01.json", "payload-01.json"])
def test_prior_packet_byte_drift_blocks_next_independent_leaf_payment(entry, monkeypatch, filename):
    original = entry.expected_payload
    changed = []
    def drifted(frozen, sample, sample_post, ledger, codec):
        if sample_post == 2 and not changed:
            changed.append(1)
            path = entry.RESULTS / filename
            path.write_bytes(path.read_bytes() + b" ")
        return original(frozen, sample, sample_post, ledger, codec)
    monkeypatch.setattr(entry, "expected_payload", drifted)
    index, calls = execute(entry)
    assert index["posts"] == 1 and index["stopped_on_error"] and len(calls) == 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 5


def test_regression_suite_uses_real_short_medium_ids_one_call_each_no_long(entry):
    entry.select_suite("regression")
    assert [s["id"] for s in entry.plan()["samples"]] == ["zh-short", "en-medium"]
    index, calls = execute(entry)
    assert index["posts"] == 2 and len(calls) == 2 and not index["stopped_on_error"]
    assert "Evidence and draft:" not in json.dumps(calls)
    assert entry.verify_results()["work_posts"] == 6


@pytest.mark.parametrize("fault", ["http", "reserve"])
def test_failed_attempt_preserved_and_stops_without_retry_or_refund(entry, monkeypatch, fault):
    entry.freeze()
    entry.check()
    calls = []
    if fault == "reserve":
        original, failed = entry.engine.durable, []
        def broken(path, value):
            if path == entry.GROUP and value.get("reserved_posts") == 5 and not failed:
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
    assert entry.read(entry.GROUP)["reserved_posts"] == 5
    assert entry.verify_results()["stopped_on_error"]


@pytest.mark.parametrize("kind", ["malformed", "overpoints", "truncated", "model"])
def test_bad_merge_raw_never_preallocates_or_sends_refinement(entry, kind):
    entry.freeze()
    entry.check()
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) != 3:
            return response(len(calls))
        body = response(3).json()
        if kind == "malformed":
            body["choices"][0]["message"]["content"] = "bad draft"
        elif kind == "overpoints":
            body["choices"][0]["message"]["content"] = json.dumps({"summary": "Oversized", "key_points": ["Point"] * 15})
        elif kind == "truncated":
            body["choices"][0]["finish_reason"] = "length"
        else:
            body["model"] = "changed"
        return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json=body)
    index = entry.run(transport=SimpleNamespace(post=post))
    assert len(calls) == 3 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 7
    assert entry.verify_results()["stopped_on_error"]


def test_dynamic_revision_capacity_overflow_stops_after_paid_merge(entry):
    entry.freeze()
    entry.check()
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        body = response(len(calls)).json()
        if len(calls) == 3:
            body["choices"][0]["message"]["content"] = json.dumps({"summary": "large draft " * 6000,
                "key_points": ["Complete draft condition."]})
        return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json=body)
    index = entry.run(transport=SimpleNamespace(post=post))
    assert len(calls) == 3 and index["stopped_on_error"]
    assert entry.verify_results()["posts"] == 3


@pytest.mark.parametrize("kind", ["source", "newsource", "criteria", "profile", "code"])
def test_drift_before_send_closes_without_post_or_preallocation(entry, kind):
    entry.freeze()
    entry.check()
    if kind == "source":
        (entry.OLD_CORPUS / "en-long.txt").write_text("changed", encoding="utf-8")
    elif kind == "newsource":
        (entry.NEW_CORPUS / "en-long-unseen.txt").write_text("changed", encoding="utf-8")
    elif kind == "criteria":
        (entry.REPORT / "unseen-review-criteria.md").write_text("changed", encoding="utf-8")
    elif kind == "profile":
        entry.test_settings.llm_summary_fidelity_mode = "off"
    else:
        (entry.PROJECT / "backend/app/services/llm_service.py").write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Drift reached HTTP")))
    assert entry.read(entry.GROUP)["reserved_posts"] == 4
    assert entry.read(entry.TRACKER)["status"] == "closed"


def test_next_phase_retains_cumulative_actual_counts(entry):
    execute(entry)
    entry.select_phase("phase-4")
    entry.select_suite("regression")
    calls = []
    execute(entry, post=lambda *a, **kw: calls.append(1) or response(len(calls)))
    assert calls == [1, 1]
    assert entry.verify_results()["work_posts"] == 16


@pytest.mark.parametrize("drift", ["profile", "versions", "helper"])
def test_closed_verify_uses_frozen_profile_sources_helpers(entry, monkeypatch, drift):
    execute(entry)
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Closed verify read env"))
    if drift == "profile":
        monkeypatch.setattr(entry, "CONFIG", {})
    elif drift == "versions":
        monkeypatch.setattr(entry.engine, "versions", lambda: {"future": "99"})
    else:
        monkeypatch.setattr(entry.test_service, "_summary_revision_messages", lambda *a, **kw: pytest.fail("Live revision helper used"))
        (entry.PROJECT / "backend/app/services/llm_service.py").write_text("changed", encoding="utf-8")
    assert entry.verify_results()["posts"] == 10


@pytest.mark.parametrize("kind", ["path", "hash", "attribution", "duplicate"])
def test_multicorpus_identity_license_and_safe_paths_refused_before_allocation(entry, kind):
    path = entry.NEW_CORPUS / "manifest.json"
    manifest = entry.read(path)
    row = manifest["samples"][0]
    if kind == "path":
        row["file"] = "../corpus/en-long.txt"
    elif kind == "hash":
        row["sha256"] = "0" * 64
    elif kind == "attribution":
        row["attribution"] = ""
    else:
        manifest["samples"].append(dict(row))
    entry.io.durable(path, manifest)
    with pytest.raises(RuntimeError):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_shared_lock_never_auto_removed(entry):
    entry.SHARED_LOCK.mkdir()
    with pytest.raises(FileExistsError):
        entry.freeze()
    assert entry.SHARED_LOCK.exists()


@pytest.mark.parametrize("allocation", ["directory", "tracker_writing"])
def test_orphan_allocation_is_retained_and_blocks_before_runtime(entry, monkeypatch, allocation):
    if allocation == "directory":
        target = entry.RESULTS
        target.mkdir(parents=True)
    else:
        target = entry.GROUP.with_name("phase-7.json.writing")
        target.write_text("Interrupted allocation\n", encoding="utf-8")
    monkeypatch.setattr(entry, "_live_runtime", lambda: pytest.fail("Orphan allocation reached runtime/env"))
    with pytest.raises(RuntimeError):
        entry.freeze()
    assert target.exists() and entry.read(entry.GROUP)["reserved_posts"] == 4
