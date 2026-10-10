"""Offline regression boundaries for the independent compact-quality phase."""
import importlib.util
import json
from pathlib import Path

import pytest
import httpx


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-08-summary-quality-final/scripts/evaluate.py"


@pytest.fixture
def entry(tmp_path, monkeypatch):
    assert SCRIPT.exists(), "Independent quality evaluator is missing"
    spec = importlib.util.spec_from_file_location("quality_evaluation_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    monkeypatch.setattr(module.base, "PROJECT", tmp_path)
    monkeypatch.setattr(module, "RESULTS", tmp_path)
    monkeypatch.setattr(module, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(module, "CALLER_LOCK", tmp_path / "caller.lock")
    monkeypatch.setattr(module, "GROUP", tmp_path / "group.json")
    module.base.exclusive(module.GROUP, {"work_id": module.WORK_ID, "hard_ceiling": 26,
        "initial_phase_ceiling": 19, "phases": [], "status": "investigating"})
    return module


def ledger(phase, count, ceiling):
    return {"phase": phase, "ceiling": ceiling, "requests": [
        {"phase": phase, "ordinal": index, "sample": "sample", "sample_post": index,
         "stage": "extract", "attempt": 1, "recovery": "none", "status": "reserved"}
        for index in range(1, count + 1)]}


def test_default_plan_has_eight_modules_and_never_loads_env(entry, monkeypatch, capsys):
    monkeypatch.setattr(entry, "load_runtime", lambda: pytest.fail("Default plan loaded user runtime"))
    entry.main([])
    plan = json.loads(capsys.readouterr().out)
    assert plan["network"] is False and plan["expected_posts"] == 13 and plan["ceiling"] == 19
    assert plan["config"]["llm_summary_quality_contract"] == "compact"
    assert set(entry.MODULES) == {"service", "config", "facts", "normalization", "references", "retry", "audit_contract", "quality"}


def test_exact_work_ceiling_is_valid_for_read_only_close(entry):
    group = entry.read(entry.GROUP)
    other = entry.RESULTS / "other.json"
    entry.base.exclusive(entry.LEDGER, ledger(entry.PHASE, 19, 19))
    entry.base.exclusive(other, ledger("followup", 7, 7))
    group["phases"] = [{"phase": entry.PHASE, "ceiling": 19, "ledger": str(entry.LEDGER)},
        {"phase": "followup", "ceiling": 7, "ledger": str(other)}]
    entry.base.durable(entry.GROUP, group)
    assert entry.validate_group()[1] == 26


def test_work_budget_overflow_is_invalid_even_for_read_only_check(entry):
    group = entry.read(entry.GROUP)
    other = entry.RESULTS / "other.json"
    entry.base.exclusive(entry.LEDGER, ledger(entry.PHASE, 19, 19))
    entry.base.exclusive(other, ledger("followup", 8, 8))
    group["phases"] = [{"phase": entry.PHASE, "ceiling": 19, "ledger": str(entry.LEDGER)},
        {"phase": "followup", "ceiling": 8, "ledger": str(other)}]
    entry.base.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="exceeded"):
        entry.validate_group()


def test_group_rejects_ledger_outside_temporary_project(entry):
    assert entry.PROJECT == entry.base.PROJECT
    group = entry.read(entry.GROUP)
    group["phases"] = [{"phase": entry.PHASE, "ceiling": 19,
                        "ledger": str(entry.PROJECT.parent / "escaped-ledger.json")}]
    entry.base.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="ledger path"):
        entry.validate_group()


def test_busy_shared_caller_never_reaches_snapshot(entry, monkeypatch):
    entry.CALLER_LOCK.mkdir()
    monkeypatch.setattr(entry, "verify", lambda _: pytest.fail("Shared caller lock bypassed"))
    with pytest.raises(FileExistsError):
        entry.BudgetClient(None, {}).post("https://offline.invalid", headers={}, json={})


def test_caller_locked_boolean_cannot_bypass_another_session(entry, monkeypatch):
    entry.CALLER_LOCK.mkdir()
    monkeypatch.setattr(entry, "verify", lambda _: pytest.fail("Foreign caller reached snapshot"))
    with pytest.raises(RuntimeError, match="session"):
        entry.BudgetClient(None, {}, caller_locked=True).post("https://offline.invalid", headers={}, json={})


