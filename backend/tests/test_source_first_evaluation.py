"""New 5/10 POST phase only; synthetic transport and isolated durable evidence."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-10-source-first-summary-live/scripts/evaluate.py"


@pytest.fixture
def entry(tmp_path, monkeypatch):
    assert SCRIPT.exists(), "New source-first runner is missing"
    spec = importlib.util.spec_from_file_location("source_first_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, path in {"PROJECT": tmp_path, "REPORT": tmp_path / "report",
            "RESULTS": tmp_path / "report/results", "CORPUS": tmp_path / "corpus",
            "GROUP": tmp_path / "group.json", "TRACKER": tmp_path / "phase-1.json",
            "SHARED_LOCK": tmp_path / "http.lock"}.items():
        monkeypatch.setattr(module, name, path)
    module.CORPUS.mkdir()
    samples = []
    for sid in module.SAMPLES:
        text = "Actual source condition.\n" if sid != "en-long" else "\n".join(
            f"{i:04d} condition and distinct consequence " + "x" * 40 for i in range(320))
        path = module.CORPUS / f"{sid}.txt"
        path.write_text(text, encoding="utf-8")
        raw = module.CORPUS / f"{sid}.vtt"
        raw.write_text("WEBVTT\n" + text, encoding="utf-8")
        samples.append({"id": sid, "file": path.name, "raw_path": raw.name,
            "title": sid, "sha256": module.io.digest(path.read_bytes()),
            "raw_sha256": module.io.digest(raw.read_bytes()), "license": "CC BY-NC-SA 4.0",
            "attribution": "MIT OCW"})
    module.io.exclusive(module.CORPUS / "manifest.json", {"samples": samples})
    module.io.exclusive(module.GROUP, {"work_id": module.WORK_ID, "hard_ceiling": 10,
        "status": "active", "reserved_posts": 0, "phases": []})
    codec = tmp_path / "backend/app/services/summary_output.py"
    codec.parent.mkdir(parents=True)
    codec.write_bytes((ROOT / "backend/app/services/summary_output.py").read_bytes())
    asset = tmp_path / "source.py"
    asset.write_text("frozen = True\n", encoding="utf-8")
    monkeypatch.setattr(module, "asset_paths", lambda: [asset, codec, *module.CORPUS.iterdir()])
    from app.services import llm_service as service
    settings = SimpleNamespace(**module.CONFIG, llm_provider="offline", llm_model="offline-model",
        llm_api_key="", llm_base_url="https://offline.invalid", llm_timeout_seconds=1,
        llm_summary_max_point_chars=240, llm_summary_notes_language="output",
        llm_summary_source_context_mode="boundary")
    # Historical guards compare the exact JSON prompt string, including field
    # order. Keep their synthetic runtime on the original note serialization;
    # production can independently put source evidence before generated notes.
    def historical_section_notes(results, contexts=None):
        notes = []
        for index, result in enumerate(results):
            note = {"section": index + 1, "summary": result.summary,
                    "key_points": result.key_points}
            if contexts and contexts[index]:
                note["source_context"] = contexts[index]
            notes.append(note)
        return json.dumps(notes, ensure_ascii=False)

    monkeypatch.setattr(service, "_section_notes", historical_section_notes)
    # Freeze plans own their original globally unique caption preparation. Use
    # that existing helper only in this temporary synthetic fixture; production
    # retains later repeated fragments whose antecedents can differ.
    # Continuation adapters export sample_plan but keep cleaned in that original
    # function's module. Bind exactly the helper used by their frozen planner.
    monkeypatch.setattr(service, "_summary_input", module.sample_plan.__globals__["cleaned"])
    monkeypatch.setattr(service, "settings", settings)
    monkeypatch.setattr(module, "runtime", lambda: (settings, service, service._endpoint()))
    module.test_settings, module.test_service, module.test_asset = settings, service, asset
    return module


def response(n=1, *, model="offline-model", summary=None):
    return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json={
        "model": model, "api_key": "DO-NOT-SAVE", "usage": {"total_tokens": 3, "secret": "DO-NOT-SAVE"},
        "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"summary": summary or f" Overview {n} ",
                "key_points": [f" Condition {n}. "]}), "reasoning_content": "DO-NOT-SAVE"}}]})


def ready(entry):
    entry.freeze()
    entry.check()


def test_plan_is_offline_and_freeze_covers_codec(entry, monkeypatch):
    real_runtime = entry.runtime
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Offline plan read runtime"))
    planned = entry.plan()
    assert [s["expected_posts"] for s in planned["samples"]] == [1, 1, 3]
    assert planned["maximum_posts"] == 5 and planned["hard_ceiling"] == 10
    monkeypatch.setattr(entry, "runtime", real_runtime)
    ready(entry)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    assert frozen["library_versions"]["pydantic"]
    assert frozen["library_versions"]["pydantic_core"]
    assert "backend/app/services/summary_output.py" in frozen["snapshots"]


def test_runtime_version_drift_refuses_before_http(entry, monkeypatch):
    ready(entry)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    recorded = frozen["library_versions"]
    assert {"python", "httpx", "httpcore", "python-dotenv", "pydantic", "pydantic_core"} <= recorded.keys()
    assert all(isinstance(value, str) and value for value in recorded.values())
    monkeypatch.setattr(entry, "versions", lambda: recorded | {"httpx": "simulated-version-drift"})
    with pytest.raises(RuntimeError, match="codec|configuration"):
        entry.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail("Version drift reached HTTP")))
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 0
    assert entry.read(entry.RESULTS / "request-ledger.json")["requests"] == []


def test_five_posts_reserved_before_http_and_last_raw_binds_each_result(entry, monkeypatch):
    ready(entry)
    sent = []

    def post(*args, **kwargs):
        ledger, group = entry.read(entry.RESULTS / "request-ledger.json"), entry.read(entry.GROUP)
        sent.append(group["reserved_posts"])
        assert ledger["requests"][-1]["status"] == "reserved"
        assert len(ledger["requests"]) == group["reserved_posts"] == entry.read(entry.TRACKER)["reserved_posts"]
        return response(len(sent))

    index = entry.run(transport=SimpleNamespace(post=post))
    assert sent == [1, 2, 3, 4, 5] and not index["stopped_on_error"]
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Verify read dotenv"))
    # Offline verification uses frozen codec bytes, not today's mutable codec.
    (entry.PROJECT / "backend/app/services/summary_output.py").write_text("raise RuntimeError('changed')")
    verified = entry.verify_results()
    assert verified["posts"] == verified["work_posts"] == 5
    assert verified["semantic_quality_verified"] is False
    assert entry.read(entry.RESULTS / "en-long.json")["result"]["summary"] == "Overview 5"
    ledger = entry.read(entry.RESULTS / "request-ledger.json")
    assert [r["sample_post"] for r in ledger["requests"]] == [1, 1, 1, 2, 3]
    assert [r["stage"] for r in ledger["requests"]] == ["extract", "extract", "extract", "extract", "merge"]
    assert "DO-NOT-SAVE" not in (entry.RESULTS / "response-01.json").read_text()
    with pytest.raises(RuntimeError):
        entry.run(transport=SimpleNamespace(post=post))


@pytest.mark.parametrize("boundary", ["sample", "group"])
def test_extra_attempt_is_refused_without_transport_or_refund(entry, monkeypatch, boundary):
    ready(entry)
    if boundary == "group":
        group = entry.read(entry.GROUP)
        group["reserved_posts"] = 9
        entry.io.durable(entry.GROUP, group)
    else:
        original = entry.test_service.summarize_text

        def double(source, **kwargs):
            result = original(source, **kwargs)
            original(source, **kwargs)
            return result

        monkeypatch.setattr(entry.test_service, "summarize_text", double)
    sent = []
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **k: sent.append(1) or response()))
    assert index["stopped_on_error"]
    assert len(sent) <= 1
    assert entry.read(entry.GROUP)["reserved_posts"] >= len(sent)
    assert entry.read(entry.TRACKER)["status"] == "closed"


def test_work_group_reaches_ten_and_phase_sixth_post_is_refused(entry, monkeypatch):
    group = entry.read(entry.GROUP)
    group.update(reserved_posts=5, phases=[{"phase": "fixture-previous", "status": "closed", "reserved_posts": 5}])
    entry.io.durable(entry.GROUP, group)
    ready(entry)
    original = entry.test_service.summarize_text
    def extra_long(source, **kw):
        result = original(source, **kw)
        if kw["title"] == "en-long":
            original(source, **kw)
        return result
    monkeypatch.setattr(entry.test_service, "summarize_text", extra_long)
    sent = []
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **k: sent.append(1) or response(len(sent))))
    assert len(sent) == index["posts"] == 5 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 10
    assert entry.read(entry.GROUP)["status"] == "closed"
    assert entry.verify_results()["work_posts"] == 10


def test_freeze_refuses_insufficient_group_headroom_before_runtime(entry, monkeypatch):
    group = entry.read(entry.GROUP)
    group["reserved_posts"] = 6
    entry.io.durable(entry.GROUP, group)
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Headroom failure reached runtime"))
    with pytest.raises(RuntimeError, match="headroom"):
        entry.freeze()
    assert not entry.RESULTS.exists()


@pytest.mark.parametrize("kind", ["ledger", "group", "tracker"])
def test_failed_reservation_write_sends_no_post_and_closes(entry, monkeypatch, kind):
    ready(entry)
    target = {"ledger": entry.RESULTS / "request-ledger.json", "group": entry.GROUP,
        "tracker": entry.TRACKER}[kind]
    original = entry.durable
    fired = []

    def broken(path, value):
        reserving = (path == target and (value.get("reserved_posts", 0) > 0
            or value.get("requests") and value["requests"][-1]["status"] == "reserved"))
        if reserving and not fired:
            fired.append(True)
            raise OSError("disk failure")
        return original(path, value)

    monkeypatch.setattr(entry, "durable", broken)
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail("Reservation failed but HTTP sent")))
    assert index["stopped_on_error"] and fired
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 1


def test_atomic_replace_failure_preserves_reservation_and_closes(entry, monkeypatch):
    ready(entry)
    original = entry.os.replace
    failed = []
    def fail_once(source, destination):
        if Path(destination) == entry.GROUP and not failed:
            failed.append(True)
            raise OSError("single atomic replace failure")
        return original(source, destination)
    monkeypatch.setattr(entry.os, "replace", fail_once)
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **k: pytest.fail("Replace failed but HTTP sent")))
    assert failed and index["stopped_on_error"] and index["posts"] == 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 1
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert not entry.GROUP.with_name(entry.GROUP.name + ".writing").exists()
    assert entry.verify_results()["posts"] == 1


def test_http_error_keeps_attempt_and_closed_receipt(entry):
    ready(entry)
    sent = []
    def fail_http(*a, **k):
        sent.append(1)
        raise httpx.ConnectError("synthetic transport failure")
    index = entry.run(transport=SimpleNamespace(post=fail_http))
    assert sent == [1] and index["stopped_on_error"] and index["posts"] == 1
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.read(entry.GROUP)["reserved_posts"] == 1
    assert entry.read(entry.RESULTS / "request-ledger.json")["requests"][0]["status"] == "error"
    assert entry.verify_results()["posts"] == 1


def test_owned_durable_keeps_preexisting_temporary_file(entry):
    temporary = entry.GROUP.with_name(entry.GROUP.name + ".writing")
    temporary.write_bytes(b"preexisting-owner")
    original = entry.GROUP.read_bytes()
    with pytest.raises(FileExistsError):
        entry.durable(entry.GROUP, {"replacement": "refused"})
    assert temporary.read_bytes() == b"preexisting-owner"
    assert entry.GROUP.read_bytes() == original


def test_owned_durable_refuses_path_outside_phase(entry):
    path = entry.PROJECT / "unowned.json"
    with pytest.raises(RuntimeError, match="owned"):
        entry.durable(path, {"replacement": "refused"})
    assert not path.exists() and not path.with_name(path.name + ".writing").exists()


@pytest.mark.parametrize("drift", ["asset", "model", "provider", "endpoint", "config", "payload", "raw_model"])
def test_per_post_drift_stops_and_closes(entry, monkeypatch, drift):
    ready(entry)
    sent = []
    if drift == "payload":
        original = entry.test_service._complete

        def wrong(*a, **kw):
            kw["max_tokens"] = 1
            return original(*a, **kw)

        monkeypatch.setattr(entry.test_service, "_complete", wrong)

    def post(*a, **kw):
        sent.append(1)
        if drift == "asset":
            entry.test_asset.write_text("changed")
        elif drift in {"model", "provider", "endpoint", "config"}:
            key = {"model": "llm_model", "provider": "llm_provider", "endpoint": "llm_base_url",
                "config": "llm_summary_max_output_tokens"}[drift]
            setattr(entry.test_settings, key, 1 if drift == "config" else "changed")
        return response(model="other-model" if drift == "raw_model" else "offline-model")

    index = entry.run(transport=SimpleNamespace(post=post))
    assert index["stopped_on_error"] and len(sent) <= 1
    assert entry.read(entry.TRACKER)["status"] == "closed"


@pytest.mark.parametrize("kind", ["initialization", "interrupt"])
def test_client_init_and_keyboardinterrupt_close_phase(entry, monkeypatch, kind):
    ready(entry)
    if kind == "initialization":
        monkeypatch.setattr(httpx, "Client", lambda **kw: (_ for _ in ()).throw(RuntimeError("constructor failed")))
        with pytest.raises(RuntimeError):
            entry.run()
    else:
        def interrupted(*a, **kw):
            raise KeyboardInterrupt
        with pytest.raises(KeyboardInterrupt):
            entry.run(transport=SimpleNamespace(post=interrupted))
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.verify_results()["stopped_on_error"] is True


def test_verify_rejects_multistage_final_result_swapped_to_first_raw(entry):
    ready(entry)
    calls = []
    entry.run(transport=SimpleNamespace(post=lambda *a, **k: calls.append(1) or response(len(calls))))
    result = entry.read(entry.RESULTS / "en-long.json")
    result["result"]["summary"] = "Overview 3"
    entry.io.durable(entry.RESULTS / "en-long.json", result)
    index = entry.read(entry.RESULTS / "result-index.json")
    index["samples"][-1]["result_sha256"] = entry.io.digest((entry.RESULTS / "en-long.json").read_bytes())
    entry.io.durable(entry.RESULTS / "result-index.json", index)
    ledger = entry.read(entry.RESULTS / "request-ledger.json")
    for row in ledger["requests"][-3:]:
        row["result_sha256"] = index["samples"][-1]["result_sha256"]
    entry.io.durable(entry.RESULTS / "request-ledger.json", ledger)
    # Rebind hashes to exercise raw/final correspondence, not just checksum refusal.
    receipt = entry.read(entry.RESULTS / "closed-receipt.json")
    receipt.update(ledger_sha256=entry.io.digest((entry.RESULTS / "request-ledger.json").read_bytes()),
        index_sha256=entry.io.digest((entry.RESULTS / "result-index.json").read_bytes()))
    entry.io.durable(entry.RESULTS / "closed-receipt.json", receipt)
    checksum = entry.io.digest((entry.RESULTS / "closed-receipt.json").read_bytes())
    tracker = entry.read(entry.TRACKER)
    tracker["closed_receipt_sha256"] = checksum
    entry.io.durable(entry.TRACKER, tracker)
    group = entry.read(entry.GROUP)
    group["phases"][-1]["closed_receipt_sha256"] = checksum
    entry.io.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="last raw"):
        entry.verify_results()


def test_secret_file_in_asset_inventory_refuses_freeze(entry, monkeypatch):
    asset = entry.PROJECT / ".env"
    asset.write_text("TEST_SECRET_DO_NOT_SNAPSHOT=synthetic", encoding="utf-8")
    original = entry.asset_paths
    monkeypatch.setattr(entry, "asset_paths", lambda: original() + [asset])
    with pytest.raises(RuntimeError, match="Unsafe"):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_merge_capacity_error_does_not_grow_posts(entry):
    ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        return response(len(calls), summary="a" * 31000 if len(calls) >= 3 else None)
    index = entry.run(transport=SimpleNamespace(post=post))
    assert len(calls) == 4 and index["stopped_on_error"]
    assert index["posts"] == entry.read(entry.GROUP)["reserved_posts"] == 4
