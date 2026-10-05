import hashlib
from dataclasses import replace

import pytest

from app.services.summary_facts import (
    FactLimits, FactValidationError, SourcePart, parse_facts, parse_candidate,
    parse_audit, split_sentences,
)


TEXT = "Noor stops release unless the audit is clean.\nBudget is 48000.\nTraining lasts six weeks."


def part():
    return SourcePart("C1", TEXT)


def fact(**changes):
    value = {
        "topic": "Release", "claim": "Noor stops release unless the audit is clean.",
        "evidence": [1], "attribution": "source", "importance": "core",
    }
    return value | changes


def test_split_sentences_produces_exact_ordered_line_slices():
    sentences = split_sentences(part())
    assert [s.id for s in sentences] == ["C1_s1", "C1_s2", "C1_s3"]
    assert sentences[0].text == "Noor stops release unless the audit is clean."
    assert sentences[1].text == "Budget is 48000."
    assert sentences[2].text == "Training lasts six weeks."
    assert sentences[0].start == 0 and sentences[0].end == len(sentences[0].text)
    assert TEXT[sentences[0].start:sentences[0].end] == sentences[0].text
    assert TEXT[sentences[2].start:sentences[2].end] == sentences[2].text


def test_evidence_indices_map_to_original_global_span_and_caller_identity():
    source = SourcePart("C2", "Intro.\nNoor stops release unless the audit is clean.\nEnd.", 100)
    parsed = parse_facts({"facts": [fact(evidence=[2])]}, source, FactLimits(), "C2F")
    item = parsed[0]
    assert item.id == "C2F1"
    assert item.quote == "Noor stops release unless the audit is clean."
    assert (item.start, item.end) == (source.global_start + source.text.index("Noor"),
                                      source.global_start + source.text.index("Noor") + len(item.quote))
    assert item.source_id == "C2"
    assert item.source_sha256 == hashlib.sha256(source.text.encode()).hexdigest()
    assert item.evidence_indices == (2,)


def test_contiguous_multi_line_evidence_joins_exact_source_text():
    source = part()
    item = parse_facts({"facts": [fact(topic="Two", evidence=[1, 2])]}, source, FactLimits(), "F")[0]
    assert item.evidence_indices == (1, 2)
    assert source.text[item.start:item.end] == item.quote
    assert item.quote == "Noor stops release unless the audit is clean.\nBudget is 48000."
    assert item.end - item.start == len(item.quote)


def test_out_of_order_evidence_is_canonicalized_to_ascending():
    item = parse_facts({"facts": [fact(topic="Two", evidence=[3, 1, 2])]},
                       part(), FactLimits(), "F")[0]
    assert item.evidence_indices == (1, 2, 3)
    assert item.quote == TEXT


@pytest.mark.parametrize("evidence", [
    [99], [], [1, 1], [True], "1", [0], [-1],
])
def test_invalid_evidence_is_rejected(evidence):
    with pytest.raises(FactValidationError):
        parse_facts({"facts": [fact(evidence=evidence)]}, part(), FactLimits(), "F")


def test_non_contiguous_evidence_is_accepted_and_joined():
    item = parse_facts({"facts": [fact(topic="Two", evidence=[1, 3])]}, part(), FactLimits(), "F")[0]
    assert item.evidence_indices == (1, 3)
    assert item.quote == "Noor stops release unless the audit is clean.\nTraining lasts six weeks."


@pytest.mark.parametrize("changes", [
    {"importance": "critical"}, {"attribution": "Mira"}, {"evidence": "1"},
    {"quote": "Noor stops release unless the audit is clean."},
    {"qualifiers": ["unless"]},
])
def test_invalid_or_legacy_fields_are_rejected(changes):
    with pytest.raises(FactValidationError):
        parse_facts({"facts": [fact(**changes)]}, part(), FactLimits(), "F")


def test_fact_count_and_evidence_length_limits_reject_without_silent_dropping():
    with pytest.raises(FactValidationError):
        parse_facts({"facts": [fact(), fact(topic="B")]}, part(), FactLimits(max_facts_per_chunk=1), "F")
    with pytest.raises(FactValidationError):
        parse_facts({"facts": [fact(topic="B", evidence=[1, 2])]},
                    part(), FactLimits(max_evidence_sentences=1), "F")