@pytest.fixture
def guarded(entry, monkeypatch):
    from app.services import llm_service
    monkeypatch.setattr(entry.base, "service", llm_service)
    monkeypatch.setattr(entry, "verify", lambda _: None)
    group = entry.read(entry.GROUP)
    group["phases"] = [{"phase": entry.PHASE, "ledger": str(entry.LEDGER), "ceiling": 19}]
    entry.base.durable(entry.GROUP, group)
    sent = []

    class Transport:
        def post(self, url, *, headers, json):
            assert entry.read(entry.LEDGER)["requests"][-1]["status"] == "reserved"
            sent.append(json)
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "invalid"}}]})

    frozen = {"model": "offline-model", "endpoint": "https://offline.invalid/v1/chat/completions",
        "options": {}, "stage_prompts": {"extract": "protocol"}, "repair_prompts": {"extract": "repair"},
        "stage_max_output_tokens": {"extract": 2}, "samples": [{"id": "sample", "maximum_posts": 5}]}
    client = entry.BudgetClient(Transport(), frozen)
    client.sample = "sample"
    client.latest = {"paid_calls": 1, "stages": [{"stage": "extract", "attempt": 1,
        "status": "requesting", "paid_attempt": True, "recovery": "none"}]}
    payload = {"model": "offline-model", "temperature": 0.2, "max_tokens": 2,
        "messages": [{"role": "system", "content": "protocol"}, {"role": "user", "content": "{}"}]}
    return entry, client, payload, sent


@pytest.mark.parametrize("where", ["paid_calls", "attempt"])
def test_bool_attempt_metadata_cannot_send_a_post(guarded, where):
    entry, client, payload, sent = guarded
    if where == "paid_calls":
        client.latest[where] = True
    else:
        client.latest["stages"][-1][where] = True
    with pytest.raises(RuntimeError):
        client.post(client.frozen["endpoint"], headers={}, json=payload)
    assert sent == [] and entry.validate_ledger()["requests"] == []


def test_wrong_destination_cannot_use_frozen_payload(guarded):
    entry, client, payload, sent = guarded
    with pytest.raises(RuntimeError):
        client.post("https://other.invalid/v1/chat/completions", headers={}, json=payload)
    assert sent == []


def test_fsync_reservation_failure_does_not_send(guarded, monkeypatch):
    entry, client, payload, sent = guarded
    monkeypatch.setattr(entry.base, "durable", lambda *args: (_ for _ in ()).throw(OSError("fsync unavailable")))
    with pytest.raises(OSError):
        client.post(client.frozen["endpoint"], headers={}, json=payload)
    assert sent == []


def test_exact_ceiling_refuses_post_but_stays_readable(guarded):
    entry, client, payload, sent = guarded
    group = entry.read(entry.GROUP)
    other = entry.RESULTS / "other.json"
    entry.base.exclusive(other, ledger("previous", 26, 26))
    group["phases"].append({"phase": "previous", "ledger": str(other), "ceiling": 26})
    entry.base.durable(entry.GROUP, group)
    assert entry.validate_group()[1] == 26
    with pytest.raises(RuntimeError, match="ceiling"):
        client.post(client.frozen["endpoint"], headers={}, json=payload)
    assert sent == [] and entry.validate_group()[1] == 26


@pytest.mark.parametrize("field", ["ordinal", "sample_post", "attempt", "ceiling"])
def test_ledger_rejects_boolean_counters(entry, field):
    record = ledger(entry.PHASE, 1, 19)
    target = record if field == "ceiling" else record["requests"][0]
    target[field] = True
    entry.base.exclusive(entry.LEDGER, record)
    with pytest.raises(RuntimeError):
        entry.validate_ledger()


