"""Hermetic contract acceptance tests; no model, environment, or old evidence writes.

Engineering: skill priority; UI ui-ux-pro-max/design-system, three-layer tokens;
configurable narrow interfaces; llm_service/yt-dlp service boundaries, scene read-only.
"""
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import socket
import sys

import dotenv
import httpx
import pytest
import test_grounded_final_evaluation as helpers

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "docs/acceptance-reports/2026-10-07-grounded-summary-contracts/scripts/evaluate.py"
PHASE = "organization-contracts"


def test_contract_entrypoint_is_available():
    assert ENTRY.is_file(), "independent contract entrypoint is missing"


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("contract tests must not read environment or use the network")
    monkeypatch.setattr(dotenv, "load_dotenv", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def entry(tmp_path, monkeypatch, request):
    monkeypatch.setattr(helpers, "ENTRY", ENTRY)
    return helpers.entry.__wrapped__(tmp_path, monkeypatch, request)


def test_default_plan_has_fresh_phase_and_preserves_fourteen_rubric_bytes(entry, capsys):
    entry.main([])
    plan = json.loads(capsys.readouterr().out)
    assert plan["phase"] == PHASE and plan["network"] is False
    assert plan["ceiling"] == plan["expected_posts"] == 13
    assert plan["ledger"] == str(entry.LEDGER)
    assert not entry.RESULTS.exists()
    original = ENTRY.parents[2] / "2026-10-07-grounded-summary-refined/rubric.json"
    assert (ENTRY.parents[1] / "rubric.json").read_bytes() == original.read_bytes()


@pytest.mark.parametrize("component", ["contracts", "final", "organization", "runner", "checker", "checker-runner"])
def test_every_effective_chain_file_is_bound_before_reservation(entry, monkeypatch, tmp_path, component):
    module = {"contracts": entry, "final": entry.final, "organization": entry.organization,
              "runner": entry.base}.get(component)
    path = Path(module.__file__) if module else getattr(entry, "CHECKER_PATH" if component == "checker" else "CHECKER_RUNNER_PATH")
    copy = tmp_path / f"{component}-copy.py"
    copy.write_bytes(path.read_bytes())
    if module:
        monkeypatch.setattr(module, "__file__", str(copy))
    else:
        monkeypatch.setattr(entry, "CHECKER_PATH" if component == "checker" else "CHECKER_RUNNER_PATH", copy)
    frozen = entry.snapshot()
    copy.write_bytes(copy.read_bytes() + b"\n# drift\n")
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("drift reached POST"))) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        client.sample = "short"
        with pytest.raises(RuntimeError, match="freeze|differs"):
            client.post(helpers.URL, headers={}, json=helpers.payload(frozen))
    assert not entry.LEDGER.exists()


@pytest.mark.parametrize("failure", [None, "transport", "http", "invalid_json", "contract"])
def test_real_base_runner_reserves_serial_3_3_7_and_never_restarts(entry, monkeypatch, failure):
    # Reuse the historical hermetic transport/runtime fixture, exercising the
    # actual runner and its durable side effects with the new wrapper bindings.
    monkeypatch.setattr(helpers, "PHASE", PHASE)
    helpers.test_real_runner_uses_serial_three_three_seven_and_stops_after_failure(entry, monkeypatch, failure)


@pytest.mark.parametrize("mutation", ["float-ceiling", "foreign-phase", "bad-ordinal"])
def test_own_ledger_identity_is_checked_before_send(entry, mutation):
    old = helpers.PHASE
    try:
        helpers.PHASE = PHASE
        helpers.test_standalone_client_refuses_invalid_existing_ledger_before_send(entry, mutation)
    finally:
        helpers.PHASE = old


def canonical(value):
    return json.loads(json.dumps(value))


def candidate_record(candidate):
    return {"summary": [{"text": c.text, "fact_ids": list(c.fact_ids)} for c in candidate.summary],
            "key_points": [{"topic": c.topic, "text": c.text, "fact_ids": list(c.fact_ids)} for c in candidate.key_points]}


