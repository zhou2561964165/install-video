"""Offline safety regressions for the two-request repair acceptance phase."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-09-adaptive-summary-repair/scripts/evaluate.py"


@pytest.fixture
def entry(tmp_path, monkeypatch):
    assert SCRIPT.exists(), "Repair acceptance runner has not been implemented"
    spec = importlib.util.spec_from_file_location("repair_acceptance_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    monkeypatch.setattr(module, "REPORT", tmp_path / "repair")
    monkeypatch.setattr(module, "RESULTS", tmp_path / "repair/results")
    monkeypatch.setattr(module, "TRACKER", tmp_path / "tracker.json")
    monkeypatch.setattr(module, "SHARED_LOCK", tmp_path / "caller.lock")
    monkeypatch.setattr(module, "CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(module, "GROUP", tmp_path / "group.json")
    monkeypatch.setattr(module, "LONG_TRACKER", tmp_path / "long-tracker.json")
    monkeypatch.setattr(module, "SHORT_TRACKER", tmp_path / "short-tracker.json")
    monkeypatch.setattr(module, "OLD_FINAL", tmp_path / "final")
    monkeypatch.setattr(module, "OLD_REPAIRED", tmp_path / "repaired")
    monkeypatch.setattr(module, "LONG_REPORT", tmp_path / "long")
    monkeypatch.setattr(module, "SHORT_REPORT", tmp_path / "short")
    module.CORPUS.mkdir()
    sources = []
    for sid in ("zh-short", "en-medium"):
        path = module.CORPUS / f"{sid}.txt"
        path.write_text("Source conditions and related examples.\n", encoding="utf-8")
        sources.append({"id": sid, "file": path.name, "title": sid,
                        "sha256": module.io.digest(path.read_bytes()),
                        "license": "CC BY-NC-SA4", "attribution": "MIT"})
    module.io.exclusive(module.CORPUS / "manifest.json", {"samples": sources})
    group = {"work_id": module.WORK_ID, "hard_ceiling": 26, "status": "closed",
             "reserved_posts": 17, "phases": []}
    for root, phase, count in ((module.OLD_FINAL, "quality-final", 3),
                                (module.OLD_REPAIRED, "quality-repaired", 14)):
        path = root / "results/request-ledger.json"
        module.io.exclusive(path, {"phase": phase, "ceiling": 19, "requests": [
            {"phase": phase, "ordinal": i} for i in range(1, count + 1)]})
        group["phases"].append({"phase": phase, "ledger": str(path), "ceiling": 19})
    module.io.exclusive(module.GROUP, group)
    for root, tracker, phase, parent, count in (
            (module.LONG_REPORT, module.LONG_TRACKER, "adaptive-transcript-long", 17, 3),
            (module.SHORT_REPORT, module.SHORT_TRACKER, "adaptive-transcript-short-medium", 20, 2)):
        requests = []
        for i in range(1, count + 1):
            row = {"ordinal": i, "status": "response", "http_status": 200}
            for name in ("payload", "response"):
                path = root / f"results/{name}-{i:02d}.json"
                module.io.exclusive(path, {"offline": True})
                row[f"{name}_sha256"] = module.io.digest(path.read_bytes())
            requests.append(row)
        module.io.exclusive(root / "results/request-ledger.json", {
            "work_id": module.WORK_ID, "phase": phase, "prior_posts": parent,
            "maximum_posts": count, "requests": requests})
        module.io.exclusive(tracker, {"work_id": module.WORK_ID, "status": "closed",
            "hard_ceiling": 26, "parent_posts": parent, "maximum_posts": count,
            "maximum_work_posts": parent + count, "reserved_posts": parent + count,
            "ledger": str(root / "results/request-ledger.json"), "parent_snapshot": str(module.GROUP),
            **({"phase": phase} if count == 2 else {})})
        if count == 3:
            module.io.exclusive(root / "results/result.json", {"success": True})
        else:
            module.io.exclusive(root / "results/result-index.json", {"phase": phase, "posts": 2,
                "stopped_on_error": False, "samples": [{"sample": s, "success": True} for s in module.SAMPLES]})
    asset = tmp_path / "service.py"
    asset.write_text("frozen product module", encoding="utf-8")
    monkeypatch.setattr(module, "asset_paths", lambda: [asset, module.GROUP,
        module.LONG_TRACKER, module.SHORT_TRACKER, *module.CORPUS.glob("*")])
    settings = SimpleNamespace(llm_provider="offline", llm_model="offline-model",
        llm_timeout_seconds=5, **module.CONFIG)

    class Service:
        @staticmethod
        def _summary_input(source):
            return source.strip()

        @staticmethod
        def _summary_chunks(source, limit):
            return [source]

        @staticmethod
        def summarize_text(source, *, title, output_language, client):
            response = client.post("https://offline.invalid/chat/completions", headers={},
                json={"model": settings.llm_model, "messages": [{"role": "user", "content": source}], "max_tokens": 10})
            response.raise_for_status()
            body = json.loads(response.json()["choices"][0]["message"]["content"])
            from dataclasses import make_dataclass
            result_type = make_dataclass("Summary", ["summary", "key_points", "provider", "model"])
            return result_type(body["summary"].strip(), [p.strip() for p in body["key_points"]],
                               settings.llm_provider, settings.llm_model)

    monkeypatch.setattr(module, "runtime", lambda: (settings, Service, "https://offline.invalid/chat/completions"))
    return module


def response():
    return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json={
        "model": "offline-model", "usage": {"total_tokens": 10}, "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps({
                "summary": " Overview ", "key_points": [" Complete conditions. "]})}}]})


def ready(entry):
    entry.freeze()
    entry.check()


def test_plan_is_offline_and_counts_all_four_closed_phases(entry, monkeypatch):
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Plan read dotenv"))
    plan = entry.plan()
    assert plan["prior_posts"] == 22 and plan["maximum_work_posts"] == 24
    assert plan["network"] is False and plan["dotenv_read"] is False
    assert [s["id"] for s in plan["samples"]] == ["zh-short", "en-medium"]


def test_run_requires_persisted_offline_check(entry):
    entry.freeze()
    with pytest.raises(RuntimeError, match="check"):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Unchecked POST")))


def test_reservation_is_durable_before_transport_and_phase_closes(entry):
    ready(entry)

    def post(*args, **kwargs):
        ledger = entry.read(entry.RESULTS / "request-ledger.json")
        assert ledger["requests"][-1]["status"] == "reserved"
        assert entry.read(entry.TRACKER)["reserved_posts"] == 22 + len(ledger["requests"])
        assert (entry.RESULTS / f"payload-{len(ledger['requests']):02d}.json").exists()
        return response()

    entry.run(transport=SimpleNamespace(post=post))
    assert entry.verify_results()["work_posts"] == 24
    assert entry.read(entry.TRACKER)["status"] == "closed"
    with pytest.raises(RuntimeError, match="reopen|started"):
        entry.run(transport=SimpleNamespace(post=post))


@pytest.mark.parametrize("failure", ["network", "non_json", "http", "invalid_summary"])
def test_failed_attempt_is_counted_and_second_sample_not_sent(entry, failure):
    ready(entry)

    def post(*args, **kwargs):
        if failure == "network":
            raise httpx.ConnectError("offline failure")
        if failure == "non_json":
            return httpx.Response(200, text="not JSON")
        res = response()
        if failure == "http":
            return httpx.Response(503, request=res.request, json={"error": "unavailable"})
        return httpx.Response(200, request=res.request, json={"choices": [
            {"finish_reason": "stop", "message": {"content": "not summary JSON"}}]})

    result = entry.run(transport=SimpleNamespace(post=post))
    assert result["stopped_on_error"] is True and result["posts"] == 1
    assert entry.read(entry.TRACKER)["reserved_posts"] == 23
    assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][0]["status"] in ("error", "response")
    verified = entry.verify_results()
    assert verified["posts"] == 1 and verified["stopped_on_error"] is True
    assert not (entry.RESULTS / "en-medium.json").exists()


def test_current_asset_changes_block_pre_send_but_not_closed_snapshot_verify(entry):
    ready(entry)
    asset = entry.PROJECT / "service.py"
    asset.write_text("changed before send", encoding="utf-8")
    with pytest.raises(RuntimeError, match="asset|input"):
        entry.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail("Drifted POST")))


def test_snapshot_verify_survives_current_document_updates_and_rejects_snapshot_tamper(entry):
    ready(entry)
    entry.run(transport=SimpleNamespace(post=lambda *a, **k: response()))
    (entry.PROJECT / "service.py").write_text("later mutable documentation", encoding="utf-8")
    assert entry.verify_results()["evidence_hashes_verified"] is True
    frozen = entry.read(entry.RESULTS / "provenance.json")
    snapshot = entry.RESULTS / next(iter(frozen["snapshots"].values()))["file"]
    snapshot.write_text("tampered", encoding="utf-8")
    with pytest.raises(RuntimeError, match="snapshot"):
        entry.verify_results()


def test_semantic_success_is_not_implied_by_http_success(entry):
    ready(entry)
    entry.run(transport=SimpleNamespace(post=lambda *a, **k: response()))
    assert entry.verify_results()["semantic_quality_verified"] is False


def test_result_must_correspond_to_raw_response_even_if_index_hash_is_rewritten(entry):
    ready(entry)
    entry.run(transport=SimpleNamespace(post=lambda *a, **k: response()))
    path = entry.RESULTS / "zh-short.json"
    result = entry.read(path)
    result["result"]["summary"] = "invented"
    entry.io.durable(path, result)
    changed_hash = entry.io.digest(path.read_bytes())
    ledger = entry.read(entry.RESULTS / "request-ledger.json")
    ledger["requests"][0]["result_sha256"] = changed_hash
    entry.io.durable(entry.RESULTS / "request-ledger.json", ledger)
    index = entry.read(entry.RESULTS / "result-index.json")
    index["samples"][0]["result_sha256"] = changed_hash
    entry.io.durable(entry.RESULTS / "result-index.json", index)
    with pytest.raises(RuntimeError, match="raw|response"):
        entry.verify_results()


def test_closed_prior_phase_drift_refuses_freeze(entry):
    value = entry.read(entry.SHORT_TRACKER)
    value["reserved_posts"] = 21
    entry.io.durable(entry.SHORT_TRACKER, value)
    with pytest.raises(RuntimeError, match="Historical|prior|closed"):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_shared_caller_lock_blocks_new_phase(entry):
    entry.SHARED_LOCK.mkdir()
    with pytest.raises(FileExistsError):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_reservation_write_failure_never_sends_and_retains_attempt_budget(entry, monkeypatch):
    ready(entry)
    durable = entry.io.durable
    failed = False

    def faulty(path, value):
        nonlocal failed
        if path == entry.TRACKER and value.get("reserved_posts") == 23 and not failed:
            failed = True
            raise OSError("simulated durable tracker write failure")
        durable(path, value)

    monkeypatch.setattr(entry.io, "durable", faulty)
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail("POST before durable tracker")))
    assert index["posts"] == 1 and index["stopped_on_error"] is True
    assert entry.read(entry.TRACKER)["reserved_posts"] == 23
    assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][0]["status"] == "error"
    assert entry.verify_results()["posts"] == 1


def test_changed_runtime_during_post_stops_without_second_reservation(entry):
    ready(entry)
    settings, _, _ = entry.runtime()

    def post(*args, **kwargs):
        settings.llm_model = "drifted-model"
        return response()

    index = entry.run(transport=SimpleNamespace(post=post))
    assert index["posts"] == 1 and index["stopped_on_error"] is True
    assert entry.read(entry.TRACKER)["reserved_posts"] == 23
    assert entry.verify_results()["posts"] == 1


def test_result_index_cannot_claim_failure_when_all_results_succeeded(entry):
    ready(entry)
    entry.run(transport=SimpleNamespace(post=lambda *a, **k: response()))
    index = entry.read(entry.RESULTS / "result-index.json")
    index["stopped_on_error"] = True
    entry.io.durable(entry.RESULTS / "result-index.json", index)
    with pytest.raises(RuntimeError, match="failure|disposition"):
        entry.verify_results()


def test_interrupted_transport_closes_with_counted_error_and_no_reopen(entry):
    ready(entry)

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        entry.run(transport=SimpleNamespace(post=interrupted))
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.TRACKER)["reserved_posts"] == 23
    assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][0]["status"] == "error"
    assert entry.verify_results()["stopped_on_error"] is True


def test_client_construction_failure_closes_zero_post_phase(entry, monkeypatch):
    ready(entry)

    def cannot_construct(*args, **kwargs):
        raise RuntimeError("offline client constructor failed")

    monkeypatch.setattr(httpx, "Client", cannot_construct)
    with pytest.raises(RuntimeError, match="constructor"):
        entry.run()
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.TRACKER)["reserved_posts"] == 22
    assert entry.read(entry.RESULTS / "result-index.json")["posts"] == 0
    assert entry.verify_results()["stopped_on_error"] is True


def test_success_results_require_unique_request_evidence_even_for_failed_phase(entry):
    ready(entry)
    entry.run(transport=SimpleNamespace(post=lambda *a, **k: response()))
    ledger = entry.read(entry.RESULTS / "request-ledger.json")
    ledger["requests"] = []
    entry.io.durable(entry.RESULTS / "request-ledger.json", ledger)
    tracker = entry.read(entry.TRACKER)
    tracker["reserved_posts"] = 22
    entry.io.durable(entry.TRACKER, tracker)
    index = entry.read(entry.RESULTS / "result-index.json")
    index.update(posts=0, stopped_on_error=True, phase_error_type="RuntimeError")
    entry.io.durable(entry.RESULTS / "result-index.json", index)
    with pytest.raises(RuntimeError, match="request|success"):
        entry.verify_results()
