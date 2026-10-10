"""Pure audit-contract behavior; no HTTP, settings, database, or test fixtures."""

import copy
import importlib
import importlib.util
import json
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.services.summary_facts import FactLimits, FactValidationError, SourcePart, parse_audit, parse_facts
from app.services.summary_normalization import NormalizationError, normalize_composition


FLAGS = {
    "supported": True,
    "qualifiers_preserved": True,
    "attribution_preserved": True,
    "scope_preserved": True,
}
RESULTS = Path(__file__).resolve().parents[2] / "docs/acceptance-reports/2026-10-08-grounded-summary-clause/results"


def contract():
    # Until implemented, each feature fails as an assertion, not an import error.
    assert importlib.util.find_spec("app.services.summary_audit_contract") is not None, "audit contract is missing"
    return importlib.import_module("app.services.summary_audit_contract")


def compact():
    return {
        "additional_facts": [],
        "output": {
            "summary": {"text": "  Do not recalculate area after radius = radius + 1.\n", "assertions": dict(FLAGS)},
            "point_1": {
                "topic": "Binding",
                "text": " radius 2.2 becomes 3.2; area does not change. ",
                "fact_ids": ["F1", "UNKNOWN", "F1"],
                "assertions": dict(FLAGS),
            },
        },
    }


def legacy():
    return {
        "additional_facts": [],
        "output": {
            "summary": [{"text": "No automatic change.", "fact_ids": ["F1"]}],
            "key_points": [{"topic": "Binding", "text": "Keep area.", "fact_ids": ["F1"]}],
        },
        "checks": [{"item_id": "S1", **FLAGS}, {"item_id": "P1", **FLAGS}],
    }


def test_compact_maps_same_item_assertions_and_preserves_every_text_and_hint():
    payload = compact()
    payload["output"]["summary"]["fact_ids"] = "hint-summary"
    payload["output"]["point_2"] = {"topic": "Afterward", "text": "Never round 3.2.", "assertions": dict(FLAGS)}
    payload["output"]["point_3"] = None
    before = copy.deepcopy(payload)

    envelope = contract().parse_audit_contract(payload, FactLimits(max_summary_chars=800))

    assert envelope.protocol == "compact"
    assert envelope.additional_facts == []
    assert envelope.composition == {
        "summary": [{"text": "  Do not recalculate area after radius = radius + 1.\n", "fact_ids": "hint-summary"}],
        "point_1": {"topic": "Binding", "text": " radius 2.2 becomes 3.2; area does not change. ",
                    "fact_ids": ["F1", "UNKNOWN", "F1"]},
        "point_2": {"topic": "Afterward", "text": "Never round 3.2."},
        "point_3": None,
    }
    assert envelope.checks == [
        {"item_id": "S1", **FLAGS}, {"item_id": "P1", **FLAGS}, {"item_id": "P2", **FLAGS},
    ]
    assert payload == before
    draft = normalize_composition(envelope.composition, FactLimits(max_summary_chars=800), final=True)
    assert draft.summary[0].text == before["output"]["summary"]["text"]
    assert draft.key_points[0].hint_ids == ("F1", "UNKNOWN", "F1")


def test_false_is_preserved_then_existing_semantic_audit_rejects_it():
    source = SourcePart("part1", "Area does not change.")
    facts = parse_facts({"facts": [{"topic": "Area", "claim": source.text, "evidence": [1],
                                    "attribution": "source", "importance": "core"}]}, source, FactLimits(), "F")
    payload = compact()
    payload["output"]["summary"] = {"text": source.text, "fact_ids": ["F1"], "assertions": dict(FLAGS)}
    payload["output"]["point_1"] = {"topic": "Area", "text": source.text, "fact_ids": ["F1"],
                                       "assertions": {**FLAGS, "scope_preserved": False}}
    envelope = contract().parse_audit_contract(payload, FactLimits())
    assert envelope.checks[1]["scope_preserved"] is False
    with pytest.raises(FactValidationError, match="^audit_not_supported$"):
        parse_audit({"additional_facts": envelope.additional_facts,
                     "output": {"summary": envelope.composition["summary"],
                                "key_points": [envelope.composition["point_1"]]},
                     "checks": envelope.checks}, [source], facts, FactLimits())