def facts():
    source = part()
    records = [fact(),
               fact(topic="Budget", claim="Budget is 48000.", evidence=[2], attribution="source"),
               fact(topic="Training", claim="Training lasts six weeks.", evidence=[3],
                    attribution="source", importance="support")]
    return parse_facts({"facts": records}, source, FactLimits(), "F")


def candidate():
    return {"summary": [{"text": "Noor controls release conditional on the audit.", "fact_ids": ["F1"]}],
            "key_points": [{"topic": "Budget", "text": "Budget is 48000.", "fact_ids": ["F2"]}]}


def test_candidate_public_text_and_caller_item_ids_preserve_valid_refs():
    parsed = parse_candidate(candidate(), facts(), FactLimits(), require_core_coverage=True)
    assert parsed.public_summary == "Noor controls release conditional on the audit."
    assert parsed.public_key_points == ("Budget is 48000.",)
    assert parsed.summary[0].id == "S1"
    assert parsed.key_points[0].id == "P1"


@pytest.mark.parametrize("refs", [[], ["unknown"], ["F1", "F1"], "F1", [True]])
def test_invalid_candidate_references_fail(refs):
    obj = candidate()
    obj["summary"][0]["fact_ids"] = refs
    with pytest.raises(FactValidationError):
        parse_candidate(obj, facts(), FactLimits())


def test_final_core_coverage_is_required_but_can_be_deferred_during_composition():
    obj = candidate()
    obj["key_points"][0]["fact_ids"] = ["F3"]
    parse_candidate(obj, facts(), FactLimits(), final=False)
    with pytest.raises(FactValidationError):
        parse_candidate(obj, facts(), FactLimits(), require_core_coverage=True)


def test_points_must_add_facts_but_can_reuse_common_context():
    obj = candidate()
    obj["key_points"].append({"topic": "Training", "text": "Budget funds six weeks of training.", "fact_ids": ["F2", "F3"]})
    assert len(parse_candidate(obj, facts(), FactLimits()).key_points) == 2
    obj["key_points"].append({"topic": "Combined", "text": "Funding and training are connected.", "fact_ids": ["F2", "F3"]})
    with pytest.raises(FactValidationError):
        parse_candidate(obj, facts(), FactLimits())


def test_duplicate_point_text_fails_even_with_new_references():
    obj = candidate()
    obj["key_points"].append({"topic": "Other", "text": "Budget  is 48000.", "fact_ids": ["F3"]})
    with pytest.raises(FactValidationError):
        parse_candidate(obj, facts(), FactLimits())


def test_final_point_limit_rejects_without_truncation_and_composition_defers_limit():
    obj = candidate()
    obj["key_points"][0]["text"] = "x" * 241
    assert len(parse_candidate(obj, facts(), FactLimits(), final=False).key_points[0].text) == 241
    with pytest.raises(FactValidationError):
        parse_candidate(obj, facts(), FactLimits())


@pytest.mark.parametrize("key,value", [("summary", []), ("key_points", []), ("summary", "text"), ("key_points", [None])])
def test_candidate_nonempty_typed_envelopes(key, value):
    obj = candidate() | {key: value}
    with pytest.raises(FactValidationError):
        parse_candidate(obj, facts(), FactLimits())


def source_parts():
    return [part()]


def audit():
    return {"additional_facts": [], "output": candidate(), "checks": [
        {"item_id": item, "supported": True, "qualifiers_preserved": True,
         "attribution_preserved": True, "scope_preserved": True} for item in ("S1", "P1")
    ]}


def test_audit_requires_each_final_claim_and_preserves_private_traceable_facts():
    parsed = parse_audit(audit(), source_parts(), facts(), FactLimits())
    assert parsed.candidate.public_key_points == ("Budget is 48000.",)
    assert tuple(check.item_id for check in parsed.checks) == ("S1", "P1")
    assert tuple(item.id for item in parsed.facts) == ("F1", "F2", "F3")


