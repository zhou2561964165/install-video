"""Isolated Responses continuation; snapshot parents, synthetic transport only."""
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-10-schema-pro-summary-live/scripts/evaluate.py"
FROZEN_RESULTS = SCRIPT.parents[1] / "results"


def isolated_parents(module, tmp_path, monkeypatch):
    """Relocate historical evidence copies without reading ignored .planning.

    Only copied metadata is rebound. Published snapshots/raw remain byte exact;
    the runner still checks closed counts, parent hashes and every raw binding.
    """
    read_bytes, read_text = Path.read_bytes, Path.read_text
    ignored = (ROOT / ".planning").resolve()
    def guarded_bytes(path):
        assert not path.resolve().is_relative_to(ignored), "Read ignored local budget"
        return read_bytes(path)
    def guarded_text(path, *args, **kwargs):
        assert not path.resolve().is_relative_to(ignored), "Read ignored local budget"
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_bytes", guarded_bytes)
    monkeypatch.setattr(Path, "read_text", guarded_text)
    published = module.read(FROZEN_RESULTS / "provenance.json")
    original_assets = module.asset_paths()
    assets = []
    for source in original_assets:
        name = source.relative_to(ROOT).as_posix()
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name.startswith(".planning/"):
            record = published["snapshots"][name]
            snapshot = (FROZEN_RESULTS / record["file"]).resolve()
            assert snapshot.is_relative_to((FROZEN_RESULTS / "snapshots").resolve())
            raw = snapshot.read_bytes()
            assert module.io.digest(raw) == record["sha256"]
            target.write_bytes(raw)
        else:
            shutil.copyfile(source, target)
        assets.append(target)

    # Path identities in closed receipts refer to the original host. Rebind
    # copies from phase one upward, retaining each phase's counts and guards.
    for name in ("PROJECT", "CORPUS", "PARENT2_REPORT", "PARENT2_RESULTS",
                 "PARENT2_RUNNER", "PARENT2_GROUP", "PARENT2_TRACKER"):
        original = getattr(module, name)
        monkeypatch.setattr(module, name, tmp_path / original.relative_to(ROOT))
    for name in ("PROJECT", "CORPUS", "PARENT_REPORT", "PARENT_RESULTS",
                 "PARENT_RUNNER", "PARENT_GROUP", "PARENT_TRACKER"):
        original = getattr(module.prior, name)
        monkeypatch.setattr(module.prior, name, tmp_path / original.relative_to(ROOT))

    def write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    first = module.read(module.prior.PARENT_GROUP)
    first_tracker = module.read(module.prior.PARENT_TRACKER)
    first_phase = first["phases"][0]
    first_phase.update(ledger=str(module.prior.PARENT_RESULTS / "request-ledger.json"),
                       tracker=str(module.prior.PARENT_TRACKER))
    first_tracker["ledger"] = first_phase["ledger"]
    write(module.prior.PARENT_TRACKER, first_tracker)
    write(module.prior.PARENT_GROUP, first)
    first_state = module.prior.parent_state()

    second = module.read(module.PARENT2_GROUP)
    second_tracker = module.read(module.PARENT2_TRACKER)
    provenance_path = module.PARENT2_RESULTS / "provenance.json"
    provenance = module.read(provenance_path)
    provenance.update(parent_sha256=first_state["parent_sha256"],
                      parent_phase=first_state["parent_phase"])
    write(provenance_path, provenance)
    provenance_sha = module.io.digest(provenance_path.read_bytes())
    receipt_path = module.PARENT2_RESULTS / "closed-receipt.json"
    receipt = module.read(receipt_path)
    receipt["provenance_sha256"] = provenance_sha
    write(receipt_path, receipt)
    receipt_sha = module.io.digest(receipt_path.read_bytes())
    second["phases"][0] = first_phase
    second_phase = second["phases"][1]
    second_phase.update(ledger=str(module.PARENT2_RESULTS / "request-ledger.json"),
                        tracker=str(module.PARENT2_TRACKER),
                        provenance_sha256=provenance_sha,
                        closed_receipt_sha256=receipt_sha)
    second_tracker.update(ledger=second_phase["ledger"],
                          provenance_sha256=provenance_sha,
                          closed_receipt_sha256=receipt_sha)
    second.update(parent_snapshot=str(module.prior.PARENT_GROUP),
                  parent_sha256=first_state["parent_sha256"])
    write(module.PARENT2_TRACKER, second_tracker)
    write(module.PARENT2_GROUP, second)
    # Execute the original complete validator after relocation; no checks are
    # replaced by a canned parent state or bypassed by fixture preparation.
    module.parent_state()
    monkeypatch.setattr(module, "asset_paths", lambda: assets)