def test_legacy_output_checks_and_additions_are_fresh_equal_copies():
    payload = legacy()
    payload["additional_facts"] = [{"topic": "Unverified", "evidence": [1]}]
    payload["checks"][0]["supported"] = False
    envelope = contract().parse_audit_contract(payload, FactLimits())
    assert envelope.protocol == "legacy"
    assert envelope.composition == payload["output"]
    assert envelope.checks == payload["checks"]
    assert envelope.additional_facts == payload["additional_facts"]
    payload["output"]["summary"][0]["fact_ids"].append("later")
    payload["checks"][0]["supported"] = True
    payload["additional_facts"][0]["evidence"].append(2)
    assert envelope.composition["summary"][0]["fact_ids"] == ["F1"]
    assert envelope.checks[0]["supported"] is False
    assert envelope.additional_facts[0]["evidence"] == [1]
    with pytest.raises(FrozenInstanceError):
        envelope.protocol = "changed"


@pytest.mark.parametrize("ordinal", [3, 6])
def test_stored_short_and_medium_legacy_raw_keep_exact_output_and_assertions(ordinal):
    raw = json.loads((RESULTS / f"responses/{ordinal:02}.json").read_text(encoding="utf-8"))["content"]
    expected = json.loads(raw)
    envelope = contract().parse_audit_contract(raw, FactLimits(max_summary_chars=800))
    assert envelope.protocol == "legacy"
    assert envelope.composition == expected["output"]
    assert envelope.checks == expected["checks"]
    assert envelope.additional_facts == expected["additional_facts"]


def test_stored_invalid_long_audit_remains_invalid_json_without_repairs():
    raw = json.loads((RESULTS / "responses/13.json").read_text(encoding="utf-8"))["content"]
    api = contract()
    with pytest.raises(api.AuditContractError, match="^invalid_json$"):
        api.read_audit_contract(raw)
    with pytest.raises(api.AuditContractError, match="^invalid_json$"):
        api.parse_audit_contract(raw, FactLimits())


def test_reader_preserves_unknown_fields_for_source_validation_before_contract():
    payload = {"additional_facts": [{"source_id": "UNKNOWN", "evidence": [999]}],
               "output": "malformed", "unknown": {"keep": [False, "raw"]}}
    decoded = contract().read_audit_contract(json.dumps(payload))
    assert decoded == payload
    decoded["unknown"]["keep"].append("changed")
    assert payload["unknown"]["keep"] == [False, "raw"]


def test_reader_copies_dict_input_and_accepts_only_a_complete_outer_fence():
    payload = compact()
    api = contract()
    assert api.read_audit_contract("```JSON\r\n" + json.dumps(payload) + "\r\n```") == payload
    decoded = api.read_audit_contract(payload)
    decoded["output"]["point_1"]["fact_ids"].append("changed")
    assert payload["output"]["point_1"]["fact_ids"] == ["F1", "UNKNOWN", "F1"]


@pytest.mark.parametrize("raw,reason", [
    ('{"additional_facts":[],"additional_facts":[],"output":{}}', "duplicate_json_field"),
    ('{"outer":{"x":1,"x":2}}', "duplicate_json_field"),
    ('prefix {"additional_facts":[],"output":{}}', "invalid_json"),
    ('{"additional_facts":[],"output":{}} suffix', "invalid_json"),
    ('```json\n{}\n```\ntrailing', "invalid_json"),
    ('{"x":NaN}', "invalid_json"),
    ('{"x":Infinity}', "invalid_json"),
    ('[]', "invalid_payload"),
])
def test_reader_rejects_lossy_json_extraction_duplicate_keys_and_constants(raw, reason):
    api = contract()
    with pytest.raises(api.AuditContractError, match=f"^{reason}$"):
        api.read_audit_contract(raw)


