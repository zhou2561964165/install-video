"""Hermetic prefix acceptance; real wrapper/runner/checker, no live model calls.

Engineering: skills precede plans; UI ui-ux-pro-max/design-system, three-layer
tokens; configurable narrow interfaces; llm_service/ytdlp_service boundaries;
scene read-only. Fixtures contain source fields, never rubric answers.
"""
import json
from pathlib import Path

import httpx
import pytest
import test_grounded_contract_evaluation as contracts_helpers
import test_grounded_final_evaluation as helpers

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "docs/acceptance-reports/2026-10-08-grounded-summary-prefix/scripts/evaluate.py"
PHASE = "organization-prefix"


def test_independent_prefix_entrypoint_is_available():
    assert ENTRY.is_file(), "independent prefix acceptance entrypoint is missing"


@pytest.fixture(autouse=True)
def isolated_helpers(monkeypatch):
    monkeypatch.setattr(helpers, "ENTRY", ENTRY)
    monkeypatch.setattr(helpers, "PHASE", PHASE)
    monkeypatch.setattr(contracts_helpers, "ENTRY", ENTRY)
    monkeypatch.setattr(contracts_helpers, "PHASE", PHASE)


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    contracts_helpers.no_external_io.__wrapped__(monkeypatch)


@pytest.fixture
def entry(tmp_path, monkeypatch, request):
    return helpers.entry.__wrapped__(tmp_path, monkeypatch, request)


def test_default_plan_is_independent_and_rubric_is_unchanged(entry, capsys):
    contracts_helpers.test_default_plan_has_fresh_phase_and_preserves_fourteen_rubric_bytes(entry, capsys)
    assert entry.CONFIG == entry.contracts.CONFIG
    assert entry.LEDGER != entry.contracts.LEDGER


@pytest.mark.parametrize("failure", [None, "transport", "http", "invalid_json", "contract"])
def test_real_runner_serial_3_3_7_and_error_stop(entry, monkeypatch, failure):
    helpers.test_real_runner_uses_serial_three_three_seven_and_stops_after_failure(entry, monkeypatch, failure)


@pytest.mark.parametrize("component", ["prefix", "contracts", "final", "organization", "runner",
                                        "checker", "contracts-checker", "checker-runner", "final-checker"])
def test_every_effective_file_drift_refuses_before_reservation(entry, monkeypatch, tmp_path, component):
    modules = {"prefix": entry, "contracts": entry.contracts, "final": entry.final,
               "organization": entry.organization, "runner": entry.base}
    keys = {"checker": "CHECKER_PATH", "contracts-checker": "CONTRACT_CHECKER_PATH",
            "checker-runner": "CHECKER_RUNNER_PATH"}
    module = modules.get(component)
    path = Path(module.__file__) if module else (entry.final.CHECKER_PATH if component == "final-checker"
                                               else getattr(entry, keys[component]))
    copy = tmp_path / f"{component}.py"
    copy.write_bytes(path.read_bytes())
    if module:
        monkeypatch.setattr(module, "__file__", str(copy))
    elif component == "final-checker":
        monkeypatch.setattr(entry.final, "CHECKER_PATH", copy)
    else:
        monkeypatch.setattr(entry, keys[component], copy)
    frozen = entry.snapshot()
    copy.write_bytes(copy.read_bytes() + b"\n# drift\n")
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("drift reached POST"))) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        client.sample = "short"
        with pytest.raises(RuntimeError, match="freeze|differs"):
            client.post(helpers.URL, headers={}, json=helpers.payload(frozen))
    assert not entry.LEDGER.exists()


@pytest.mark.parametrize("mutation", ["float-ceiling", "foreign-phase", "bad-ordinal"])
def test_bad_ledger_is_rejected_before_send(entry, mutation):
    helpers.test_standalone_client_refuses_invalid_existing_ledger_before_send(entry, mutation)


@pytest.mark.parametrize("duplicate", ["requests", "phase", "ordinal"])
def test_duplicate_ledger_cannot_spend(entry, duplicate):
    row = '{"ordinal":1,"phase":"organization-prefix"}'
    if duplicate == "requests":
        value = '{"ceiling":13,"requests":[' + row + '],"requests":[]}'
    else:
        field = '1' if duplicate == "ordinal" else '"organization-prefix"'
        value = '{"ceiling":13,"requests":[{"' + duplicate + '":' + field + ',' + row[1:] + ']}'
    entry.LEDGER.parent.mkdir(parents=True)
    entry.LEDGER.write_text(value)
    original = entry.LEDGER.read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("duplicate POST"))) as http:
        client = entry.BudgetClient(http, PHASE, entry.snapshot())
        client.sample = "short"
        with pytest.raises(RuntimeError, match="ledger|JSON|Duplicate"):
            client.post(helpers.URL, headers={}, json=helpers.payload(client.frozen))
    assert entry.LEDGER.read_bytes() == original
    assert not (entry.RESULTS / "payloads").exists()