@pytest.fixture
def frozen_entry(entry, monkeypatch):
    from app.config import settings
    from app.services import llm_service
    from app.services.summary_facts import FactLimits
    for name, value in {**entry.CONFIG, "llm_model": "offline-model", "llm_provider": "compatible",
        "llm_base_url": "https://offline.invalid/v1", "llm_api_key": "",
        "llm_timeout_seconds": 20}.items():
        monkeypatch.setattr(settings, name, value, raising=False)

    def runtime():
        entry.base.settings, entry.base.service, entry.base.FactLimits = settings, llm_service, FactLimits
        entry.base.REPORT, entry.base.RESULTS = entry.REPORT, entry.RESULTS
        entry.base.CONFIG, entry.base.MODULES = entry.CONFIG, entry.MODULES

    monkeypatch.setattr(entry, "load_runtime", runtime)
    entry.main(["--freeze"])
    return entry


@pytest.fixture
def completed(frozen_entry, monkeypatch, request):
    entry = frozen_entry
    profile = getattr(request, "param", "mixed")
    original_client = httpx.Client
    facts, compose_repaired, audit_repaired = [], set(), set()

    def respond(request):
        row = entry.read(entry.LEDGER)["requests"][-1]
        assert row["status"] == "reserved", "POST preceded persistent reservation"
        user = entry.read_user(json.loads(request.content))
        sample, stage = row["sample"], row["stage"]
        if stage == "extract":
            if user["source"]["id"] == "part1":
                facts.clear()
            claim = user["source"]["text"].splitlines()[0].split("] ", 1)[1]
            facts.append({"topic": "Section " + str(len(facts) + 1), "claim": claim, "evidence": [1],
                "attribution": "source", "importance": "core"})
            output = {"fact_1": facts[-1]}
        elif (stage == "compose" and profile != "normal" and (profile == "worst" or sample == "zh-short")
                and sample not in compose_repaired):
            compose_repaired.add(sample)
            output = "invalid"
        elif stage == "compose":
            output = {"summary": " ".join(f["claim"] for f in facts),
                "key_points": [{"topic": f["topic"], "text": f["claim"], "fact_ids": [f"F{i}_1"]}
                    for i, f in enumerate(facts, 1)],
                "theme_plan": {f"theme_{i}": {"topic": f["topic"], "principle": f["claim"],
                    "conditions": [], "consequences": [], "fact_ids": [f"F{i}_1"]}
                    for i, f in enumerate(facts, 1)}}
        else:
            flags = {"supported": True, "qualifiers_preserved": True,
                "attribution_preserved": True, "scope_preserved": True}
            output = {"additional_facts": [], "output": {
                "summary": {"text": " ".join(f["claim"] for f in facts), "assertions": flags},
                **{f"point_{i}": {"topic": f["topic"], "text": f["claim"],
                    "assertions": flags, "fact_ids": [f"F{i}_1"]} for i, f in enumerate(facts, 1)}}}
            if (profile != "normal" and (profile == "worst" or sample == "zh-short")
                    and sample not in audit_repaired):
                audit_repaired.add(sample)
                output["output"]["summary"]["assertions"] = {**flags, "supported": False}
        content = output if isinstance(output, str) else json.dumps(output)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})

    monkeypatch.setattr(entry.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(respond)))
    entry.main(["--run"])
    spec = importlib.util.spec_from_file_location("quality_checker_fixture", SCRIPT.with_name("check_evidence.py"))
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(checker, "entry", entry)
    return entry, checker


def test_all_three_sources_compact_repairs_replay_exactly(completed):
    entry, checker = completed
    result = checker.check_phase()
    assert result["posts"] == 15 and len(result["samples"]) == 3
    assert result["evidence_verified"] is True and result["semantic_quality"] == "NOT_EVALUATED"
    assert all(row["status"] == "completed" for row in result["samples"])
    assert result["samples"][0]["retry_budget"]["format_used"] == 1
    assert result["samples"][0]["retry_budget"]["semantic_used"] == 1
    trace = entry.read(entry.RESULTS / f"{entry.PHASE}-zh-short-trace.json")["events"][-1]
    assert trace["audit_protocol"] == "compact" and trace["audit_quality"]["issues"] == []
    frozen = entry.read(entry.RESULTS / f"{entry.PHASE}-provenance.json")
    runtime, added = checker.frozen_runtime(frozen)
    try:
        assert runtime.parse_audit_contract.__module__.startswith("quality_frozen_")
        assert runtime.inspect_quality.__module__.startswith("quality_frozen_")
        assert issubclass(runtime.AuditContractError, runtime.FactValidationError)
    finally:
        import sys
        for name in reversed(added):
            sys.modules.pop(name, None)
    with pytest.raises(RuntimeError):
        entry.main(["--run"])