@pytest.mark.parametrize("location", ["summary", "point_1"])
@pytest.mark.parametrize("bad", [1, 0, "true", None, [], {}])
def test_compact_assertions_require_actual_booleans(location, bad):
    payload = compact()
    payload["output"][location]["assertions"]["supported"] = bad
    api = contract()
    with pytest.raises(api.AuditContractError, match="^invalid_fields$"):
        api.parse_audit_contract(payload, FactLimits())


@pytest.mark.parametrize("change", ["missing_flag", "extra_flag", "missing_assertions"])
def test_compact_assertions_have_exact_required_fields(change):
    payload = compact()
    if change == "missing_flag":
        del payload["output"]["point_1"]["assertions"]["scope_preserved"]
    elif change == "extra_flag":
        payload["output"]["point_1"]["assertions"]["approved"] = True
    else:
        del payload["output"]["point_1"]["assertions"]
    api = contract()
    with pytest.raises(api.AuditContractError, match="^invalid_fields$"):
        api.parse_audit_contract(payload, FactLimits())


@pytest.mark.parametrize("change,reason", [
    ("extra_outer", "invalid_fields"), ("compact_with_checks", "invalid_fields"),
    ("legacy_nested_assertions", "invalid_fields"), ("legacy_missing_checks", "invalid_fields"),
    ("array_points", "invalid_fields"), ("summary_array", "invalid_fields"),
    ("summary_string", "invalid_fields"), ("summary_topic", "invalid_fields"),
    ("point_missing_topic", "invalid_fields"), ("point_missing_text", "invalid_fields"),
    ("unknown_slot", "invalid_fields"), ("point_zero", "invalid_fields"),
    ("point_eight", "too_many_points"), ("point_twenty_seven", "too_many_points"),
    ("hole", "nontrailing_empty_slot"), ("no_point", "invalid_count"),
    ("null_only", "invalid_count"),
])
def test_protocol_routes_do_not_guess_drop_overflow_or_mix_assertions(change, reason):
    payload = compact()
    output = payload["output"]
    point = copy.deepcopy(output["point_1"])
    if change == "extra_outer": payload["checks_extra"] = []
    elif change == "compact_with_checks": payload["checks"] = [{"item_id": "S1", **FLAGS}]
    elif change == "legacy_nested_assertions":
        payload = legacy()
        payload["output"]["summary"][0]["assertions"] = dict(FLAGS)
    elif change == "legacy_missing_checks":
        payload = legacy()
        del payload["checks"]
    elif change == "array_points": output["key_points"] = [output.pop("point_1")]
    elif change == "summary_array": output["summary"] = [output["summary"]]
    elif change == "summary_string": output["summary"] = "missing assertions"
    elif change == "summary_topic": output["summary"]["topic"] = "unexpected"
    elif change == "point_missing_topic": del point["topic"]; output["point_1"] = point
    elif change == "point_missing_text": del point["text"]; output["point_1"] = point
    elif change == "unknown_slot": output["point_extra"] = point
    elif change == "point_zero": output["point_0"] = point
    elif change == "point_eight": output["point_8"] = point
    elif change == "point_twenty_seven": output["point_27"] = point
    elif change == "hole": output["point_2"] = None; output["point_3"] = point
    elif change == "no_point": del output["point_1"]
    elif change == "null_only": output["point_1"] = None
    api = contract()
    with pytest.raises(api.AuditContractError, match=f"^{reason}$"):
        api.parse_audit_contract(payload, FactLimits())


@pytest.mark.parametrize("bad", ["true", 1, None])
def test_legacy_flags_are_strict_without_guessing_or_changing_values(bad):
    payload = legacy()
    payload["checks"][0]["supported"] = bad
    api = contract()
    with pytest.raises(api.AuditContractError, match="^invalid_fields$"):
        api.parse_audit_contract(payload, FactLimits())