@pytest.fixture
def entry(tmp_path, monkeypatch):
    assert SCRIPT.exists(), "Schema Pro runner missing"
    spec = importlib.util.spec_from_file_location("schema_pro_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    isolated_parents(module, tmp_path, monkeypatch)
    report = tmp_path / "new-phase"
    for key, value in {"REPORT": report, "RESULTS": report / "results", "GROUP": tmp_path / "group.json",
                       "TRACKER": tmp_path / "phase.json", "SHARED_LOCK": tmp_path / "caller.lock"}.items():
        monkeypatch.setattr(module, key, value)
    original_context = module.base_context
    def temporary_owned_paths():
        original_context()
        module.stage.base.PROJECT = tmp_path
    monkeypatch.setattr(module, "base_context", temporary_owned_paths)
    parent = module.read(module.PARENT2_GROUP)
    group = parent | {"status": "active", "hard_ceiling": 17,
        "parent_snapshot": str(module.PARENT2_GROUP), "parent_sha256": module.io.digest(module.PARENT2_GROUP.read_bytes()),
        "parent_posts": 11, "budget_adjustment": {"from": 12, "to": 17}}
    module.io.exclusive(module.GROUP, group)
    from app.services import llm_service as service
    settings = SimpleNamespace(**module.CONFIG, llm_provider="deepseek", llm_api_key="",
        llm_base_url="https://offline.invalid/v1", llm_timeout_seconds=1, llm_summary_max_point_chars=240,
        llm_summary_notes_language="output", llm_summary_source_context_mode="boundary")
    # Preserve the exact source preparation owned by the immutable first
    # parent's planner; today's adjacent-copy policy has different source parts.
    monkeypatch.setattr(service, "_summary_input", module.prior.base.cleaned)
    monkeypatch.setattr(service, "settings", settings)
    monkeypatch.setattr(module, "runtime", lambda: (settings, service, service._endpoint(responses=True)))
    module.test_service, module.test_settings = service, settings
    module.parent_bytes = {p: p.read_bytes() for p in module.parent_assets()}
    return module


def ready(entry):
    entry.freeze()
    entry.check()


def response(payload, n=1, *, status="completed", model=None, invalid=False):
    points = payload["text"]["format"]["name"].endswith("points")
    content = {"key_points": [f"Condition {n}."]} if points else {"summary": f"Overview {n}."}
    if invalid:
        content["unexpected"] = "invalid"
    return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid/v1/responses"), json={
        "object": "response", "status": status, "model": model or "deepseek-v4-pro",
        "output": [{"type": "reasoning", "secret": "DO-NOT-SAVE"},
            {"type": "message", "role": "assistant", "status": "completed", "content": [
                {"type": "output_text", "text": json.dumps(content), "secret": "DO-NOT-SAVE"}]}],
        "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3,
            "input_tokens_details": {"cached_tokens": 1, "secret": "DO-NOT-SAVE"}, "secret": "DO-NOT-SAVE"},
        "headers": "DO-NOT-SAVE", "error": None, "incomplete_details": None})


def test_six_responses_reserve_parent_eleven_and_bind_both_roles(entry, monkeypatch):
    monkeypatch.setattr(entry, "runtime", entry.runtime)
    assert entry.plan()["parent_posts"] == 11
    ready(entry)
    sent = []
    def post(url, **kw):
        assert url.endswith("/responses") and "messages" not in kw["json"]
        assert kw["json"]["reasoning"] == {"effort": "none"}
        sent.append(entry.read(entry.GROUP)["reserved_posts"])
        assert sent[-1] == 11 + len(sent)
        return response(kw["json"], len(sent))
    index = entry.run(transport=SimpleNamespace(post=post))
    assert sent == list(range(12, 18)) and index["posts"] == 6 and not index["stopped_on_error"]
    assert all(p.read_bytes() == raw for p, raw in entry.parent_bytes.items())
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Offline verify read runtime"))
    verified = entry.verify_results()
    assert verified["work_posts"] == 17 and verified["format_posts"] == 0
    for i, sid in enumerate(entry.SAMPLES):
        result = entry.read(entry.RESULTS / f"{sid}.json")["result"]
        assert result["key_points"] == [f"Condition {i * 2 + 1}."]
        assert result["summary"] == f"Overview {i * 2 + 2}."
    raw = entry.read(entry.RESULTS / "response-01.json")
    assert raw["object"] == "response" and raw["status"] == "completed"
    assert json.loads(raw["content"]) == {"key_points": ["Condition 1."]}
    assert raw["usage"] == {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3,
        "input_tokens_details": {"cached_tokens": 1}}
    assert "DO-NOT-SAVE" not in (entry.RESULTS / "response-01.json").read_text(encoding="utf8")
    with pytest.raises(RuntimeError, match="reopen|started"):
        entry.run(transport=SimpleNamespace(post=post))