@pytest.mark.parametrize("completed,posts", [("normal", 13), ("worst", 19)], indirect=["completed"])
def test_three_source_normal_and_worst_ceiling_are_closed_and_replayable(completed, posts):
    entry, checker = completed
    result = checker.check_phase()
    assert result["posts"] == posts and len(result["samples"]) == 3
    assert all(row["status"] == "completed" for row in result["samples"])
    assert entry.read(entry.GROUP)["status"] == "closed"
    assert entry.validate_group()[1] == posts


@pytest.mark.parametrize("field", ["fact_limits", "stage_max_output_tokens", "stage_prompts", "repair_prompts", "options", "endpoint"])
def test_forged_derived_freeze_metadata_is_rejected(completed, field):
    entry, checker = completed
    path = entry.RESULTS / f"{entry.PHASE}-provenance.json"
    frozen = entry.read(path)
    if field == "fact_limits":
        frozen[field]["max_summary_chars"] = 801
    elif field == "stage_max_output_tokens":
        frozen[field]["extract"] = True
    elif field in {"stage_prompts", "repair_prompts"}:
        frozen[field]["audit"] = "forged guidance"
    elif field == "options":
        frozen[field] = {"response_format": {"type": "text"}}
    else:
        frozen[field] = "https://foreign.invalid/v1/chat/completions"
    entry.base.durable(path, frozen)
    with pytest.raises(RuntimeError, match="metadata"):
        checker.check_phase()


def test_rubric_is_a_byte_exact_copy_of_the_original(entry):
    assert (entry.REPORT / "rubric.json").read_bytes() == entry.ORIGINAL_RUBRIC.read_bytes()


def test_headers_and_api_secret_are_never_persisted(guarded):
    entry, client, payload, sent = guarded
    client.post(client.frozen["endpoint"], headers={"Authorization": "Bearer offline-sentinel-secret"}, json=payload)
    assert len(sent) == 1
    assert all("offline-sentinel-secret" not in path.read_text(encoding="utf-8")
               for path in entry.RESULTS.rglob("*.json"))


@pytest.mark.parametrize("reason", ["previous_response", "failed_items", "terminal_category"])
def test_guard_refuses_forged_or_terminal_repair_before_second_post(guarded, reason):
    entry, client, payload, sent = guarded
    client.post(client.frozen["endpoint"], headers={}, json=payload)
    previous = client.latest["stages"][0]
    previous.update(status="failed", error_category="format", reason="invalid_json", failed_items=[])
    client.latest["paid_calls"] = 2
    client.latest["stages"].append({"stage": "extract", "attempt": 2, "status": "requesting",
        "paid_attempt": True, "recovery": "model_format_repair"})
    repair = {"category": "format", "reason": "invalid_json", "failed_items": [], "previous_response": "invalid"}
    if reason == "terminal_category":
        previous["error_category"] = "source"
        repair["category"] = "source"
    elif reason == "previous_response":
        repair[reason] = "forged"
    else:
        repair[reason] = ["invented"]
    payload["messages"] = [{"role": "system", "content": "repair"},
        {"role": "user", "content": json.dumps({"repair": repair})}]
    with pytest.raises(RuntimeError):
        client.post(client.frozen["endpoint"], headers={}, json=payload)
    assert len(sent) == len(entry.validate_ledger()["requests"]) == 1


def test_runtime_configuration_failure_after_first_post_does_not_retry(frozen_entry, monkeypatch):
    entry = frozen_entry
    original_client = httpx.Client
    sent = []

    def respond(request):
        sent.append(request)
        monkeypatch.setattr(entry.base.settings, "llm_base_url", "")
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "invalid"}}]})

    monkeypatch.setattr(entry.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(respond)))
    entry.main(["--run"])
    assert len(sent) == len(entry.validate_ledger()["requests"]) == 1
    trace = entry.read(entry.RESULTS / f"{entry.PHASE}-zh-short-trace.json")["events"][-1]
    assert trace["error_category"] == "config" and trace["retry_budget"]["used"] == 0
    assert trace["stages"][-1]["status"] == "blocked" and trace["stages"][-1]["paid_attempt"] is False
    assert len(entry.read(entry.RESULTS / f"{entry.PHASE}-index.json")["sample_results"]) == 1