@pytest.mark.parametrize("drift", ["source", "manifest", "runtime", "prompt", "codec", "module-config", "budget",
                                  "model", "options", "rubric", "phase", "ledger", "lock", "ceiling"])
def test_full_generation_freeze_is_verified(entry, monkeypatch, tmp_path, drift):
    helpers.test_post_rechecks_entire_freeze_before_reservation(entry, monkeypatch, tmp_path, drift)


def test_lock_and_thirteen_ceiling(entry):
    helpers.test_prior_caller_lock_excludes_final_and_ledger_lock_is_independent(entry)
    entry.CALLER_LOCK.rmdir()
    helpers.test_thirteen_post_ceiling_is_enforced_in_own_ledger(entry)


def test_module_runtime_bindings_restore_even_on_failure(entry):
    before = {module: dict(vars(module)) for module in (entry.contracts, entry.final, entry.organization, entry.base)}
    with pytest.raises(RuntimeError, match="fixture"):
        with entry.configured_base():
            assert entry.base.SHARED_LEDGER == entry.LEDGER
            assert entry.organization.PHASE == entry.final.PHASE == entry.contracts.PHASE == PHASE
            entry.base.settings = object()
            entry.base.service = object()
            entry.base.FactLimits = object()
            raise RuntimeError("fixture")
    for module, previous in before.items():
        assert vars(module) == previous


@pytest.fixture
def evidence(entry, monkeypatch):
    checked = contracts_helpers.evidence.__wrapped__(entry, monkeypatch)
    # Drop unused NULL tails in stored model responses only; all source, fact,
    # attribution/evidence fields and independent caller traces remain intact.
    for path in (entry.RESULTS / "responses").glob("*.json"):
        response = json.loads(path.read_text())
        content = json.loads(response["content"])
        if "fact_1" in content:
            content = {key: value for key, value in content.items() if value is not None}
        elif "theme_plan" in content:
            content = {key: value for key, value in content.items() if value is not None}
            content["theme_plan"] = {key: value for key, value in content["theme_plan"].items() if value is not None}
        response["content"] = json.dumps(content)
        helpers.write(path, response)
        contracts_helpers.refresh_call_hash(checked, int(path.stem), "responses")
    return checked


def test_checker_binds_sparse_raw_to_hash_verified_frozen_codec(evidence, entry):
    contracts_helpers.test_checker_reconstructs_raw_contracts_with_frozen_codec(evidence, entry)
    frozen = json.loads((entry.RESULTS / f"{PHASE}-provenance.json").read_text())
    assert set(frozen["runner_chain_sha256"]) == {"prefix", "contracts", "final", "organization", "runner",
        "checker", "contracts-checker", "checker-runner", "final-checker"}
    assert frozen["contracts_wrapper_sha256"] == helpers.sha(Path(entry.contracts.__file__).read_bytes())
    assert frozen["entrypoint_sha256"] == helpers.sha(ENTRY.read_bytes())


@pytest.mark.parametrize("mutation", ["extract-raw", "compose-raw", "trace-fact", "trace-theme", "audit-plan", "received"])
def test_raw_trace_and_audit_plan_disagreement_fails(evidence, mutation):
    contracts_helpers.test_checker_rejects_rehashed_raw_trace_plan_disagreement(evidence, mutation)


@pytest.mark.parametrize("artifact", ["provenance", "ledger", "payload", "response", "trace", "index", "result",
                                     "nested-ledger", "nested-trace"])
def test_duplicate_artifact_fields_fail(evidence, artifact):
    contracts_helpers.test_checker_rejects_duplicate_outer_and_nested_artifact_fields(evidence, artifact)


@pytest.mark.parametrize("location", ["ledger-ordinal", "ledger-sample_post", "response-ordinal"])
@pytest.mark.parametrize("bad", [True, 1.0])
def test_request_identity_is_type_sensitive(evidence, location, bad):
    contracts_helpers.test_checker_requires_exact_integer_request_identity(evidence, location, bad)