@pytest.mark.parametrize("failure", ["incomplete", "in_progress", "failed", "model", "format", "interrupt", "initialization"])
def test_terminal_attempt_never_repairs_or_refunds(entry, monkeypatch, failure):
    ready(entry)
    sent = []
    def post(url, **kw):
        sent.append(1)
        if failure == "interrupt":
            raise KeyboardInterrupt
        return response(kw["json"], status=failure if failure in {"incomplete", "in_progress", "failed"} else "completed",
            model="wrong-model" if failure == "model" else None, invalid=failure == "format")
    if failure == "initialization":
        monkeypatch.setattr(httpx, "Client", lambda **kw: (_ for _ in ()).throw(RuntimeError("init")))
    if failure in {"interrupt", "initialization"}:
        with pytest.raises(KeyboardInterrupt if failure == "interrupt" else RuntimeError):
            entry.run(**({} if failure == "initialization" else {"transport": SimpleNamespace(post=post)}))
    else:
        assert entry.run(transport=SimpleNamespace(post=post))["stopped_on_error"]
    assert len(sent) <= 1
    assert entry.read(entry.GROUP)["reserved_posts"] == 11 + len(sent)
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.verify_results()["stopped_on_error"]


@pytest.mark.parametrize("drift", ["model", "endpoint"])
def test_runtime_drift_refuses_transport(entry, drift):
    ready(entry)
    setattr(entry.test_settings, "llm_model" if drift == "model" else "llm_base_url", "wrong-model" if drift == "model" else "https://different.invalid")
    with pytest.raises(RuntimeError, match="drift"):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Drift spent POST")))
    assert entry.verify_results()["work_posts"] == 11


def test_parent_receipt_drift_refused_before_allocation(entry, monkeypatch):
    original = entry.parent_state
    def changed(*args, **kwargs):
        parent = original(*args, **kwargs)
        parent["parent_sha256"] = "wrong"
        return parent
    monkeypatch.setattr(entry, "parent_state", changed)
    with pytest.raises(RuntimeError):
        entry.freeze()
    assert not entry.RESULTS.exists()


@pytest.mark.parametrize("drift", ["receipt", "ledger", "raw", "first_leaf",
                                  "first_budget", "second_budget", "first_tracker", "second_tracker"])
def test_readonly_parent_evidence_drift_is_rejected(entry, drift):
    paths = {"receipt": entry.PARENT2_RESULTS / "closed-receipt.json",
        "ledger": entry.PARENT2_RESULTS / "request-ledger.json",
        "raw": entry.PARENT2_RESULTS / "response-05.json",
        "first_leaf": entry.prior.PARENT_RESULTS / "response-03.json",
        "first_budget": entry.prior.PARENT_GROUP, "second_budget": entry.PARENT2_GROUP,
        "first_tracker": entry.prior.PARENT_TRACKER, "second_tracker": entry.PARENT2_TRACKER}
    target = paths[drift]
    def reader(path):
        raw = path.read_bytes()
        if path == target:
            value = json.loads(raw)
            if drift.endswith("budget") or drift.endswith("tracker"):
                value["status"] = "active"
            else:
                value["tampered"] = True
            return json.dumps(value).encode("utf8")
        return raw
    with pytest.raises(RuntimeError, match="Parent"):
        entry.parent_state(reader=reader)
    assert not entry.RESULTS.exists()


def test_verify_rejects_points_changed_even_with_rebound_outer_hashes(entry):
    ready(entry)
    entry.run(transport=SimpleNamespace(post=lambda *a, **kw: response(kw["json"])))
    path = entry.RESULTS / "en-long.json"
    result = entry.read(path)
    result["result"]["key_points"] = ["Never returned by accepted points role."]
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
    tracker, group = entry.read(entry.TRACKER), entry.read(entry.GROUP)
    tracker["closed_receipt_sha256"] = group["phases"][-1]["closed_receipt_sha256"] = receipt_sha
    entry.io.durable(entry.TRACKER, tracker)
    entry.io.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="points|overview|raw"):
        entry.verify_results()