@pytest.fixture
def evidence(entry, monkeypatch):
    # Use actual production pure codec bytes in the frozen snapshot. No runtime,
    # service imports or environment access are needed for this fixture.
    path = ROOT / "backend/app/services/summary_facts.py"
    spec = importlib.util.spec_from_file_location("contract_fixture_codec", path)
    codec = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, codec)
    spec.loader.exec_module(codec)
    entry.base.MODULES["facts"].write_bytes(path.read_bytes())
    entry.base.FactLimits = codec.FactLimits
    entry.main(["--freeze"])
    frozen = json.loads((entry.RESULTS / f"{PHASE}-provenance.json").read_text())
    limits = codec.FactLimits(**frozen["fact_limits"])
    pending = []
    def respond(request):
        assert json.loads(entry.LEDGER.read_text())["requests"][-1]["status"] == "reserved"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(pending.pop(0))}, "finish_reason": "stop"}]})
    rows = []
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        for sample in frozen["samples"]:
            identifier = sample["id"]
            source = (entry.base.OLD / f"corpus/{identifier}.txt").read_text()
            parts, start = [], 0
            for n, text in enumerate(source.split("|"), 1):
                parts.append(codec.SourcePart(f"S{n}", text, start))
                start += len(text) + 1
            client.sample, client.sample_post = identifier, 0
            facts = []
            stages = []
            def post(stage, user, output):
                pending.append(output)
                payload = helpers.payload(frozen, stage, 4096 if stage == "extract" else 8192)
                payload["messages"].append({"role": "user", "content": json.dumps(user)})
                client.post(helpers.URL, headers={}, json=payload)
                stages.append({"stage": stage, "status": "validated", "max_output_tokens": payload["max_tokens"]})
            for n, part in enumerate(parts, 1):
                output = {f"fact_{i}": None for i in range(1, 13)}
                output["fact_1"] = {"topic": "source topic", "claim": f"source claim {n}",
                                    "evidence": [1], "attribution": "source", "importance": "core"}
                post("extract", {"source": {"id": part.id, "line_count": 1, "text": f"[1] {part.text}"}}, output)
                facts.extend(codec.parse_extraction(output, part, limits, f"F{n}_"))
            refs = [fact.id for fact in facts]
            point = {"topic": "global topic", "text": "source point", "fact_ids": refs}
            composition = {"summary": [{"text": "source summary", "fact_ids": refs}],
                           **{f"point_{i}": point if i == 1 else None for i in range(1, 8)},
                           "theme_plan": {f"theme_{i}": {"topic": "global topic", "principle": "source principle",
                               "conditions": ["source condition"], "consequences": ["source consequence"],
                               "fact_ids": refs} if i == 1 else None for i in range(1, 8)}}
            post("compose", {"facts": [{"id": f.id, "topic": f.topic, "claim": f.claim, "evidence": f.quote,
                                        "attribution": f.attribution, "importance": f.importance} for f in facts]}, composition)
            planned = codec.parse_planned_composition(composition, facts, limits)
            themes = canonical([asdict(t) for t in planned.themes])
            candidate = candidate_record(planned.candidate)
            audit_output = {"additional_facts": [], "output": candidate, "checks": [
                {"item_id": item, "supported": True, "qualifiers_preserved": True,
                 "attribution_preserved": True, "scope_preserved": True} for item in ("S1", "P1")]}
            user = {"sources": [{"id": p.id, "line_count": 1, "text": f"[1] {p.text}"} for p in parts],
                    "facts": [{"id": f.id, "source_id": f.source_id, "topic": f.topic, "claim": f.claim,
                               "evidence": list(f.evidence_indices), "attribution": f.attribution,
                               "importance": f.importance} for f in facts],
                    "candidate": candidate, "theme_plan": themes, "missing_core_fact_ids": []}
            post("audit", user, audit_output)
            audit = codec.parse_audit(audit_output, parts, facts, limits)
            event = {"sources": [{"id": p.id, "text": p.text, "global_start": p.global_start, "sha256": p.sha256} for p in parts],
                     "planned_calls": len(parts) + 2, "stages": stages, "status": "completed",
                     "facts": canonical([asdict(f) for f in facts]), "candidate": candidate, "theme_plan": themes,
                     "audit": {"facts": canonical([asdict(f) for f in audit.facts]), "output": candidate,
                               "checks": canonical([asdict(c) for c in audit.checks])}}
            trace = entry.RESULTS / f"{PHASE}-{identifier}-trace.json"
            helpers.write(trace, {"phase": PHASE, "id": identifier, "events": [event]})
            result_path = entry.RESULTS / f"{PHASE}-{identifier}.json"
            helpers.write(result_path, {"phase": PHASE, "id": identifier, "source_sha256": sample["sha256"],
                "trace_sha256": helpers.sha(trace.read_bytes()), "result": {"summary": "source summary", "key_points": ["source point"],
                                                                          "provider": "offline", "model": "offline-model"}})
            rows.append({"id": identifier, "file": result_path.name, "sha256": helpers.sha(result_path.read_bytes()),
                         "posts": len(parts) + 2})
    helpers.write(entry.RESULTS / f"{PHASE}-index.json", {"sample_results": rows})
    checking = helpers.load(ENTRY.with_name("check_evidence.py"), "contracts_test_checker")
    for key in ("REPORT", "RESULTS", "LEDGER"):
        monkeypatch.setattr(checking, key, getattr(entry, key))
    monkeypatch.setattr(checking.checker, "OLD", entry.base.OLD)
    monkeypatch.setattr(checking.checker, "BASE", entry.base.BASE)
    return checking