def test_source_change_after_freeze_is_refused_before_send(frozen_entry, monkeypatch):
    entry = frozen_entry
    frozen = entry.read(entry.RESULTS / f"{entry.PHASE}-provenance.json")
    current = entry.snapshot()
    current["samples"][0]["sha256"] = "changed"
    monkeypatch.setattr(entry, "snapshot", lambda: current)
    with pytest.raises(RuntimeError, match="changed"):
        entry.verify(frozen)


@pytest.mark.parametrize("module", ["service", "config", "facts", "normalization", "references", "retry", "audit_contract", "quality"])
def test_every_frozen_module_hash_is_checked_before_execution(completed, module, monkeypatch):
    entry, checker = completed
    path = entry.RESULTS / f"{entry.PHASE}-{module}.py"
    path.write_bytes(path.read_bytes() + b"\n# tampered\n")
    monkeypatch.setattr(checker, "frozen_runtime", lambda _: pytest.fail("Unverified module executed"))
    with pytest.raises(RuntimeError, match="module hash"):
        checker.check_phase()


def test_self_consistent_hashes_cannot_hide_forged_repair_feedback(completed):
    entry, checker = completed
    record = entry.read(entry.LEDGER)
    row = next(r for r in record["requests"] if r["recovery"] == "model_format_repair")
    path = entry.RESULTS / "payloads" / f"{row['ordinal']:02d}.json"
    payload = entry.read(path)
    user = entry.read_user(payload)
    user["repair"]["previous_response"] = "forged"
    payload["messages"][1]["content"] = json.dumps(user)
    entry.base.durable(path, payload)
    row["payload_sha256"] = entry.base.digest(path.read_bytes())
    entry.base.durable(entry.LEDGER, record)
    with pytest.raises(RuntimeError, match="Recorded POST differs"):
        checker.check_phase()


@pytest.mark.parametrize("target", ["public", "trace"])
def test_foreign_phase_metadata_is_not_verified_even_with_updated_hashes(completed, target):
    entry, checker = completed
    index_path = entry.RESULTS / f"{entry.PHASE}-index.json"
    index = entry.read(index_path)
    row = index["sample_results"][0]
    public_path = entry.RESULTS / row["file"]
    public = entry.read(public_path)
    if target == "public":
        public["phase"] = "foreign"
    else:
        path = entry.RESULTS / f"{entry.PHASE}-{row['id']}-trace.json"
        trace = entry.read(path)
        trace["phase"] = "foreign"
        entry.base.durable(path, trace)
        public["trace_sha256"] = entry.base.digest(path.read_bytes())
    entry.base.durable(public_path, public)
    row["sha256"] = entry.base.digest(public_path.read_bytes())
    entry.base.durable(index_path, index)
    with pytest.raises(RuntimeError, match="identity"):
        checker.check_phase()


