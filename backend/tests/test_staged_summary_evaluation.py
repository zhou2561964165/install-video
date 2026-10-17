"""Only new staged continuation; isolated parent copies, synthetic HTTP, no dotenv."""
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-10-staged-summary-live/scripts/evaluate.py"
OLD_REPORT = ROOT / "docs/acceptance-reports/2026-10-10-source-first-summary-live"
PLANNING = ROOT / "backend/tests/fixtures/source-first-parent"


@pytest.fixture
def entry(tmp_path, monkeypatch):
    assert SCRIPT.exists(), "New staged runner missing"
    spec = importlib.util.spec_from_file_location("staged_acceptance_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parent_report = tmp_path / OLD_REPORT.relative_to(ROOT)
    shutil.copytree(OLD_REPORT / "results", parent_report / "results")
    (parent_report / "scripts").mkdir()
    shutil.copyfile(OLD_REPORT / "scripts/evaluate.py", parent_report / "scripts/evaluate.py")
    corpus = tmp_path / "docs/acceptance-reports/2026-10-04-natural-subtitle-quality/corpus"
    shutil.copytree(ROOT / corpus.relative_to(tmp_path), corpus)
    parent_group = tmp_path / ".planning/parent-group.json"
    parent_tracker = tmp_path / ".planning/parent-phase.json"
    parent_group.parent.mkdir()
    group = json.loads((PLANNING / "budget-group.json").read_text(encoding="utf-8"))
    group["status"] = "closed"
    row = group["phases"][0]
    row.update(ledger=str(parent_report / "results/request-ledger.json"), tracker=str(parent_tracker))
    parent_group.write_text(json.dumps(group), encoding="utf-8")
    tracker = json.loads((PLANNING / "phase-1.json").read_text(encoding="utf-8"))
    tracker["ledger"] = row["ledger"]
    parent_tracker.write_text(json.dumps(tracker), encoding="utf-8")
    report = tmp_path / "docs/acceptance-reports/staged-fixture"
    for name, path in {"PROJECT": tmp_path, "REPORT": report, "RESULTS": report / "results",
            "CORPUS": corpus, "PARENT_REPORT": parent_report, "PARENT_RESULTS": parent_report / "results",
            "PARENT_GROUP": parent_group, "PARENT_TRACKER": parent_tracker,
            "PARENT_RUNNER": parent_report / "scripts/evaluate.py", "GROUP": tmp_path / ".planning/group-2.json",
            "TRACKER": tmp_path / ".planning/phase-2.json", "SHARED_LOCK": tmp_path / "caller.lock"}.items():
        monkeypatch.setattr(module, name, path)
    continuation = group | {"status": "active", "hard_ceiling": 12,
        "parent_snapshot": str(parent_group), "parent_sha256": module.io.digest(parent_group.read_bytes()),
        "parent_posts": 5, "budget_adjustment": {"from": 10, "to": 12}}
    module.io.exclusive(module.GROUP, continuation)
    codec = tmp_path / "backend/app/services/summary_output.py"
    codec.parent.mkdir(parents=True)
    codec.write_bytes((ROOT / "backend/app/services/summary_output.py").read_bytes())
    artifact = tmp_path / "artifact.py"
    artifact.write_text("current = True\n", encoding="utf-8")
    monkeypatch.setattr(module, "asset_paths", lambda: [artifact, codec,
        *[p for p in parent_report.rglob("*") if p.is_file()], parent_group, parent_tracker,
        *[p for p in corpus.rglob("*") if p.is_file()]])
    from app.services import llm_service as service
    frozen = module.read(module.PARENT_RESULTS / "provenance.json")
    settings = SimpleNamespace(**module.CONFIG, llm_provider=frozen["provider"], llm_model=frozen["model"],
        llm_api_key="", llm_base_url="https://offline.invalid", llm_timeout_seconds=1,
        llm_summary_max_point_chars=240, llm_summary_notes_language="output",
        llm_summary_source_context_mode="boundary")
    # This continuation checks source parts bound by the closed parent's
    # globally unique preparation, not the current production caption policy.
    monkeypatch.setattr(service, "_summary_input", module.base.cleaned)
    monkeypatch.setattr(service, "settings", settings)
    monkeypatch.setattr(module, "runtime", lambda: (settings, service, service._endpoint()))
    module.test_service, module.test_settings, module.test_artifact = service, settings, artifact
    module.parent_bytes = {p: p.read_bytes() for p in [parent_group, parent_tracker,
        *[p for p in parent_report.rglob("*") if p.is_file()]]}
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def response(entry, payload, n=1, *, invalid=False, model=None):
    points = "Generate only key_points" in payload["messages"][0]["content"]
    content = {"key_points": [f"Complete condition {n}."]} if points else {"summary": f"Overview {n}."}
    if invalid:
        content["unexpected"] = "structure error"
    return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"), json={
        "model": model or entry.test_settings.llm_model,
        "usage": {"total_tokens": 3, "arbitrary": "DO-NOT-SAVE"},
        "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(content), "reasoning_content": "DO-NOT-SAVE"}}]})


def test_plan_and_frozen_parent_notes_are_offline(entry, monkeypatch):
    original = entry.runtime
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Plan read dotenv/runtime"))
    planned = entry.plan()
    assert planned["parent_posts"] == 5 and planned["maximum_posts"] == 7 and planned["hard_ceiling"] == 12
    assert [s["expected_posts"] for s in planned["samples"]] == [2, 2, 2]
    assert planned["parent_semantic_quality_verified"] is False
    monkeypatch.setattr(entry, "runtime", original)
    ready(entry)
    frozen = entry.read(entry.RESULTS / "provenance.json")
    assert frozen["library_versions"]["langchain-core"] and frozen["library_versions"]["langsmith"]
    assert [r["parent_ordinal"] for r in frozen["reused_sections"]] == [3, 4]


@pytest.mark.parametrize("repair", [False, True])
def test_six_or_seven_requests_reserve_parent_five_and_bind_both_roles(entry, monkeypatch, repair):
    ready(entry)
    sent = []
    def post(*a, **kw):
        ledger, group = entry.read(entry.RESULTS / "request-ledger.json"), entry.read(entry.GROUP)
        sent.append(group["reserved_posts"])
        assert sent[-1] == 5 + len(ledger["requests"])
        assert ledger["requests"][-1]["status"] == "reserved"
        return response(entry, kw["json"], len(sent), invalid=repair and len(sent) == 1)
    index = entry.run(transport=SimpleNamespace(post=post))
    assert index["posts"] == len(sent) == (7 if repair else 6)
    assert sent == list(range(6, 13 if repair else 12))
    assert index["stopped_on_error"] is False
    assert all(p.read_bytes() == raw for p, raw in entry.parent_bytes.items())
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Verify read product runtime"))
    verified = entry.verify_results()
    assert verified["work_posts"] == (12 if repair else 11)
    assert verified["semantic_quality_verified"] is False
    ledger = entry.read(entry.RESULTS / "request-ledger.json")
    assert not any(r["stage"].startswith("leaf") for r in ledger["requests"])
    for item in index["samples"]:
        accepted = [r for r in ledger["requests"] if r["sample"] == item["sample"]]
        points_row = [r for r in accepted if r["stage"].startswith("points")][-1]
        overview_row = accepted[-1]
        public = entry.read(entry.RESULTS / f"{item['sample']}.json")["result"]
        assert public["key_points"] == [f"Complete condition {points_row['ordinal']}."]
        assert public["summary"] == f"Overview {overview_row['ordinal']}."
    with pytest.raises(RuntimeError, match="reopen|started"):
        entry.run(transport=SimpleNamespace(post=post))


def test_second_format_is_refused_without_spending_phase_remainder(entry):
    ready(entry)
    sent = []
    def post(*a, **kw):
        sent.append(1)
        return response(entry, kw["json"], len(sent), invalid=len(sent) in {1, 4})
    index = entry.run(transport=SimpleNamespace(post=post))
    assert len(sent) == index["posts"] == 4 and index["stopped_on_error"]
    assert entry.read(entry.GROUP)["reserved_posts"] == 9
    assert entry.verify_results()["format_posts"] == 1


@pytest.mark.parametrize("tamper", ["parent_group", "leaf_sample", "leaf_payload", "leaf_raw", "source"])
def test_parent_source_stage_or_hash_drift_refuses_allocation(entry, tamper):
    if tamper == "parent_group":
        value = entry.read(entry.PARENT_GROUP)
        value["status"] = "active"
        entry.io.durable(entry.PARENT_GROUP, value)
    elif tamper == "leaf_sample":
        value = entry.read(entry.PARENT_RESULTS / "request-ledger.json")
        value["requests"][2]["sample"] = "en-medium"
        entry.io.durable(entry.PARENT_RESULTS / "request-ledger.json", value)
    elif tamper == "leaf_payload":
        value = entry.read(entry.PARENT_RESULTS / "payload-03.json")
        value["messages"][1]["content"] = "unbound notes"
        entry.io.durable(entry.PARENT_RESULTS / "payload-03.json", value)
    elif tamper == "leaf_raw":
        value = entry.read(entry.PARENT_RESULTS / "response-03.json")
        value["model"] = "different-provider-model"
        entry.io.durable(entry.PARENT_RESULTS / "response-03.json", value)
    else:
        (entry.CORPUS / "en-long.txt").write_text("wrong source", encoding="utf-8")
    with pytest.raises(RuntimeError):
        entry.freeze()
    assert not entry.RESULTS.exists()


def test_notes_payload_mutation_refuses_long_before_transport(entry, monkeypatch):
    ready(entry)
    original = entry.test_service._staged_messages
    def changed(role, **kw):
        messages = original(role, **kw)
        if role == "points" and kw["notes"]:
            messages[1]["content"] += "unbound note"
        return messages
    monkeypatch.setattr(entry.test_service, "_staged_messages", changed)
    sent = []
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: sent.append(1) or response(entry, kw["json"], len(sent))))
    assert len(sent) == index["posts"] == 4 and index["stopped_on_error"]
    assert entry.read(entry.TRACKER)["status"] == "closed"