def refresh_trace_hashes(evidence, sample="short"):
    result = evidence.RESULTS / f"{PHASE}-{sample}.json"
    data = json.loads(result.read_text())
    data["trace_sha256"] = helpers.sha((evidence.RESULTS / f"{PHASE}-{sample}-trace.json").read_bytes())
    helpers.write(result, data)
    path = evidence.RESULTS / f"{PHASE}-index.json"
    index = json.loads(path.read_text())
    next(row for row in index["sample_results"] if row["id"] == sample)["sha256"] = helpers.sha(result.read_bytes())
    helpers.write(path, index)


def refresh_call_hash(evidence, ordinal, kind):
    path = evidence.RESULTS / kind / f"{ordinal:02d}.json"
    ledger = json.loads(evidence.LEDGER.read_text())
    ledger["requests"][ordinal - 1]["payload_sha256" if kind == "payloads" else "response_sha256"] = helpers.sha(path.read_bytes())
    helpers.write(evidence.LEDGER, ledger)


def test_checker_reconstructs_raw_contracts_with_frozen_codec(evidence, entry):
    entry.base.MODULES["facts"].write_text('raise RuntimeError("live codec forbidden")\n')
    result = evidence.check_phase()
    assert result["offline_only"] is True and result["phase"] == PHASE
    assert [s["validated_contract_stages"] for s in result["samples"]] == [3, 3, 7]
    assert all(s["raw_contracts_bound"] for s in result["samples"])
    assert result["semantic_accuracy_not_proven_by_this_check"] is True