@pytest.mark.parametrize("kind,category,posts", [
    ("source", "source", 1), ("network", "network", 1), ("provider", "provider", 1),
    ("invalid_http_json", "provider", 1), ("adapter", "provider", 1),
    ("capacity", "capacity", 1), ("format", "format", 2),
])
def test_terminal_failure_keeps_raw_and_stops_following_samples(frozen_entry, monkeypatch, kind, category, posts):
    entry = frozen_entry
    original_client = httpx.Client
    sent = []

    def respond(request):
        sent.append(request)
        if kind == "network":
            raise httpx.ConnectError("offline")
        if kind == "provider":
            return httpx.Response(503, json={})
        if kind == "invalid_http_json":
            return httpx.Response(200, text="Not a JSON provider envelope")
        user = entry.read_user(json.loads(request.content))
        line = user["source"]["text"].splitlines()[0].split("] ", 1)[1]
        output = "invalid"
        finish = "stop"
        if kind == "source":
            output = json.dumps({"fact_1": {"topic": "Fixture", "claim": line,
                "evidence": [1], "attribution": "source", "importance": "core", "quote": "invented"}})
        elif kind == "adapter":
            finish = 1
        elif kind == "capacity":
            output = "invalid" + "x" * 100001
        return httpx.Response(200, json={"choices": [{"finish_reason": finish, "message": {"content": output}}]})

    monkeypatch.setattr(entry.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(respond)))
    entry.main(["--run"])
    assert len(sent) == posts
    index = entry.read(entry.RESULTS / f"{entry.PHASE}-index.json")
    assert len(index["sample_results"]) == 1
    trace = entry.read(entry.RESULTS / f"{entry.PHASE}-zh-short-trace.json")["events"][-1]
    assert trace["status"] == "failed" and trace["error_category"] == category
    assert trace["retry_budget"]["used"] == (1 if kind == "format" else 0)
    if kind == "provider":
        row = entry.validate_ledger()["requests"][0]
        assert row["status"] == "http_error" and row["http_status"] == 503 and row["usage"] is None
    spec = importlib.util.spec_from_file_location("quality_failed_checker", SCRIPT.with_name("check_evidence.py"))
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(checker, "entry", entry)
    result = checker.check_phase()
    assert result["posts"] == posts and result["samples"][0]["status"] == "failed"


def test_missing_diagnostic_trace_cannot_be_saved_as_success(frozen_entry, monkeypatch):
    entry = frozen_entry
    from app.services.llm_service import LLMSummaryResult
    monkeypatch.setattr(entry.base.service, "summarize_text", lambda *args, **kwargs:
        LLMSummaryResult("Invented successful result", ["Invented point"], "compatible", "offline-model"))
    entry.main(["--run"])
    public = entry.read(entry.RESULTS / f"{entry.PHASE}-zh-short.json")
    assert "result" not in public and public["error_type"] == "RuntimeError"
    assert len(entry.read(entry.RESULTS / f"{entry.PHASE}-index.json")["sample_results"]) == 1
    assert entry.validate_ledger()["requests"] == []


def test_response_write_failure_preserves_reserved_post_and_stops(frozen_entry, monkeypatch):
    entry = frozen_entry
    original_client, original_write = httpx.Client, entry.base.exclusive
    sent = []

    def respond(request):
        sent.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "invalid"}}]})

    def exclusive(path, value):
        if path.parent.name == "responses":
            raise OSError("Response storage unavailable")
        return original_write(path, value)

    monkeypatch.setattr(entry.base, "exclusive", exclusive)
    monkeypatch.setattr(entry.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(respond)))
    entry.main(["--run"])
    record = entry.validate_ledger()
    assert len(sent) == len(record["requests"]) == 1
    assert record["requests"][0]["status"] == "evidence_error"
    assert (entry.RESULTS / "payloads/01.json").exists()
    public = entry.read(entry.RESULTS / f"{entry.PHASE}-zh-short.json")
    assert "result" not in public and public["error_type"] == "OSError"


@pytest.mark.parametrize("changes", [
    {"status": "http_error", "http_status": True},
    {"status": "http_error"}, {"http_status": True}, {"http_status": 200.0},
    {"http_status": 503}, {"usage": {"prompt_tokens": 3}},
    {"ended_utc": None}, {"ended_utc": "before-response"},
    {"ended_utc": "2000-01-01T00:00:00+00:00"},
])
def test_contradictory_response_ledger_is_rejected_before_frozen_execution(completed, monkeypatch, changes):
    entry, checker = completed
    ledger = entry.read(entry.LEDGER)
    ledger["requests"][0].update(changes)
    entry.base.durable(entry.LEDGER, ledger)
    executed = []
    original_runtime = checker.frozen_runtime
    monkeypatch.setattr(checker, "frozen_runtime", lambda frozen: (executed.append(True), original_runtime(frozen))[1])
    with pytest.raises(RuntimeError):
        checker.check_phase()
    assert executed == []