@pytest.mark.parametrize("failure", ["raw_model", "trace", "initialization", "interrupt", "atomic_replace"])
def test_failure_keeps_attempts_and_closes(entry, monkeypatch, failure):
    ready(entry)
    sent = []
    if failure == "trace":
        original = entry.durable
        def broken(path, value):
            if Path(path).name.startswith("trace-"):
                raise OSError("diagnostic persistence failed")
            return original(path, value)
        monkeypatch.setattr(entry, "durable", broken)
    elif failure == "initialization":
        monkeypatch.setattr(httpx, "Client", lambda **kw: (_ for _ in ()).throw(RuntimeError("client init failed")))
    elif failure == "atomic_replace":
        original = entry.base.os.replace
        fired = []
        def broken(source, destination):
            if Path(destination) == entry.GROUP and not fired:
                fired.append(1)
                raise OSError("single atomic failure")
            return original(source, destination)
        monkeypatch.setattr(entry.base.os, "replace", broken)
    def post(*a, **kw):
        sent.append(1)
        if failure == "interrupt":
            raise KeyboardInterrupt
        return response(entry, kw["json"], model="different-model" if failure == "raw_model" else None)
    if failure in {"initialization", "interrupt"}:
        with pytest.raises(RuntimeError if failure == "initialization" else KeyboardInterrupt):
            entry.run(**({} if failure == "initialization" else {"transport": SimpleNamespace(post=post)}))
    else:
        assert entry.run(transport=SimpleNamespace(post=post))["stopped_on_error"]
    assert len(sent) <= 1 and entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.verify_results()["stopped_on_error"] is True