@pytest.mark.parametrize("mutation", ["extract-raw", "compose-raw", "trace-fact", "trace-theme", "audit-plan", "received"])
def test_checker_rejects_rehashed_raw_trace_plan_disagreement(evidence, mutation):
    if mutation in ("extract-raw", "compose-raw"):
        ordinal = 1 if mutation == "extract-raw" else 2
        path = evidence.RESULTS / "responses" / f"{ordinal:02d}.json"
        response = json.loads(path.read_text())
        raw = json.loads(response["content"])
        if mutation == "extract-raw":
            raw["fact_1"]["claim"] = "different valid claim"
        else:
            raw["theme_plan"]["theme_1"]["principle"] = "different valid principle"
        response["content"] = json.dumps(raw)
        helpers.write(path, response)
        refresh_call_hash(evidence, ordinal, "responses")
    elif mutation == "audit-plan":
        path = evidence.RESULTS / "payloads/03.json"
        payload = json.loads(path.read_text())
        user = json.loads(payload["messages"][1]["content"])
        user["theme_plan"][0]["conditions"] = ["changed condition"]
        payload["messages"][1]["content"] = json.dumps(user)
        helpers.write(path, payload)
        refresh_call_hash(evidence, 3, "payloads")
    else:
        path = evidence.RESULTS / f"{PHASE}-short-trace.json"
        trace = json.loads(path.read_text())
        event = trace["events"][-1]
        if mutation == "trace-fact":
            event["facts"][0]["claim"] = "different valid claim"
        elif mutation == "trace-theme":
            event["theme_plan"][0]["consequences"] = ["different valid consequence"]
        else:
            event["stages"][-1]["status"] = "received"
        helpers.write(path, trace)
        refresh_trace_hashes(evidence)
    with pytest.raises(ValueError, match="mismatch|validated|contract|stage"):
        evidence.check_phase()


def test_checker_verifies_frozen_hash_before_codec_execution(evidence, monkeypatch):
    (evidence.RESULTS / f"{PHASE}-facts.py").write_text('raise RuntimeError("must never execute")\n')
    monkeypatch.setattr(evidence.checker, "frozen_helpers", lambda *a: pytest.fail("drifted snapshot was executed"))
    with pytest.raises(ValueError, match="Frozen module hash mismatch"):
        evidence.check_phase()


@pytest.mark.parametrize("smuggle_fact", [False, True])
def test_received_invalid_extraction_never_becomes_validated_evidence(evidence, smuggle_fact):
    # The eighth POST receives 13 slots and is rejected. Only long's first
    # extraction is validated; its second received response spends budget but
    # cannot contribute a fact or count as a successful contract stage.
    path = evidence.RESULTS / "responses/08.json"
    response = json.loads(path.read_text())
    raw = json.loads(response["content"])
    raw["fact_13"] = dict(raw["fact_1"])
    response["content"] = json.dumps(raw)
    helpers.write(path, response)
    ledger = json.loads(evidence.LEDGER.read_text())
    ledger["requests"] = ledger["requests"][:8]
    ledger["requests"][-1]["response_sha256"] = helpers.sha(path.read_bytes())
    helpers.write(evidence.LEDGER, ledger)
    trace_path = evidence.RESULTS / f"{PHASE}-long-trace.json"
    trace = json.loads(trace_path.read_text())
    event = trace["events"][-1]
    event["stages"] = event["stages"][:2]
    event["stages"][-1]["status"] = "received"
    event["facts"] = event["facts"][:2 if smuggle_fact else 1]
    event["status"], event["error_type"] = "failed", "llm_invalid_response"
    for key in ("candidate", "theme_plan", "audit"):
        event.pop(key)
    helpers.write(trace_path, trace)
    result_path = evidence.RESULTS / f"{PHASE}-long.json"
    result = json.loads(result_path.read_text())
    result.pop("result")
    result["error_type"] = "llm_invalid_response"
    helpers.write(result_path, result)
    index_path = evidence.RESULTS / f"{PHASE}-index.json"
    index = json.loads(index_path.read_text())
    index["sample_results"][-1]["posts"] = 2
    helpers.write(index_path, index)
    refresh_trace_hashes(evidence, "long")
    if smuggle_fact:
        with pytest.raises(ValueError, match="Raw extraction trace facts mismatch"):
            evidence.check_phase()
    else:
        checked = evidence.check_phase()["samples"][-1]
        assert checked["validated_contract_stages"] == 1
        assert checked["audit_contract_valid"] is False
        assert checked["unvalidated_contract_stages"] == [
            {"stage": "extract", "trace_status": "received", "reason": "invalid_fields"}]