@pytest.mark.parametrize("location", ["frozen-sections", "frozen-total", "trace-calls", "stage-budget", "source-lines"])
def test_identity_counts_are_exact_integers(evidence, location):
    contracts_helpers.test_checker_rejects_noninteger_identity_counts(evidence, location)


@pytest.mark.parametrize("bad", [True, 1.0])
def test_audit_evidence_binding_is_type_sensitive(evidence, bad):
    contracts_helpers.test_audit_payload_evidence_binding_rejects_bool_and_float(evidence, bad)


@pytest.mark.parametrize("bad", [False, 0.0])
def test_trace_fact_binding_is_type_sensitive(evidence, bad):
    contracts_helpers.test_raw_extraction_trace_binding_rejects_wrong_numeric_types(evidence, bad)


@pytest.mark.parametrize("smuggle_fact", [False, True])
def test_received_invalid_contract_does_not_become_validated(evidence, smuggle_fact):
    contracts_helpers.test_received_invalid_extraction_never_becomes_validated_evidence(evidence, smuggle_fact)


def test_reordered_json_objects_keep_binding(evidence):
    contracts_helpers.test_binding_accepts_object_key_reordering_and_normal_json_arrays(evidence)


def test_frozen_codec_hash_precedes_loading(evidence, monkeypatch):
    contracts_helpers.test_checker_verifies_frozen_hash_before_codec_execution(evidence, monkeypatch)


@pytest.mark.parametrize("component", ["prefix", "contracts", "final", "organization", "runner", "checker",
                                        "contracts-checker", "checker-runner", "final-checker"])
def test_checker_checks_entire_effective_chain_before_frozen_loading(evidence, monkeypatch, tmp_path, component):
    path = evidence.CHECKER if component == "checker-runner" else (Path(evidence.__file__) if component == "checker"
                                                                 else evidence.CHAIN_PATHS[component])
    copy = tmp_path / f"drifted-{component}.py"
    copy.write_bytes(path.read_bytes() + b"\n# drift\n")
    if component == "checker-runner":
        monkeypatch.setattr(evidence, "CHECKER", copy)
    elif component == "checker":
        monkeypatch.setattr(evidence, "__file__", str(copy))
    else:
        monkeypatch.setitem(evidence.CHAIN_PATHS, component, copy)
    monkeypatch.setattr(evidence.checker, "frozen_helpers", lambda *args: pytest.fail("drift executed frozen codec"))
    with pytest.raises(ValueError, match="chain|Checker"):
        evidence.check_phase()


@pytest.mark.parametrize("artifact", ["rubric", "manifest", "source", "facts", "service", "config"])
def test_checker_validates_all_generation_bytes_before_codec_execution(evidence, monkeypatch, artifact):
    if artifact == "rubric":
        path = evidence.REPORT / "rubric.json"
    elif artifact == "manifest":
        path = evidence.checker.OLD / "corpus/manifest.json"
    elif artifact == "source":
        path = evidence.checker.OLD / "corpus/short.txt"
    else:
        path = evidence.RESULTS / f"{PHASE}-{artifact}.py"
    path.write_bytes(path.read_bytes() + b"\n# drift\n")
    monkeypatch.setattr(evidence.checker, "frozen_helpers", lambda *args: pytest.fail("unverified generation bytes executed codec"))
    with pytest.raises(ValueError, match="hash mismatch"):
        evidence.check_phase()


@pytest.mark.parametrize("identity,bad", [("ordinal", True), ("ordinal", 1.0), ("sample_post", True),
                                         ("sample_post", 1.0), ("sample", 1)])
def test_existing_request_identity_is_checked_before_next_send(entry, identity, bad):
    frozen = entry.snapshot()
    sent = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200, json={}))) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        client.sample = "short"
        client.post(helpers.URL, headers={}, json=helpers.payload(frozen))
        ledger = json.loads(entry.LEDGER.read_text())
        ledger["requests"][0][identity] = bad
        helpers.write(entry.LEDGER, ledger)
        before = entry.LEDGER.read_bytes()
        with pytest.raises(RuntimeError, match="ledger|identity"):
            client.post(helpers.URL, headers={}, json=helpers.payload(frozen, "compose", 8192))
    assert len(sent) == 1
    assert entry.LEDGER.read_bytes() == before
    assert not (entry.RESULTS / "payloads/02.json").exists()