@pytest.mark.parametrize("value", [True, 200.0, 503])
def test_response_http_status_is_typed_and_bound_to_ledger(completed, monkeypatch, value):
    entry, checker = completed
    ledger = entry.read(entry.LEDGER)
    row = ledger["requests"][0]
    path = entry.RESULTS / "responses" / f"{row['ordinal']:02d}.json"
    response = entry.read(path)
    response["http_status"] = value
    entry.base.durable(path, response)
    row["response_sha256"] = entry.base.digest(path.read_bytes())
    entry.base.durable(entry.LEDGER, ledger)
    executed = []
    original_runtime = checker.frozen_runtime
    monkeypatch.setattr(checker, "frozen_runtime", lambda frozen: (executed.append(True), original_runtime(frozen))[1])
    with pytest.raises(RuntimeError):
        checker.check_phase()
    assert executed == []


@pytest.mark.parametrize("usage", [
    {"prompt_tokens": True}, {"completion_tokens": 1.0}, {"total_tokens": -1},
    {"arbitrary": 1}, {"prompt_tokens_details": {"cached_tokens": True}},
    {"completion_tokens_details": {"reasoning_tokens": -1}},
    {"prompt_tokens_details": {"secret": "unrecognized"}},
    {"completion_tokens_details": []},
])
def test_self_consistent_invalid_usage_cannot_be_evidence_verified(completed, monkeypatch, usage):
    entry, checker = completed
    ledger = entry.read(entry.LEDGER)
    row = ledger["requests"][0]
    path = entry.RESULTS / "responses" / f"{row['ordinal']:02d}.json"
    response = entry.read(path)
    response["usage"] = row["usage"] = usage
    entry.base.durable(path, response)
    row["response_sha256"] = entry.base.digest(path.read_bytes())
    entry.base.durable(entry.LEDGER, ledger)
    executed = []
    original_runtime = checker.frozen_runtime
    monkeypatch.setattr(checker, "frozen_runtime", lambda frozen: (executed.append(True), original_runtime(frozen))[1])
    with pytest.raises(RuntimeError):
        checker.check_phase()
    assert executed == []


@pytest.mark.parametrize("usage", [None, {}, {
    "prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13,
    "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 9,
    "prompt_tokens_details": {"cached_tokens": 0, "audio_tokens": 1},
    "completion_tokens_details": {"reasoning_tokens": 0, "audio_tokens": 0,
        "accepted_prediction_tokens": 2, "rejected_prediction_tokens": 0},
}])
def test_matching_safe_usage_remains_replayable(completed, usage):
    entry, checker = completed
    ledger = entry.read(entry.LEDGER)
    row = ledger["requests"][0]
    path = entry.RESULTS / "responses" / f"{row['ordinal']:02d}.json"
    response = entry.read(path)
    response["usage"] = row["usage"] = usage
    entry.base.durable(path, response)
    row["response_sha256"] = entry.base.digest(path.read_bytes())
    entry.base.durable(entry.LEDGER, ledger)
    assert checker.check_phase()["evidence_verified"] is True


@pytest.mark.parametrize("status", ["reserved", "evidence_error", "transport_error"])
def test_missing_response_completion_cannot_verify_success(completed, monkeypatch, status):
    entry, checker = completed
    ledger = entry.read(entry.LEDGER)
    row = ledger["requests"][0]
    row["status"] = status
    if status == "transport_error":
        for key in ("http_status", "usage", "response_sha256"):
            row.pop(key)
    entry.base.durable(entry.LEDGER, ledger)
    executed = []
    original_runtime = checker.frozen_runtime
    monkeypatch.setattr(checker, "frozen_runtime", lambda frozen: (executed.append(True), original_runtime(frozen))[1])
    with pytest.raises(RuntimeError):
        checker.check_phase()
    assert executed == []


def test_missing_response_original_cannot_verify_success(completed, monkeypatch):
    entry, checker = completed
    # Only this test's isolated response file is removed; real phase assets remain untouched.
    (entry.RESULTS / "responses/01.json").unlink()
    executed = []
    original_runtime = checker.frozen_runtime
    monkeypatch.setattr(checker, "frozen_runtime", lambda frozen: (executed.append(True), original_runtime(frozen))[1])
    with pytest.raises((RuntimeError, FileNotFoundError)):
        checker.check_phase()
    assert executed == []
