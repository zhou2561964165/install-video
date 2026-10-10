"""Offline budget boundaries for the new normalized evaluation phase."""
import importlib.util
import json
from pathlib import Path

import pytest
import httpx


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-08-grounded-summary-normalized/scripts/evaluate.py"


@pytest.fixture
def entry(tmp_path, monkeypatch):
    assert SCRIPT.exists(), "Retry-aware evidence evaluator is missing"
    spec = importlib.util.spec_from_file_location("normalized_evaluation_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    monkeypatch.setattr(module.base, "PROJECT", tmp_path)
    monkeypatch.setattr(module, "RESULTS", tmp_path)
    monkeypatch.setattr(module, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(module, "CALLER_LOCK", tmp_path / "caller.lock")
    monkeypatch.setattr(module, "GROUP", tmp_path / "group.json")
    module.base.exclusive(module.GROUP, {"work_id": module.WORK_ID, "hard_ceiling": 26,
        "initial_phase_ceiling": 19, "phases": [{"phase": module.PHASE,
        "ledger": str(module.LEDGER), "ceiling": 19}], "status": "frozen"})
    return module


@pytest.mark.parametrize("bad", [True, 19.0, 20, -1])
def test_ledger_rejects_wrong_or_untyped_ceiling(entry, bad):
    entry.base.exclusive(entry.LEDGER, {"phase": entry.PHASE, "ceiling": bad, "requests": []})
    with pytest.raises(RuntimeError):
        entry.validate_ledger()


def test_ledger_rejects_foreign_identity_and_bool_ordinal(entry):
    entry.base.exclusive(entry.LEDGER, {"phase": entry.PHASE, "ceiling": 19,
        "requests": [{"phase": "other", "ordinal": True, "sample": "short", "sample_post": 1}]})
    with pytest.raises(RuntimeError):
        entry.validate_ledger()


def test_group_counts_reserved_attempts_and_refuses_cross_phase_overflow(entry):
    group = entry.read(entry.GROUP)
    extra = entry.RESULTS / "other-ledger.json"
    entry.base.exclusive(extra, {"requests": [{}] * 27})
    group["phases"].append({"phase": "other", "ledger": str(extra), "ceiling": 27})
    entry.base.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError):
        entry.validate_group()


def test_group_rejects_ledger_outside_temporary_project(entry):
    assert entry.PROJECT == entry.base.PROJECT
    group = entry.read(entry.GROUP)
    group["phases"][0]["ledger"] = str(entry.PROJECT.parent / "escaped-ledger.json")
    entry.base.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="ledger path"):
        entry.validate_group()


def test_caller_guard_does_not_remove_an_existing_lock(entry):
    entry.CALLER_LOCK.mkdir()
    with pytest.raises(FileExistsError):
        with entry.base.directory_guard(entry.CALLER_LOCK):
            pass
    assert entry.CALLER_LOCK.exists()


def test_default_plan_does_not_load_runtime_or_env(entry, monkeypatch, capsys):
    monkeypatch.setattr(entry, "load_runtime", lambda: pytest.fail("Default plan read runtime"))
    entry.main([])
    plan = json.loads(capsys.readouterr().out)
    assert plan["network"] is False and plan["expected_posts"] == 13 and plan["ceiling"] == 19


@pytest.fixture
def completed(entry, monkeypatch):
    from app.config import settings
    from app.services import llm_service
    from app.services.summary_facts import FactLimits
    for name, value in {**entry.CONFIG, "llm_model": "offline-model", "llm_provider": "compatible",
        "llm_base_url": "https://offline.invalid/v1", "llm_api_key": "",
        "llm_timeout_seconds": 20}.items():
        monkeypatch.setattr(settings, name, value)
    def runtime():
        entry.base.settings, entry.base.service, entry.base.FactLimits = settings, llm_service, FactLimits
        entry.base.REPORT, entry.base.RESULTS = entry.REPORT, entry.RESULTS
        entry.base.CONFIG, entry.base.MODULES = entry.CONFIG, entry.MODULES
    monkeypatch.setattr(entry, "load_runtime", runtime)
    group = entry.read(entry.GROUP)
    group["phases"] = []
    entry.base.durable(entry.GROUP, group)
    entry.main(["--freeze"])
    original_client = httpx.Client
    facts, compose_repairs, audit_repairs = [], set(), set()
    def respond(request):
        ledger = entry.read(entry.LEDGER)
        row = ledger["requests"][-1]
        assert row["status"] == "reserved", "POST was sent before durable reservation"
        user = entry.read_user(json.loads(request.content))
        sample, stage = row["sample"], row["stage"]
        if stage == "extract":
            if user["source"]["id"] == "part1":
                facts.clear()
            claim = user["source"]["text"].splitlines()[0].split("] ", 1)[1]
            facts.append({"topic": "Source context", "claim": claim, "evidence": [1],
                          "attribution": "source", "importance": "core"})
            output = {"fact_1": facts[-1]}
        elif stage == "compose" and sample == "zh-short" and sample not in compose_repairs:
            compose_repairs.add(sample)
            output = "invalid"
        else:
            candidate = {"summary": [{"text": f["claim"]} for f in facts],
                "key_points": [{"topic": f["topic"], "text": f["claim"]} for f in facts]}
            if stage == "compose":
                output = candidate
            else:
                checks = [{"item_id": prefix + str(n), "supported": True,
                    "qualifiers_preserved": True, "attribution_preserved": True, "scope_preserved": True}
                    for prefix in ("S", "P") for n in range(1, len(facts) + 1)]
                if sample == "zh-short" and sample not in audit_repairs:
                    audit_repairs.add(sample)
                    checks[0]["supported"] = False
                output = {"additional_facts": [], "output": candidate, "checks": checks}
        content = output if isinstance(output, str) else json.dumps(output)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
    monkeypatch.setattr(entry.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(respond)))
    entry.main(["--run"])
    spec = importlib.util.spec_from_file_location("normalized_checker_fixture", SCRIPT.with_name("check_evidence.py"))
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(checker, "entry", entry)
    frozen_runtime = checker.frozen_runtime
    def offline_frozen_runtime(frozen):
        runtime, added = frozen_runtime(frozen)
        runtime.settings.llm_base_url = "https://offline.invalid/v1"
        return runtime, added
    monkeypatch.setattr(checker, "frozen_runtime", offline_frozen_runtime)
    return entry, checker