@pytest.mark.parametrize("changes", [
    {"supported": False}, {"qualifiers_preserved": False},
    {"attribution_preserved": False}, {"scope_preserved": False},
    {"supported": 1}, {"scope_preserved": "true"}, {"item_id": "unknown"},
])
def test_audit_false_or_wrong_type_cannot_publish(changes):
    obj = audit()
    obj["checks"][0].update(changes)
    with pytest.raises(FactValidationError):
        parse_audit(obj, source_parts(), facts(), FactLimits())


@pytest.mark.parametrize("checks", [[], ["S1"], [None]])
def test_incomplete_or_malformed_audit_list_fails(checks):
    obj = audit() | {"checks": checks}
    with pytest.raises(FactValidationError):
        parse_audit(obj, source_parts(), facts(), FactLimits())


def test_duplicate_check_cannot_replace_missing_item():
    obj = audit()
    obj["checks"][1] = dict(obj["checks"][0])
    with pytest.raises(FactValidationError):
        parse_audit(obj, source_parts(), facts(), FactLimits())


def test_additional_audit_fact_is_assigned_id_and_revalidated_against_source():
    obj = audit()
    obj["additional_facts"] = [fact(source_id="C1", topic="Training", evidence=[3],
                                    claim="Training lasts six weeks.", attribution="source")]
    obj["output"]["key_points"][0]["fact_ids"].append("A1")
    parsed = parse_audit(obj, source_parts(), facts(), FactLimits())
    assert parsed.facts[-1].id == "A1"
    assert parsed.facts[-1].quote == "Training lasts six weeks."
    assert parsed.candidate.key_points[0].fact_ids == ("F2", "A1")


@pytest.mark.parametrize("changes", [{"source_id": "unknown"}, {"evidence": [99]}])
def test_audit_addition_cannot_invent_evidence_or_choose_identity(changes):
    obj = audit()
    obj["additional_facts"] = [fact(source_id="C1", **changes)] if "source_id" not in changes else [fact(**changes)]
    with pytest.raises(FactValidationError):
        parse_audit(obj, source_parts(), facts(), FactLimits())


def test_added_core_fact_requires_final_reference():
    obj = audit()
    obj["additional_facts"] = [fact(source_id="C1", evidence=[3])]
    with pytest.raises(FactValidationError):
        parse_audit(obj, source_parts(), facts(), FactLimits())


def test_audit_rejects_fact_trace_that_does_not_match_supplied_source():
    changed = [SourcePart("C1", "Unrelated source")]
    with pytest.raises(FactValidationError):
        parse_audit(audit(), changed, facts(), FactLimits())


def test_audit_rebuild_rejects_forged_evidence_or_span():
    original = list(facts())
    original[0] = replace(original[0], evidence_indices=(3,))
    with pytest.raises(FactValidationError):
        parse_audit(audit(), source_parts(), original, FactLimits())


def test_duplicate_json_fields_cannot_hide_an_invalid_evidence_record():
    payload = ('{"facts": [], "facts": [{"topic":"x","claim":"x","evidence":[2],'
               '"attribution":"source","importance":"support"}]}')
    with pytest.raises(FactValidationError):
        parse_facts(payload, part(), FactLimits(), "F")


@pytest.mark.parametrize("payload", ["not json", "null", "[]", {}, {"facts": []}, {"facts": [None]}, {"facts": [fact()], "file": "model-file.json"}])
def test_malformed_fact_envelopes_are_rejected(payload):
    with pytest.raises(FactValidationError):
        parse_facts(payload, part(), FactLimits(), "F")


@pytest.mark.parametrize("source", [SourcePart("bad/id", "x"), SourcePart("C1", ""), SourcePart("C1", "x", True), SourcePart("C1", "x", -1)])
def test_invalid_caller_sources_cannot_generate_traces(source):
    with pytest.raises(FactValidationError):
        parse_facts({"facts": [fact()]}, source, FactLimits(), "F")


def test_bounded_identity_prefix_does_not_produce_unusable_fact_ids():
    with pytest.raises(FactValidationError):
        parse_facts({"facts": [fact()]}, part(), FactLimits(), "F" * 64)