def test_external_langsmith_trace_is_disabled_even_with_environment_enabled(entry, monkeypatch):
    ready(entry)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    from langsmith import Client
    monkeypatch.setattr(Client, "create_run", lambda *a, **kw: pytest.fail("External tracing invoked"))
    monkeypatch.setattr(Client, "update_run", lambda *a, **kw: pytest.fail("External tracing invoked"))
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **kw: response(entry, kw["json"])))
    assert index["posts"] == 6 and index["stopped_on_error"] is False


def test_verify_rejects_points_changed_while_overview_stays_bound(entry):
    ready(entry)
    entry.run(transport=SimpleNamespace(post=lambda *a, **kw: response(entry, kw["json"])))
    path = entry.RESULTS / "en-long.json"
    result = entry.read(path)
    result["result"]["key_points"] = ["points never returned by model"]
    entry.io.durable(path, result)
    checksum = entry.io.digest(path.read_bytes())
    index = entry.read(entry.RESULTS / "result-index.json")
    index["samples"][-1]["result_sha256"] = checksum
    entry.io.durable(entry.RESULTS / "result-index.json", index)
    ledger = entry.read(entry.RESULTS / "request-ledger.json")
    for row in ledger["requests"]:
        if row["sample"] == "en-long":
            row["result_sha256"] = checksum
    entry.io.durable(entry.RESULTS / "request-ledger.json", ledger)
    receipt = entry.read(entry.RESULTS / "closed-receipt.json")
    receipt.update(ledger_sha256=entry.io.digest((entry.RESULTS / "request-ledger.json").read_bytes()),
        index_sha256=entry.io.digest((entry.RESULTS / "result-index.json").read_bytes()))
    entry.io.durable(entry.RESULTS / "closed-receipt.json", receipt)
    receipt_sha = entry.io.digest((entry.RESULTS / "closed-receipt.json").read_bytes())
    tracker = entry.read(entry.TRACKER)
    tracker["closed_receipt_sha256"] = receipt_sha
    entry.io.durable(entry.TRACKER, tracker)
    group = entry.read(entry.GROUP)
    group["phases"][-1]["closed_receipt_sha256"] = receipt_sha
    entry.io.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="role|points|raw"):
        entry.verify_results()
