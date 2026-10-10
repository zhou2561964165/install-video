"""Behavior contracts for finite extraction and global composition plans."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json

import pytest

from app.services import summary_facts as codec


def extraction_parser():
    parser = getattr(codec, "parse_extraction", None)
    assert callable(parser), "finite extraction parser must be available"
    return parser


def source():
    return codec.SourcePart("C2", "Noor introduces policy.\nRelease requires a clean audit.\nA failed audit stops release.", 100)


def fact_record(**changes):
    return {"topic": "Release", "claim": "Release requires a clean audit.",
            "evidence": [2], "attribution": "Noor", "importance": "core"} | changes


def extraction(count=12, used=1):
    return {f"fact_{i}": fact_record(claim=f"Requirement {i}.") if i <= used else None
            for i in range(1, count + 1)}


@pytest.mark.parametrize("count", [1, 2, 12])
def test_extraction_retains_all_configured_slots_in_order_with_exact_source(count):
    parsed = extraction_parser()(extraction(count, count), source(),
                                 codec.FactLimits(max_facts_per_chunk=count), "C2F")
    assert len(parsed) == count
    assert [item.id for item in parsed] == [f"C2F{i}" for i in range(1, count + 1)]
    assert [item.claim for item in parsed] == [f"Requirement {i}." for i in range(1, count + 1)]
    assert all(item.source_id == "C2" and item.evidence_indices == (2,) for item in parsed)
    assert parsed[0].quote == "Release requires a clean audit."
    assert (parsed[0].start, parsed[0].end) == (124, 155)
    assert (parsed[0].attribution_start, parsed[0].attribution_end) == (100, 104)
    assert parsed[0].source_sha256 == hashlib.sha256(source().text.encode()).hexdigest()


def test_extraction_accepts_json_and_only_trailing_unused_slots():
    parsed = extraction_parser()(json.dumps(extraction(used=2)), source(), codec.FactLimits(), "F")
    assert tuple(item.id for item in parsed) == ("F1", "F2")
    assert tuple(item.claim for item in parsed) == ("Requirement 1.", "Requirement 2.")


@pytest.mark.parametrize("change", ["extra_13", "missing_first", "missing_active", "first_empty", "all_empty", "gap", "legacy", "extra_field"])
def test_extraction_rejects_capacity_or_slot_shape_instead_of_dropping_facts(change):
    payload = extraction()
    if change == "extra_13":
        payload["fact_13"] = fact_record()
    elif change == "missing_first":
        del payload["fact_1"]
    elif change == "missing_active":
        payload = extraction(used=3)
        del payload["fact_2"]
    elif change == "first_empty":
        payload["fact_1"], payload["fact_2"] = None, fact_record()
    elif change == "all_empty":
        payload["fact_1"] = None
    elif change == "gap":
        payload["fact_3"] = fact_record()
    elif change == "legacy":
        payload = {"facts": [fact_record()]}
    else:
        payload["fact_1"]["source_id"] = "unknown"
    parser = extraction_parser()
    with pytest.raises(codec.FactValidationError):
        parser(payload, source(), codec.FactLimits(), "F")


@pytest.mark.parametrize("changes", [
    {"evidence": [0]}, {"evidence": [4]}, {"evidence": [True]}, {"evidence": [2, 2]},
    {"evidence": []}, {"evidence": "2"}, {"attribution": "Mira"},
    {"attribution": "NOOR"}, {"importance": "critical"}, {"claim": "x" * 601},
    {"quote": "invented"},
])
def test_extraction_reuses_original_evidence_attribution_and_field_bounds(changes):
    payload = extraction()
    payload["fact_1"] = fact_record(**changes)
    parser = extraction_parser()
    with pytest.raises(codec.FactValidationError):
        parser(payload, source(), codec.FactLimits(), "F")


@pytest.mark.parametrize("invalid_source", [None, codec.SourcePart("bad/id", "text"),
    codec.SourcePart("C2", ""), codec.SourcePart("C2", "text", -1)])
def test_extraction_rejects_invalid_caller_source(invalid_source):
    parser = extraction_parser()
    with pytest.raises(codec.FactValidationError):
        parser(extraction(), invalid_source, codec.FactLimits(), "F")


@pytest.mark.parametrize("level", ["slot", "fact"])
def test_extraction_rejects_duplicate_json_fields_at_every_level(level):
    if level == "slot":
        payload = json.dumps(extraction())[:-1] + ',"fact_1":null}'
    else:
        payload = json.dumps(extraction()).replace('"importance": "core"', '"importance":"core","importance":"support"')
    parser = extraction_parser()
    with pytest.raises(codec.FactValidationError):
        parser(payload, source(), codec.FactLimits(), "F")


def test_extraction_rejects_overlong_generated_identity():
    parser = extraction_parser()
    with pytest.raises(codec.FactValidationError):
        parser(extraction(), source(), codec.FactLimits(), "F" * 64)


def composition_parser():
    parser = getattr(codec, "parse_planned_composition", None)
    assert callable(parser), "planned composition parser must be available"
    return parser


def relation_facts():
    limits = codec.FactLimits()
    first = codec.SourcePart("C1", "Noor sets release policy.\nRelease requires a clean audit.")
    second = codec.SourcePart("C2", "A failed audit stops release.\nBudget is 48000.\nTraining lasts six weeks.", 100)
    records = codec.parse_facts({"facts": [fact_record(attribution="Noor")]}, first, limits, "F")
    records += codec.parse_facts({"facts": [
        fact_record(claim="A failed audit stops release.", evidence=[1], attribution="source"),
        fact_record(topic="Budget", claim="Budget is 48000.", evidence=[2], attribution="source", importance="support"),
        fact_record(topic="Training", claim="Training lasts six weeks.", evidence=[3], attribution="source"),
    ]}, second, limits, "G")
    return records


def theme_record(**changes):
    return {"topic": "Release policy", "principle": "Release requires a clean audit.",
            "conditions": ["The audit must be clean."],
            "consequences": ["A failed audit stops release."],
            "fact_ids": ["F1", "G1"]} | changes


def planned_composition(count=7):
    return {"summary": [{"text": "Release requires a clean audit; failure stops release.", "fact_ids": ["F1", "G1"]}],
            "point_1": {"topic": "Release policy", "text": "Release requires a clean audit; failure stops release.", "fact_ids": ["F1", "G1"]},
            **{f"point_{i}": None for i in range(2, count + 1)},
            "theme_plan": {"theme_1": theme_record(), **{f"theme_{i}": None for i in range(2, count + 1)}}}


@pytest.mark.parametrize("count", [1, 2, 7])
def test_planned_composition_preserves_cross_source_principle_condition_and_consequence(count):
    parsed = composition_parser()(planned_composition(count), relation_facts(), codec.FactLimits(max_items=count))
    assert parsed.candidate.public_summary == "Release requires a clean audit; failure stops release."
    assert parsed.candidate.key_points[0].fact_ids == ("F1", "G1")
    assert len(parsed.themes) == 1
    theme = parsed.themes[0]
    assert theme.id == "T1"
    assert theme.topic == "Release policy"
    assert theme.principle == "Release requires a clean audit."
    assert theme.conditions == ("The audit must be clean.",)
    assert theme.consequences == ("A failed audit stops release.",)
    assert theme.fact_ids == ("F1", "G1")
    with pytest.raises(FrozenInstanceError):
        theme.topic = "Changed"
    with pytest.raises(FrozenInstanceError):
        parsed.themes = ()


def test_planned_composition_assigns_ordered_ids_and_allows_shared_fact_context():
    payload = planned_composition()
    payload["theme_plan"]["theme_2"] = theme_record(topic="Resources", principle="Budget funds training.",
        conditions=[], consequences=[], fact_ids=["G1", "G2", "G3"])
    payload["point_2"] = {"topic": "Resources", "text": "Budget funds six weeks of training.", "fact_ids": ["G1", "G2", "G3"]}
    parsed = composition_parser()(json.dumps(payload), relation_facts(), codec.FactLimits())
    assert tuple(item.id for item in parsed.themes) == ("T1", "T2")
    assert tuple(item.id for item in parsed.candidate.key_points) == ("P1", "P2")
    assert parsed.themes[1].conditions == parsed.themes[1].consequences == ()
    assert parsed.themes[1].fact_ids == ("G1", "G2", "G3")


@pytest.mark.parametrize("change", ["extra_top", "extra_point_slot", "missing_active_point", "extra_theme_slot",
    "missing_summary", "missing_theme_plan", "missing_point_1", "missing_theme_1", "missing_active_theme",
    "first_empty", "all_empty", "theme_gap", "point_gap", "too_many_themes",
    "too_many_points", "model_id", "extra_theme_field", "missing_theme_field"])
def test_planned_composition_rejects_unknown_fields_and_mismatched_slot_prefixes(change):
    payload = planned_composition()
    if change == "extra_top":
        payload["note"] = "Discard me"
    elif change == "extra_point_slot":
        payload["point_8"] = None
    elif change == "missing_active_point":
        payload["point_2"] = deepcopy(payload["point_1"])
        payload["point_3"] = deepcopy(payload["point_1"])
        del payload["point_2"]
    elif change == "extra_theme_slot":
        payload["theme_plan"]["theme_8"] = theme_record()
    elif change == "missing_summary":
        del payload["summary"]
    elif change == "missing_theme_plan":
        del payload["theme_plan"]
    elif change == "missing_point_1":
        del payload["point_1"]
    elif change == "missing_theme_1":
        del payload["theme_plan"]["theme_1"]
    elif change == "missing_active_theme":
        payload["theme_plan"]["theme_3"] = theme_record()
        del payload["theme_plan"]["theme_2"]
    elif change == "first_empty":
        payload["theme_plan"]["theme_1"] = None
        payload["theme_plan"]["theme_2"] = theme_record()
    elif change == "all_empty":
        payload["theme_plan"]["theme_1"] = None
        payload["point_1"] = None
    elif change == "theme_gap":
        payload["theme_plan"]["theme_3"] = theme_record()
    elif change == "point_gap":
        payload["point_3"] = deepcopy(payload["point_1"])
    elif change == "too_many_themes":
        payload["theme_plan"]["theme_2"] = theme_record()
    elif change == "too_many_points":
        payload["point_2"] = {"topic": "Budget", "text": "Budget is 48000.", "fact_ids": ["G2"]}
    elif change == "model_id":
        payload["theme_plan"]["theme_1"]["id"] = "T77"
    elif change == "extra_theme_field":
        payload["theme_plan"]["theme_1"]["source_id"] = "C1"
    else:
        del payload["theme_plan"]["theme_1"]["principle"]
    parser = composition_parser()
    with pytest.raises(codec.FactValidationError):
        parser(payload, relation_facts(), codec.FactLimits())


def test_planned_composition_rejects_point_theme_prefix_count_mismatch():
    payload = planned_composition()
    payload["point_2"] = {"topic": "Budget", "text": "Budget is 48000.", "fact_ids": ["G2"]}
    with pytest.raises(codec.FactValidationError, match="theme_point_count_mismatch"):
        composition_parser()(payload, relation_facts(), codec.FactLimits())


@pytest.mark.parametrize("field,value", [
    ("topic", ""), ("topic", "x" * 121), ("principle", " "), ("principle", "x" * 601),
    ("conditions", "condition"), ("conditions", [""]), ("conditions", ["x" * 241]),
    ("conditions", ["condition"] * 8), ("conditions", [None]),
    ("consequences", "outcome"), ("consequences", [" "]), ("consequences", ["x" * 241]),
    ("consequences", ["outcome"] * 8),
    ("fact_ids", []), ("fact_ids", ["unknown"]), ("fact_ids", ["F1", "F1"]),
    ("fact_ids", [True]), ("fact_ids", "F1"),
])
def test_planned_composition_rejects_invalid_theme_text_counts_or_references(field, value):
    payload = planned_composition()
    payload["theme_plan"]["theme_1"][field] = value
    parser = composition_parser()
    with pytest.raises(codec.FactValidationError):
        parser(payload, relation_facts(), codec.FactLimits())


def test_planned_composition_accepts_complete_theme_text_at_limits_without_truncation():
    payload = planned_composition()
    payload["theme_plan"]["theme_1"] = theme_record(topic="t" * 120, principle="p" * 600,
        conditions=["c" * 240] * 7, consequences=["o" * 240] * 7)
    parsed = composition_parser()(payload, relation_facts(), codec.FactLimits())
    assert parsed.themes[0].principle == "p" * 600
    assert parsed.themes[0].conditions == ("c" * 240,) * 7
    assert parsed.themes[0].consequences == ("o" * 240,) * 7


@pytest.mark.parametrize("change", ["outside_allocation", "unknown_point", "unknown_summary", "repeated_point_refs"])
def test_planned_composition_preserves_point_allocation_and_original_candidate_reference_contract(change):
    payload = planned_composition()
    if change == "outside_allocation":
        payload["point_1"]["fact_ids"] = ["G2"]
    elif change == "unknown_point":
        payload["point_1"]["fact_ids"] = ["unknown"]
    elif change == "unknown_summary":
        payload["summary"][0]["fact_ids"] = ["unknown"]
    else:
        payload["theme_plan"]["theme_2"] = theme_record()
        payload["point_2"] = {"topic": "Other", "text": "The policy controls release.", "fact_ids": ["F1", "G1"]}
    parser = composition_parser()
    with pytest.raises(codec.FactValidationError):
        parser(payload, relation_facts(), codec.FactLimits())


@pytest.mark.parametrize("level", ["top", "theme_plan", "theme", "point"])
def test_planned_composition_rejects_duplicate_json_fields_before_normalization(level):
    payload = json.dumps(planned_composition())
    if level == "top":
        payload = payload[:-1] + ',"summary":[]}'
    elif level == "theme_plan":
        payload = payload.replace('"theme_1":', '"theme_1":null,"theme_1":', 1)
    elif level == "theme":
        payload = payload.replace('"principle":', '"principle":"wrong","principle":', 1)
    else:
        payload = payload.replace('"point_1":', '"point_1":null,"point_1":', 1)
    parser = composition_parser()
    with pytest.raises(codec.FactValidationError):
        parser(payload, relation_facts(), codec.FactLimits())


def test_planned_composition_defers_missing_core_even_when_allocated_in_theme():
    payload = planned_composition()
    payload["theme_plan"]["theme_1"]["fact_ids"].append("G3")
    parsed = composition_parser()(payload, relation_facts(), codec.FactLimits())
    assert "G3" in parsed.themes[0].fact_ids
    assert "G3" not in parsed.candidate.summary[0].fact_ids
    assert "G3" not in parsed.candidate.key_points[0].fact_ids
    output = {"summary": payload["summary"], "key_points": [payload["point_1"]]}
    audit_payload = {"additional_facts": [], "output": output, "checks": []}
    sources = [codec.SourcePart("C1", "Noor sets release policy.\nRelease requires a clean audit."),
               codec.SourcePart("C2", "A failed audit stops release.\nBudget is 48000.\nTraining lasts six weeks.", 100)]
    with pytest.raises(codec.FactValidationError, match="missing_core_fact"):
        codec.parse_audit(audit_payload, sources, relation_facts(), codec.FactLimits())


@pytest.mark.parametrize("change", ["summary_length", "summary_count", "point_length"])
def test_planned_composition_keeps_preliminary_budget_and_original_final_hard_limits(change):
    payload = planned_composition()
    limits = codec.FactLimits(max_summary_chars=800)
    if change == "summary_length":
        payload["summary"][0]["text"] = "s" * 801
    elif change == "summary_count":
        payload["summary"] = [{"text": f"Claim {i}", "fact_ids": ["F1"]} for i in range(8)]
    else:
        payload["point_1"]["text"] = "p" * 241
    parsed = composition_parser()(payload, relation_facts(), limits)
    output = {"summary": [{"text": item.text, "fact_ids": list(item.fact_ids)} for item in parsed.candidate.summary],
              "key_points": [{"topic": item.topic, "text": item.text, "fact_ids": list(item.fact_ids)} for item in parsed.candidate.key_points]}
    with pytest.raises(codec.FactValidationError):
        codec.parse_candidate(output, relation_facts(), limits)


@pytest.mark.parametrize("outer", ["dict", "raw_json"])
def test_extraction_rejects_nested_json_string_fact_objects(outer):
    payload = extraction()
    payload["fact_1"] = json.dumps(payload["fact_1"])
    if outer == "raw_json":
        payload = json.dumps(payload)
    with pytest.raises(codec.FactValidationError):
        extraction_parser()(payload, source(), codec.FactLimits(), "F")


@pytest.mark.parametrize("outer", ["dict", "raw_json"])
@pytest.mark.parametrize("field", ["theme_plan", "theme_1", "point_1", "summary_claim"])
def test_planned_composition_rejects_nested_json_string_objects(field, outer):
    payload = planned_composition()
    if field == "theme_1":
        payload["theme_plan"]["theme_1"] = json.dumps(payload["theme_plan"]["theme_1"])
    elif field == "summary_claim":
        payload["summary"][0] = json.dumps(payload["summary"][0])
    else:
        payload[field] = json.dumps(payload[field])
    if outer == "raw_json":
        payload = json.dumps(payload)
    with pytest.raises(codec.FactValidationError):
        composition_parser()(payload, relation_facts(), codec.FactLimits())


@pytest.mark.parametrize("interface", ["facts", "composition", "candidate"])
def test_existing_parsers_preserve_nested_json_object_compatibility(interface):
    if interface == "facts":
        parsed = codec.parse_facts({"facts": [json.dumps(fact_record())]}, source(), codec.FactLimits(), "F")
        assert parsed[0].claim == "Release requires a clean audit."
        assert parsed[0].id == "F1"
    else:
        payload = planned_composition()
        point = json.dumps(payload["point_1"])
        payload["summary"][0] = json.dumps(payload["summary"][0])
        if interface == "composition":
            del payload["theme_plan"]
            payload["point_1"] = point
            parsed = codec.parse_composition(payload, relation_facts(), codec.FactLimits())
        else:
            parsed = codec.parse_candidate({"summary": payload["summary"], "key_points": [point]}, relation_facts(), codec.FactLimits())
        assert parsed.public_summary == "Release requires a clean audit; failure stops release."
        assert parsed.key_points[0].fact_ids == ("F1", "G1")