@pytest.mark.parametrize("changes", [{"max_items": 8}, {"max_point_chars": True}, {"max_evidence_sentences": 0}])
def test_invalid_limits_cannot_disable_contract_count_or_length_bounds(changes):
    with pytest.raises(FactValidationError):
        parse_candidate(candidate(), facts(), FactLimits(**changes))


def test_at_most_seven_points_and_summary_claims_are_published():
    obj = candidate()
    obj["summary"] *= 8
    with pytest.raises(FactValidationError):
        parse_candidate(obj, facts(), FactLimits())


def test_summary_can_reference_point_facts_without_counting_as_duplicate_point():
    obj = candidate()
    obj["summary"][0]["fact_ids"] = ["F1", "F2"]
    assert parse_candidate(obj, facts(), FactLimits()).key_points[0].fact_ids == ("F2",)


@pytest.mark.parametrize("changes", [{"max_facts_per_chunk": 49}, {"max_evidence_sentences": 257},
                                     {"max_summary_chars": 20001}, {"max_claim_chars": 4001}])
def test_limits_cannot_create_unbounded_internal_model_records(changes):
    with pytest.raises(FactValidationError):
        parse_facts({"facts": [fact()]}, part(), FactLimits(**changes), "F")


def test_named_attribution_in_same_source_header_gets_its_own_global_span():
    source = SourcePart("C4", "Mira introduces policy.\nBudget is 48000.", 100)
    record = fact(topic="Budget", claim="Budget is 48000.", evidence=[2], attribution="Mira")
    item = parse_facts({"facts": [record]}, source, FactLimits(), "F")[0]
    assert (item.start, item.end) == (100 + source.text.index("Budget"), 100 + len(source.text))
    assert (item.attribution_start, item.attribution_end) == (100, 104)
    assert item.source_id == "C4"


def test_generic_attribution_has_no_named_source_span():
    item = facts()[1]
    assert (item.attribution_start, item.attribution_end) == (None, None)


@pytest.mark.parametrize("name", ["MIRA", "Mira Liao", "unknown"])
def test_named_attribution_is_not_case_corrected_or_invented(name):
    source = SourcePart("C4", "Mira introduces policy.\nBudget is 48000.")
    record = fact(topic="Budget", claim="Budget is 48000.", evidence=[2], attribution=name)
    with pytest.raises(FactValidationError):
        parse_facts({"facts": [record]}, source, FactLimits(), "F")


def test_audit_cannot_borrow_attribution_from_another_source_part():
    sources = [SourcePart("C1", "Budget is 48000."), SourcePart("C2", "Mira introduces policy.", 100)]
    original = parse_facts({"facts": [fact(topic="Budget", claim="Budget is 48000.",
                            evidence=[1], attribution="source")]}, sources[0], FactLimits(), "F")
    obj = audit()
    obj["additional_facts"] = [fact(source_id="C1", topic="Budget", evidence=[1],
                                    claim="Budget is 48000.", attribution="Mira")]
    with pytest.raises(FactValidationError):
        parse_audit(obj, sources, original, FactLimits())


def test_audit_rebuild_rejects_forged_private_attribution_position():
    original = list(facts())
    original[0] = replace(original[0], attribution_start=1, attribution_end=5)
    with pytest.raises(FactValidationError):
        parse_audit(audit(), source_parts(), original, FactLimits())


def test_model_cannot_supply_private_attribution_positions():
    with pytest.raises(FactValidationError):
        parse_facts({"facts": [fact(attribution_start=0, attribution_end=4)]},
                    part(), FactLimits(), "F")


def test_verbatim_quote_copy_issue_is_removed_entirely():
    # The 466-char verbatim-quote failure is gone: the model selects line numbers,
    # and long single-line evidence no longer needs a quote-length limit.
    long_line = "The pilot requires " + "a" * 446 + "."
    source = SourcePart("C1", long_line)
    record = fact(topic="Pilot", claim="The pilot has a requirement.", evidence=[1])
    item = parse_facts({"facts": [record]}, source, FactLimits(), "F")[0]
    assert len(item.quote) == len(long_line)
    assert item.quote == long_line
