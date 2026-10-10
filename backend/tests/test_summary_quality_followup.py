"""Isolated offline checks for the finite quality-repaired continuation.

Engineering: skill-first, UI three-layer tokens, configurable narrow interfaces;
HTTP only llm_service, yt-dlp only ytdlp_service, scene read-only.
"""
import importlib.util
import json
from pathlib import Path
import shutil

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-09-summary-quality-repaired/scripts/evaluate.py"
PARENT = ROOT / "docs/acceptance-reports/2026-10-08-summary-quality-final"


@pytest.fixture
def entry(tmp_path, monkeypatch):
    assert SCRIPT.exists(), "Finite follow-up evaluator is missing"
    spec = importlib.util.spec_from_file_location("quality_followup_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = tmp_path / "new"
    results.mkdir()
    old = tmp_path / "parent"
    shutil.copytree(PARENT / "results", old)
    monkeypatch.setattr(module, "RESULTS", results)
    monkeypatch.setattr(module, "LEDGER", results / "request-ledger.json")
    monkeypatch.setattr(module, "PARENT_RESULTS", old)
    monkeypatch.setattr(module, "PARENT_LEDGER", old / "request-ledger.json")
    monkeypatch.setattr(module, "GROUP", tmp_path / "group.json")
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    monkeypatch.setattr(module, "CALLER_LOCK", tmp_path / "caller.lock")
    module.base.exclusive(module.GROUP, {"work_id": module.WORK_ID, "hard_ceiling": 26,
        "initial_phase_ceiling": 19, "maximum_followup_phase_posts": 19,
        "followup_normal_posts": 13, "followup_maximum_work_posts": 22,
        "reserved_posts": 3, "followup_reason": "Offline-confirmed scalar normalization",
        "phases": [{"phase": "quality-final", "ceiling": 19, "ledger": str(module.PARENT_LEDGER)}],
        "status": "closed"})
    return module


def test_default_plan_keeps_env_network_off_and_default_repairs(entry, monkeypatch, capsys):
    monkeypatch.setattr(entry, "load_runtime", lambda: pytest.fail("Default plan loaded user runtime"))
    entry.main([])
    plan = json.loads(capsys.readouterr().out)
    assert plan["phase"] == "quality-repaired"
    assert plan["network"] is False and plan["expected_posts"] == 13 and plan["ceiling"] == 19
    assert plan["work_ceiling"] == 26 and plan["maximum_work_posts"] == 22
    assert plan["config"]["llm_summary_format_retries"] == 1
    assert plan["config"]["llm_summary_semantic_retries"] == 1
    assert plan["config"]["llm_summary_max_extra_calls"] == 2
    assert len(entry.MODULES) == 8


def test_existing_closed_three_post_phase_is_legal(entry):
    group, used = entry.validate_group()
    assert used == 3 and group["status"] == "closed"
    assert len(group["phases"]) == 1


def test_rubric_is_byte_exact_parent_copy(entry):
    assert (entry.REPORT / "rubric.json").read_bytes() == (PARENT / "rubric.json").read_bytes()


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


def test_freeze_appends_finite_allocation_and_binds_all_executed_files(frozen_entry):
    entry = frozen_entry
    group, count = entry.validate_group()
    assert count == 3 and group["status"] == "frozen" and group["hard_ceiling"] == 26
    assert [p["phase"] for p in group["phases"]] == ["quality-final", "quality-repaired"]
    assert group["phases"][-1]["ceiling"] == 19
    frozen = entry.read(entry.RESULTS / f"{entry.PHASE}-provenance.json")
    assert set(frozen["runner_chain_sha256"]) == {"entry", "checker", "parent_evaluator", "parent_checker", "helper"}
    assert frozen["parent_assets_sha256"] == entry.parent_assets()
    assert frozen["runner_sha256"] == entry.base.digest(entry.HELPER.read_bytes())
    entry.main(["--check-only"])
    with pytest.raises(RuntimeError):
        entry.main(["--freeze"])
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
        elif (stage == "compose" and profile in {"mixed", "worst"} and (profile == "worst" or sample == "zh-short")
                and sample not in compose_repaired):
            compose_repaired.add(sample)
            output = "invalid"
        elif stage == "compose":
            output = {"summary": " ".join(f["claim"] for f in facts),
                "key_points": [{"topic": f["topic"], "text": f["claim"], "fact_ids": [f"F{i}_1"]}
                    for i, f in enumerate(facts, 1)],
                "theme_plan": {f"theme_{i}": {"topic": f["topic"], "principle": f["claim"],
                    "conditions": f["claim"] if profile == "scalar" else [],
                    "consequences": "" if profile == "scalar" else [], "fact_ids": [f"F{i}_1"]}
                    for i, f in enumerate(facts, 1)}}
        else:
            flags = {"supported": True, "qualifiers_preserved": True,
                "attribution_preserved": True, "scope_preserved": True}
            output = {"additional_facts": [], "output": {
                "summary": {"text": " ".join(f["claim"] for f in facts), "assertions": flags},
                **{f"point_{i}": {"topic": f["topic"], "text": f["claim"],
                    "assertions": flags, "fact_ids": [f"F{i}_1"]} for i, f in enumerate(facts, 1)}}}
            if (profile in {"mixed", "worst"} and (profile == "worst" or sample == "zh-short")
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

@pytest.mark.parametrize("completed,posts", [("normal", 13), ("scalar", 13), ("mixed", 15), ("worst", 19)], indirect=["completed"])
def test_default_normal_mixed_worst_replay_inside_original_work_ceiling(completed, posts):
    entry, checker = completed
    result = checker.check_phase()
    assert result["posts"] == posts and result["work_posts"] == posts + 3
    assert result["evidence_verified"] is True and result["semantic_quality"] == "NOT_EVALUATED"
    assert len(result["samples"]) == 3 and all(row["status"] == "completed" for row in result["samples"])
    group, count = entry.validate_group()
    assert group["status"] == "closed" and count == posts + 3 <= 22 < 26
    with pytest.raises(RuntimeError):
        entry.main(["--run"])
    with pytest.raises(RuntimeError):
        entry.main(["--freeze"])


@pytest.mark.parametrize("completed", ["scalar"], indirect=True)
def test_scalar_theme_repair_is_local_and_preserves_raw_original(completed):
    entry, checker = completed
    assert checker.check_phase()["posts"] == 13
    trace = entry.read(entry.RESULTS / f"{entry.PHASE}-zh-short-trace.json")["events"][-1]
    assert "theme_scalar_text_wrapped" in trace["normalization"]
    assert trace["retry_budget"]["used"] == 0
    row = next(r for r in entry.validate_ledger()["requests"] if r["stage"] == "compose")
    raw = entry.read(entry.RESULTS / "responses" / f"{row['ordinal']:02d}.json")
    original = json.loads(raw["content"])
    assert isinstance(original["theme_plan"]["theme_1"]["conditions"], str)
    assert original["theme_plan"]["theme_1"]["consequences"] == ""


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



@pytest.mark.parametrize("changes", [{"status": "frozen"}, {"reserved_posts": True},
    {"hard_ceiling": 27}, {"maximum_followup_phase_posts": 20}, {"followup_maximum_work_posts": 23}])
def test_invalid_parent_allocation_refused_before_runtime(entry, monkeypatch, changes):
    group = entry.read(entry.GROUP)
    group.update(changes)
    entry.base.durable(entry.GROUP, group)
    monkeypatch.setattr(entry, "load_runtime", lambda: pytest.fail("Invalid allocation loaded runtime"))
    with pytest.raises(RuntimeError):
        entry.main(["--freeze"])


def test_parent_raw_tamper_before_freeze_is_refused(entry, monkeypatch):
    path = entry.PARENT_RESULTS / "responses/01.json"
    path.write_bytes(path.read_bytes() + b" ")
    monkeypatch.setattr(entry, "load_runtime", lambda: pytest.fail("Tampered parent loaded runtime"))
    with pytest.raises(RuntimeError, match="Parent"):
        entry.main(["--freeze"])


@pytest.mark.parametrize("asset", ["PARENT_EVALUATOR", "PARENT_CHECKER", "HELPER", "CHECKER"])
def test_executed_helper_tamper_is_rejected_before_frozen_execution(completed, monkeypatch, tmp_path, asset):
    entry, checker = completed
    changed = tmp_path / "tampered-helper.py"
    changed.write_bytes(getattr(entry, asset).read_bytes() + b"\n# changed prefix\n")
    monkeypatch.setattr(entry, asset, changed)
    monkeypatch.setattr(checker, "frozen_runtime", lambda _: pytest.fail("Unverified helper executed frozen code"))
    with pytest.raises(RuntimeError, match="hash"):
        checker.check_phase()


def test_closed_parent_tamper_is_rejected_before_frozen_execution(completed, monkeypatch):
    entry, checker = completed
    path = entry.PARENT_RESULTS / "responses/01.json"
    path.write_bytes(path.read_bytes() + b" ")
    monkeypatch.setattr(checker, "frozen_runtime", lambda _: pytest.fail("Changed parent reached frozen code"))
    with pytest.raises(RuntimeError, match="parent"):
        checker.check_phase()


@pytest.mark.parametrize("field", ["parent_posts", "maximum_work_posts"])
def test_parent_bool_metadata_is_refused_before_frozen_execution(completed, monkeypatch, field):
    entry, checker = completed
    path = entry.RESULTS / f"{entry.PHASE}-provenance.json"
    frozen = entry.read(path)
    frozen[field] = True
    entry.base.durable(path, frozen)
    monkeypatch.setattr(checker, "frozen_runtime", lambda _: pytest.fail("Bool metadata reached frozen code"))
    with pytest.raises(RuntimeError, match="metadata"):
        checker.check_phase()


@pytest.fixture
def guarded(frozen_entry):
    entry = frozen_entry
    frozen = entry.read(entry.RESULTS / f"{entry.PHASE}-provenance.json")
    sent = []

    def respond(request):
        assert entry.validate_ledger()["requests"][-1]["status"] == "reserved"
        sent.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "invalid"}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = entry.BudgetClient(transport, frozen)
        client.sample = "zh-short"
        client.latest = {"paid_calls": 1, "stages": [{"stage": "extract", "attempt": 1,
            "status": "requesting", "paid_attempt": True, "recovery": "none"}]}
        payload = {"model": frozen["model"], "temperature": 0.2,
            "max_tokens": frozen["stage_max_output_tokens"]["extract"], **frozen["options"],
            "messages": [{"role": "system", "content": frozen["stage_prompts"]["extract"]},
                         {"role": "user", "content": "{}"}]}
        yield entry, client, payload, sent


@pytest.mark.parametrize("field", ["attempt", "paid_calls"])
def test_bool_request_metadata_cannot_reach_transport(guarded, field):
    entry, client, payload, sent = guarded
    target = client.latest if field == "paid_calls" else client.latest["stages"][-1]
    target[field] = True
    with pytest.raises(RuntimeError):
        client.post(client.frozen["endpoint"], headers={}, json=payload)
    assert sent == [] and entry.validate_group()[1] == 3


@pytest.mark.parametrize("field", ["previous_response", "failed_items", "category"])
def test_guard_rejects_forged_repair_feedback_before_additional_transport(guarded, field):
    entry, client, payload, sent = guarded
    client.post(client.frozen["endpoint"], headers={}, json=payload)
    previous = client.latest["stages"][0]
    previous.update(status="failed", error_category="format", reason="invalid_json", failed_items=[])
    client.latest["paid_calls"] = 2
    client.latest["stages"].append({"stage": "extract", "attempt": 2, "status": "requesting",
        "paid_attempt": True, "recovery": "model_format_repair"})
    repair = {"category": "format", "reason": "invalid_json", "failed_items": [], "previous_response": "invalid"}
    repair[field] = ["invented"] if field == "failed_items" else "invented"
    payload["messages"] = [{"role": "system", "content": client.frozen["repair_prompts"]["extract"]},
        {"role": "user", "content": json.dumps({"repair": repair})}]
    with pytest.raises(RuntimeError):
        client.post(client.frozen["endpoint"], headers={}, json=payload)
    assert len(sent) == len(entry.validate_ledger()["requests"]) == 1


def test_secret_headers_are_not_saved(guarded):
    entry, client, payload, sent = guarded
    client.post(client.frozen["endpoint"], headers={"Authorization": "Bearer offline-only-secret"}, json=payload)
    assert all("offline-only-secret" not in p.read_text(encoding="utf-8") for p in entry.RESULTS.rglob("*.json"))
    assert len(sent) == 1


def test_fsync_reservation_failure_cannot_send(guarded, monkeypatch):
    entry, client, payload, sent = guarded
    monkeypatch.setattr(entry.base, "durable", lambda *args: (_ for _ in ()).throw(OSError("fsync unavailable")))
    with pytest.raises(OSError):
        client.post(client.frozen["endpoint"], headers={}, json=payload)
    assert sent == []


def test_closed_phase_cannot_send_through_direct_budget_client(guarded):
    entry, client, payload, sent = guarded
    group = entry.read(entry.GROUP)
    group["status"] = "closed"
    entry.base.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="[Cc]losed"):
        client.post(client.frozen["endpoint"], headers={}, json=payload)
    assert sent == [] and entry.validate_group()[1] == 3