@pytest.mark.parametrize("drift", ["source", "prompt", "codec", "module-config", "budget"])
def test_live_post_freeze_rechecks_generation_inputs(entry, monkeypatch, tmp_path, drift):
    monkeypatch.setattr(helpers, "PHASE", PHASE)
    helpers.test_post_rechecks_entire_freeze_before_reservation(entry, monkeypatch, tmp_path, drift)


def test_contract_caller_lock_excludes_historical_sessions(entry, monkeypatch):
    monkeypatch.setattr(helpers, "PHASE", PHASE)
    helpers.test_prior_caller_lock_excludes_final_and_ledger_lock_is_independent(entry)


@pytest.mark.parametrize("duplicate", ["requests", "phase", "ordinal"])
def test_existing_duplicate_ledger_refuses_post_before_reservation(entry, duplicate):
    frozen = entry.snapshot()
    if duplicate == "requests":
        text = '{"ceiling":13,"requests":[{"ordinal":1,"phase":"organization-contracts"}],"requests":[]}'
    else:
        row = '{"ordinal":1,"phase":"organization-contracts"}'
        value = '1' if duplicate == "ordinal" else '"organization-contracts"'
        row = '{"' + duplicate + '":' + value + ',' + row[1:]
        text = '{"ceiling":13,"requests":[' + row + ']}'
    entry.LEDGER.parent.mkdir(parents=True, exist_ok=True)
    entry.LEDGER.write_text(text, encoding="utf-8")
    before = entry.LEDGER.read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("duplicate ledger reached POST"))) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        client.sample = "short"
        with pytest.raises(RuntimeError, match="duplicate|Duplicate|ledger"):
            client.post(helpers.URL, headers={}, json=helpers.payload(frozen))
    assert entry.LEDGER.read_bytes() == before
    assert not (entry.RESULTS / "payloads").exists()


@pytest.mark.parametrize("artifact", ["provenance", "ledger", "payload", "response", "trace", "index", "result", "nested-ledger", "nested-trace"])
def test_checker_rejects_duplicate_outer_and_nested_artifact_fields(evidence, artifact):
    table = {
        "provenance": (evidence.RESULTS / f"{PHASE}-provenance.json", "phase"),
        "ledger": (evidence.LEDGER, "requests"),
        "payload": (evidence.RESULTS / "payloads/01.json", "messages"),
        "response": (evidence.RESULTS / "responses/01.json", "ordinal"),
        "trace": (evidence.RESULTS / f"{PHASE}-short-trace.json", "phase"),
        "index": (evidence.RESULTS / f"{PHASE}-index.json", "sample_results"),
        "result": (evidence.RESULTS / f"{PHASE}-short.json", "id"),
    }
    if artifact in table:
        path, key = table[artifact]
        data = json.loads(path.read_text())
        text = '{"' + key + '":' + json.dumps(data[key]) + ',' + json.dumps(data)[1:]
    elif artifact == "nested-ledger":
        path = evidence.LEDGER
        text = path.read_text().replace('"ordinal": 1', '"ordinal": 1, "ordinal": 1', 1)
    else:
        path = evidence.RESULTS / f"{PHASE}-short-trace.json"
        text = path.read_text().replace('"claim": "source claim 1"', '"claim": "source claim 1", "claim": "source claim 1"', 1)
    path.write_text(text, encoding="utf-8")
    if artifact == "payload":
        refresh_call_hash(evidence, 1, "payloads")
    elif artifact == "response":
        refresh_call_hash(evidence, 1, "responses")
    elif artifact in ("trace", "nested-trace"):
        refresh_trace_hashes(evidence)
    elif artifact == "result":
        index_path = evidence.RESULTS / f"{PHASE}-index.json"
        index = json.loads(index_path.read_text())
        index["sample_results"][0]["sha256"] = helpers.sha(path.read_bytes())
        helpers.write(index_path, index)
    with pytest.raises(ValueError, match="Duplicate JSON field"):
        evidence.check_phase()