def test_adapter_preserves_overlong_text_for_final_normalizer_after_bank_validation():
    payload = compact()
    payload["output"]["summary"]["text"] = "S" * 801
    payload["output"]["point_1"]["text"] = "P" * 241
    limits = FactLimits(max_summary_chars=800)
    envelope = contract().parse_audit_contract(payload, limits)
    assert envelope.composition["summary"][0]["text"] == "S" * 801
    assert envelope.composition["point_1"]["text"] == "P" * 241
    with pytest.raises(NormalizationError, match="^summary_too_long$"):
        normalize_composition(envelope.composition, limits, final=True)
    payload["output"]["summary"]["text"] = "S" * 800
    envelope = contract().parse_audit_contract(payload, limits)
    with pytest.raises(NormalizationError, match="^point_too_long$"):
        normalize_composition(envelope.composition, limits, final=True)


def test_configured_finite_slot_limit_is_used_and_hints_do_not_select_checks():
    payload = compact()
    payload["output"]["point_2"] = {"topic": "Other", "text": "Different condition.",
                                      "fact_ids": ["P1", "S1"], "assertions": {**FLAGS, "supported": False}}
    envelope = contract().parse_audit_contract(payload, FactLimits(max_items=2))
    assert [check["item_id"] for check in envelope.checks] == ["S1", "P1", "P2"]
    assert envelope.checks[2]["supported"] is False
    payload["output"]["point_3"] = copy.deepcopy(payload["output"]["point_1"])
    with pytest.raises(contract().AuditContractError, match="^too_many_points$"):
        contract().parse_audit_contract(payload, FactLimits(max_items=2))


def test_maximum_final_boundaries_and_reverse_input_key_order_keep_check_ownership():
    payload = compact()
    payload["output"]["summary"]["text"] = "S" * 800
    payload["output"] = {
        **{f"point_{index}": {"topic": f"Topic {index}", "text": str(index) * 240,
                              "assertions": dict(FLAGS)} for index in range(7, 0, -1)},
        "summary": payload["output"]["summary"],
    }
    limits = FactLimits(max_summary_chars=800)
    envelope = contract().parse_audit_contract(payload, limits)
    draft = normalize_composition(envelope.composition, limits, final=True)
    assert len(draft.key_points) == 7
    assert [item.text[0] for item in draft.key_points] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [check["item_id"] for check in envelope.checks] == ["S1", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]


def test_legacy_overflow_is_retained_for_strict_final_normalization():
    payload = legacy()
    payload["output"]["key_points"] = [{"topic": "T", "text": f"Point {index}.", "fact_ids": ["F1"]}
                                        for index in range(27)]
    envelope = contract().parse_audit_contract(payload, FactLimits())
    assert len(envelope.composition["key_points"]) == 27
    with pytest.raises(NormalizationError, match="^too_many_points$"):
        normalize_composition(envelope.composition, FactLimits(), final=True)


@pytest.mark.parametrize("payload", [None, [], "null", "false"])
def test_reader_errors_have_bounded_codes_without_raw_payloads(payload):
    api = contract()
    with pytest.raises(api.AuditContractError, match="^invalid_payload$"):
        api.read_audit_contract(payload)


def test_relative_import_supports_an_isolated_frozen_module_namespace(monkeypatch):
    api = contract()
    package = types.ModuleType("frozen_audit_test")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, package.__name__, package)
    monkeypatch.setitem(sys.modules, "frozen_audit_test.summary_facts", importlib.import_module("app.services.summary_facts"))
    spec = importlib.util.spec_from_file_location("frozen_audit_test.summary_audit_contract", api.__file__)
    frozen = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, frozen)
    spec.loader.exec_module(frozen)
    envelope = frozen.parse_audit_contract(compact(), FactLimits())
    assert envelope.protocol == "compact"
    assert envelope.checks[0] == {"item_id": "S1", **FLAGS}