@pytest.mark.parametrize("mutation,ordinal", [("model", 1), ("tokens", 1), ("float-tokens", 1), ("bool-tokens", 1),
    ("temperature", 1), ("options", 1), ("root-extra", 1), ("system-role", 1), ("system-content", 1), ("user-role", 1),
    ("system-extra", 1), ("user-extra", 1), ("tokens", 6), ("model", 13)])
def test_rehashed_actual_transport_mismatch_fails_before_codec(evidence, monkeypatch, mutation, ordinal):
    path = evidence.RESULTS / "payloads" / f"{ordinal:02d}.json"
    payload = json.loads(path.read_text())
    if mutation == "model":
        payload["model"] = "foreign-model"
    elif mutation == "tokens":
        payload["max_tokens"] = 1
    elif mutation == "float-tokens":
        payload["max_tokens"] = float(payload["max_tokens"])
    elif mutation == "bool-tokens":
        payload["max_tokens"] = True
    elif mutation == "temperature":
        payload["temperature"] = 1.7
    elif mutation == "options":
        payload["response_format"] = {"type": "json_object"}
    elif mutation == "root-extra":
        payload["unfrozen_transport_option"] = False
    elif mutation == "system-role":
        payload["messages"][0]["role"] = "user"
    elif mutation == "system-content":
        payload["messages"][0]["content"] = "unfrozen prompt"
    elif mutation == "user-role":
        payload["messages"][1]["role"] = "assistant"
    else:
        payload["messages"][0 if mutation == "system-extra" else 1]["unfrozen_message_field"] = False
    helpers.write(path, payload)
    contracts_helpers.refresh_call_hash(evidence, ordinal, "payloads")
    monkeypatch.setattr(evidence.checker, "frozen_helpers", lambda *args: pytest.fail("bad transport executed codec"))
    with pytest.raises(ValueError, match="Payload transport|Payload message"):
        evidence.check_phase()


@pytest.mark.parametrize("field,bad", [("model", "foreign-model"), ("max_tokens", 1), ("temperature", 1.7)])
def test_real_checker_refuses_rehashed_actual_transport(evidence, field, bad):
    # No checker-function replacement: before Fix1 this real checker accepted
    # the changed request and returned raw_contracts_bound=True.
    path = evidence.RESULTS / "payloads/01.json"
    payload = json.loads(path.read_text())
    payload[field] = bad
    helpers.write(path, payload)
    contracts_helpers.refresh_call_hash(evidence, 1, "payloads")
    with pytest.raises(ValueError, match="Payload transport"):
        evidence.check_phase()


@pytest.fixture
def option_evidence(evidence):
    # Supported response_format is frozen independently of output content. This
    # never injects rubric or producer answers; all 13 stored requests match it.
    path = evidence.RESULTS / f"{PHASE}-provenance.json"
    frozen = json.loads(path.read_text())
    frozen["options"] = {"response_format": {"type": "json_object"}}
    helpers.write(path, frozen)
    for path in (evidence.RESULTS / "payloads").glob("*.json"):
        payload = json.loads(path.read_text())
        payload.update(frozen["options"])
        helpers.write(path, payload)
        contracts_helpers.refresh_call_hash(evidence, int(path.stem), "payloads")
    return evidence


def test_legal_frozen_options_and_key_reordering_keep_binding(option_evidence):
    path = option_evidence.RESULTS / "payloads/01.json"
    payload = json.loads(path.read_text())
    payload = dict(reversed(list(payload.items())))
    payload["messages"] = [dict(reversed(list(message.items()))) for message in payload["messages"]]
    helpers.write(path, payload)
    contracts_helpers.refresh_call_hash(option_evidence, 1, "payloads")
    result = option_evidence.check_phase()
    assert [sample["validated_contract_stages"] for sample in result["samples"]] == [3, 3, 7]
    assert all(sample["raw_contracts_bound"] for sample in result["samples"])


@pytest.mark.parametrize("mutation", ["missing", "changed"])
def test_rehashed_frozen_options_must_match(option_evidence, monkeypatch, mutation):
    path = option_evidence.RESULTS / "payloads/13.json"
    payload = json.loads(path.read_text())
    if mutation == "missing":
        del payload["response_format"]
    else:
        payload["response_format"]["type"] = "text"
    helpers.write(path, payload)
    contracts_helpers.refresh_call_hash(option_evidence, 13, "payloads")
    monkeypatch.setattr(option_evidence.checker, "frozen_helpers", lambda *args: pytest.fail("bad options executed codec"))
    with pytest.raises(ValueError, match="Payload transport"):
        option_evidence.check_phase()