@pytest.mark.parametrize("location", ["ledger-ordinal", "ledger-sample_post", "response-ordinal"])
@pytest.mark.parametrize("bad", [True, 1.0])
def test_checker_requires_exact_integer_request_identity(evidence, location, bad):
    if location.startswith("ledger"):
        data = json.loads(evidence.LEDGER.read_text())
        data["requests"][0][location.split("-", 1)[1]] = bad
        helpers.write(evidence.LEDGER, data)
    else:
        path = evidence.RESULTS / "responses/01.json"
        data = json.loads(path.read_text())
        data["ordinal"] = bad
        helpers.write(path, data)
        refresh_call_hash(evidence, 1, "responses")
    with pytest.raises(ValueError, match="ordinal|sample_post|identity"):
        evidence.check_phase()


@pytest.mark.parametrize("location", ["frozen-sections", "frozen-total", "trace-calls", "stage-budget", "source-lines"])
def test_checker_rejects_noninteger_identity_counts(evidence, location):
    if location.startswith("frozen"):
        path = evidence.RESULTS / f"{PHASE}-provenance.json"
        data = json.loads(path.read_text())
        if location == "frozen-sections":
            data["samples"][0]["sections"] = True
        else:
            data["expected_posts"] = 13.0
        helpers.write(path, data)
    elif location == "source-lines":
        path = evidence.RESULTS / "payloads/01.json"
        data = json.loads(path.read_text())
        user = json.loads(data["messages"][1]["content"])
        user["source"]["line_count"] = True
        data["messages"][1]["content"] = json.dumps(user)
        helpers.write(path, data)
        refresh_call_hash(evidence, 1, "payloads")
    else:
        path = evidence.RESULTS / f"{PHASE}-short-trace.json"
        data = json.loads(path.read_text())
        event = data["events"][-1]
        if location == "trace-calls":
            event["planned_calls"] = 3.0
        else:
            event["stages"][0]["max_output_tokens"] = 4096.0
        helpers.write(path, data)
        refresh_trace_hashes(evidence)
    with pytest.raises(ValueError, match="integer|count|budget"):
        evidence.check_phase()


@pytest.mark.parametrize("bad", [True, 1.0])
def test_audit_payload_evidence_binding_rejects_bool_and_float(evidence, bad):
    path = evidence.RESULTS / "payloads/03.json"
    payload = json.loads(path.read_text())
    user = json.loads(payload["messages"][1]["content"])
    user["facts"][0]["evidence"] = [bad]
    payload["messages"][1]["content"] = json.dumps(user)
    helpers.write(path, payload)
    refresh_call_hash(evidence, 3, "payloads")
    with pytest.raises(ValueError, match="Audit request facts mismatch"):
        evidence.check_phase()


@pytest.mark.parametrize("bad", [False, 0.0])
def test_raw_extraction_trace_binding_rejects_wrong_numeric_types(evidence, bad):
    path = evidence.RESULTS / f"{PHASE}-short-trace.json"
    trace = json.loads(path.read_text())
    trace["events"][-1]["facts"][0]["start"] = bad
    helpers.write(path, trace)
    refresh_trace_hashes(evidence)
    with pytest.raises(ValueError, match="Raw extraction trace facts mismatch"):
        evidence.check_phase()


def test_binding_accepts_object_key_reordering_and_normal_json_arrays(evidence):
    def reorder(value):
        if isinstance(value, dict):
            return {key: reorder(item) for key, item in reversed(list(value.items()))}
        if isinstance(value, list):
            return [reorder(item) for item in value]
        return value
    path = evidence.RESULTS / "payloads/03.json"
    payload = json.loads(path.read_text())
    user = json.loads(payload["messages"][1]["content"])
    payload["messages"][1]["content"] = json.dumps(reorder(user))
    helpers.write(path, reorder(payload))
    refresh_call_hash(evidence, 3, "payloads")
    result = evidence.check_phase()
    assert result["samples"][0]["validated_contract_stages"] == 3
    assert result["samples"][0]["raw_contracts_bound"] is True