def test_frozen_replay_binds_all_modules_raw_repairs_trace_and_public_result(completed):
    entry, checker = completed
    result = checker.check_phase()
    assert result["posts"] == 15 and result["evidence_verified"] is True
    assert all(sample["status"] == "completed" for sample in result["samples"])
    assert result["samples"][0]["retry_budget"]["format_used"] == 1
    assert result["samples"][0]["retry_budget"]["semantic_used"] == 1
    assert result["semantic_quality"] == "NOT_EVALUATED"
    with pytest.raises(RuntimeError):
        entry.main(["--run"])


@pytest.mark.parametrize("module", ["normalization", "references", "retry"])
def test_new_frozen_module_tamper_is_rejected_before_execution(completed, module, monkeypatch):
    entry, checker = completed
    path = entry.RESULTS / f"{entry.PHASE}-{module}.py"
    path.write_bytes(path.read_bytes() + b"\n# changed\n")
    monkeypatch.setattr(checker, "frozen_runtime", lambda _: pytest.fail("Unverified snapshot executed"))
    with pytest.raises(RuntimeError, match="module hash"):
        checker.check_phase()


def test_matching_file_hashes_cannot_hide_forged_repair_feedback(completed):
    entry, checker = completed
    ledger = entry.read(entry.LEDGER)
    repair_row = next(row for row in ledger["requests"] if row["recovery"] == "model_format_repair")
    path = entry.RESULTS / "payloads" / f"{repair_row['ordinal']:02d}.json"
    payload = entry.read(path)
    user = entry.read_user(payload)
    user["repair"]["previous_response"] = "forged"
    payload["messages"][1]["content"] = json.dumps(user, ensure_ascii=False)
    entry.base.durable(path, payload)
    repair_row["payload_sha256"] = entry.base.digest(path.read_bytes())
    entry.base.durable(entry.LEDGER, ledger)
    with pytest.raises(RuntimeError, match="Recorded POST differs"):
        checker.check_phase()


def test_durable_reservation_failure_never_sends_a_post(entry, monkeypatch):
    monkeypatch.setattr(entry, "verify", lambda _: None)
    calls = []
    class NoSend:
        def post(self, *args, **kwargs):
            calls.append(kwargs)
            pytest.fail("POST happened before durable reservation")
    frozen = {"model": "fixture", "options": {}, "stage_prompts": {"extract": "protocol"},
        "stage_max_output_tokens": {"extract": 2}, "samples": [{"id": "short", "maximum_posts": 5}]}
    client = entry.BudgetClient(NoSend(), frozen)
    client.sample = "short"
    client.latest = {"paid_calls": 1, "stages": [{"stage": "extract", "attempt": 1,
        "status": "requesting", "paid_attempt": True, "recovery": "none"}]}
    def denied(*args):
        raise OSError("Durable reservation unavailable")
    monkeypatch.setattr(entry.base, "durable", denied)
    payload = {"model": "fixture", "temperature": 0.2, "max_tokens": 2,
        "messages": [{"role": "system", "content": "protocol"}, {"role": "user", "content": "{}"}]}
    with pytest.raises(OSError):
        client.post("https://offline.invalid", headers={}, json=payload)
    assert calls == [] and not entry.CALLER_LOCK.exists()


def test_post_directly_cannot_bypass_a_shared_caller_lock(entry, monkeypatch):
    entry.CALLER_LOCK.mkdir()
    monkeypatch.setattr(entry, "verify", lambda _: pytest.fail("Busy caller lock was bypassed"))
    with pytest.raises(FileExistsError):
        entry.BudgetClient(None, {}).post("https://offline.invalid", headers={}, json={})
