"""Source identity and theme ownership regressions, not semantic entailment tests."""

from dataclasses import FrozenInstanceError, asdict, replace
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from app.services.summary_facts import (
    CandidateSummary, FactLimits, FactValidationError, SourcePart, SummaryClaim, SummaryPoint,
    parse_extraction, parse_facts,
)
from app.services.summary_normalization import DraftItem, NormalizedDraft, ThemeHint, normalize_composition


def api():
    assert importlib.util.find_spec("app.services.summary_quality") is not None, "quality diagnostics feature missing"
    return importlib.import_module("app.services.summary_quality")


def bank(text="ALICE DOE: Explain conditions.", *, name="ALICE DOE", source_id="C1", offset=23):
    source = SourcePart(source_id, text, offset)
    facts = parse_facts({"facts": [{"topic": "Conditions", "claim": "Explain conditions.",
        "evidence": [1], "attribution": name, "importance": "core"}]}, source, FactLimits(), "F" + source_id)
    return source, facts


def draft(text, *, points=(), themes=()):
    return NormalizedDraft((DraftItem("S1", text),), points, themes)


def reasons(report):
    return [issue.reason for issue in report.issues]


def test_real_medium_compose_added_name_is_reported_without_changing_original():
    root = Path(__file__).resolve().parents[2]
    results = root / "docs/acceptance-reports/2026-10-08-grounded-summary-clause/results"
    paths = [results / "responses/04.json", results / "responses/05.json"]
    original = [path.read_bytes() for path in paths]
    extracted, composed = [json.loads(raw)["content"] for raw in original]
    source = SourcePart("part1", (root / "docs/acceptance-reports/2026-10-04-natural-subtitle-quality/corpus/en-medium.txt").read_text(encoding="utf-8").strip())
    facts = parse_extraction(extracted, source, FactLimits(), "F1_")
    normalized = normalize_composition(composed, FactLimits())
    before = asdict(normalized)
    report = api().inspect_quality(normalized, facts, [source])
    issue = next(item for item in report.issues if item.reason == "unconfirmed_identity")
    assert (issue.item_id, issue.surface) == ("S1", "廖浩翔")
    assert normalized.summary[0].text[issue.output_start:issue.output_end] == "廖浩翔"
    assert asdict(normalized) == before
    assert [path.read_bytes() for path in paths] == original


@pytest.mark.parametrize("text,surface", [
    ("讲者王若林介绍课程的条件。", "王若林"),
    ("教授赵晓雨指出条件十分重要。", "赵晓雨"),
    ("主讲人名为许晨。", "许晨"),
    ("Speaker Alex Brown explains the conditions.", "Alex Brown"),
])
def test_role_bound_unconfirmed_names_are_not_sample_specific(text, surface):
    source, facts = bank()
    issue = next(item for item in api().inspect_quality(draft(text), facts, [source]).issues
                 if item.reason == "unconfirmed_identity")
    assert issue.surface == surface
    assert text[issue.output_start:issue.output_end] == surface


@pytest.mark.parametrize("text", [
    "讲者明确指出条件十分重要。", "讲者进一步详细介绍条件。", "讲者认为条件很重要。",
    "讲者通常介绍课程。", "讲者对课程进行介绍。", "这是文化概念与课堂用语。",
    "The speaker clearly explains the conditions.", "讲者：条件重要。",
])
def test_generic_roles_adverbs_and_nonidentity_text_are_not_names(text):
    source, facts = bank()
    assert not api().inspect_quality(draft(text), facts, [source]).has_issues


def test_multisource_verbatim_names_have_verified_global_spans():
    first, facts1 = bank("王若林：说明条件。", name="王若林", offset=31)
    second, facts2 = bank("BOB RAY: Explain outcomes.", name="BOB RAY", source_id="C2", offset=103)
    text = "讲者王若林介绍条件；BOB RAY explains outcomes."
    report = api().inspect_quality(draft(text), (*facts1, *facts2), [first, second])
    assert not report.has_issues
    assert [(b.surface, b.source_id, b.source_start, b.source_end) for b in report.identities] == [
        ("王若林", "C1", 31, 34), ("BOB RAY", "C2", 103, 110)]
    for binding in report.identities:
        assert text[binding.output_start:binding.output_end] == binding.surface
    with pytest.raises(FrozenInstanceError):
        report.issues = ()


def test_invalid_bank_attribution_cannot_create_allowed_alias():
    source, facts = bank()
    with pytest.raises(FactValidationError, match="attribution_not_found"):
        api().derive_attribution_policy((replace(facts[0], attribution="虚构姓名"),), [source])
    with pytest.raises(FactValidationError, match="invalid_fact_trace"):
        api().derive_attribution_policy((replace(facts[0], attribution_start=24),), [source])


def test_literal_protection_does_not_bind_latin_substrings():
    source, facts = bank("Li: Explain conditions.", name="Li")
    report = api().inspect_quality(draft("Limits apply."), facts, [source])
    assert not report.identities and not report.has_issues


def test_required_theme_plan_missing_is_a_diagnostic_not_text_rewrite():
    source, facts = bank()
    normalized = draft("Explain conditions.", points=(DraftItem("P1", "Explain conditions.", "Conditions"),))
    report = api().inspect_quality(normalized, facts, [source], require_theme_plan=True)
    assert "missing_theme_plan" in reasons(report)
    assert normalized.key_points[0].text == "Explain conditions."
    assert not api().inspect_quality(normalized, facts, [source]).has_issues


def test_duplicate_primary_ownership_is_not_hidden_by_different_theme_labels():
    source, facts = bank()
    identifier = facts[0].id
    normalized = draft("Conditions matter.", points=(DraftItem("P1", "Explain conditions.", "Principle"),
        DraftItem("P2", "Explain conditions in detail.", "Example")), themes=(
        ThemeHint(1, "Principle", "Explain conditions.", hint_ids=(identifier,)),
        ThemeHint(2, "Example", "Explain conditions in detail.", hint_ids=(identifier,))))
    report = api().inspect_quality(normalized, facts, [source], require_theme_plan=True)
    issue = next(item for item in report.issues if item.reason == "duplicate_theme_ownership")
    assert issue.fact_ids == (identifier,) and issue.related_item_ids == ("P1",)


def test_identical_theme_labels_and_unknown_primary_ids_are_reported():
    source, facts = bank()
    normalized = draft("Conditions matter.", points=(DraftItem("P1", "First.", "Conditions"),
        DraftItem("P2", "Second.", " conditions ")), themes=(
        ThemeHint(1, "Conditions", "First.", hint_ids=(facts[0].id,)),
        ThemeHint(2, " conditions ", "Second.", hint_ids=("UNKNOWN",))))
    report = api().inspect_quality(normalized, facts, [source], require_theme_plan=True)
    assert "duplicate_theme_label" in reasons(report) and "unknown_theme_fact" in reasons(report)


def test_core_in_actual_summary_associations_needs_no_separate_point_theme():
    first, facts1 = bank()
    second, facts2 = bank("BOB RAY: Explain outcomes.", name="BOB RAY", source_id="C2", offset=103)
    normalized = draft("Explain conditions.", points=(DraftItem("P1", "Explain outcomes.", "Outcomes"),),
        themes=(ThemeHint(1, "Outcomes", "Explain outcomes.", hint_ids=(facts2[0].id,)),))
    candidate = CandidateSummary((SummaryClaim("S1", "Explain conditions.", (facts1[0].id,)),), ())
    report = api().inspect_quality(normalized, (*facts1, *facts2), [first, second], require_theme_plan=True, candidate=candidate)
    assert not report.has_issues
    hinted_summary = replace(normalized, summary=(replace(normalized.summary[0], hint_ids=(facts1[0].id,)),))
    without_actual_candidate = api().inspect_quality(hinted_summary, (*facts1, *facts2), [first, second], require_theme_plan=True)
    assert any(issue.reason == "core_theme_gap" and issue.fact_ids == (facts1[0].id,) for issue in without_actual_candidate.issues)


def test_crosspart_theme_preserves_conditions_and_consequences_without_rewriting():
    first, facts1 = bank()
    second, facts2 = bank("BOB RAY: Explain outcomes.", name="BOB RAY", source_id="C2", offset=103)
    normalized = draft("Conditions and outcomes.", points=(DraftItem("P1", "If prepared, complete tasks; otherwise ask afterward.", "Preparation"),),
        themes=(ThemeHint(1, "Preparation", "Match preparation with tasks.", ("If prepared",),
                          ("Otherwise ask afterward",), (facts1[0].id, facts2[0].id)),))
    before = asdict(normalized)
    assert not api().inspect_quality(normalized, (*facts1, *facts2), [first, second], require_theme_plan=True).has_issues
    assert asdict(normalized) == before


@pytest.mark.parametrize("themes,expected", [
    ((ThemeHint(2, "Conditions", "Conditions.", hint_ids=("FC11",)),), "theme_point_mismatch"),
    ((ThemeHint(1, "Other", "Conditions.", hint_ids=("FC11",)),), "theme_point_topic_mismatch"),
    ((ThemeHint(1, "Conditions", "", hint_ids=("FC11",)),), "invalid_theme_shape"),
    ((ThemeHint(1, "Conditions", "Conditions.", hint_ids=()),), "empty_theme_ownership"),
])
def test_malformed_theme_relations_are_specific_diagnostics(themes, expected):
    source, facts = bank()
    normalized = draft("Conditions.", points=(DraftItem("P1", "Conditions.", "Conditions"),), themes=themes)
    assert expected in reasons(api().inspect_quality(normalized, facts, [source], require_theme_plan=True))


@pytest.mark.parametrize("text", ["讲者们介绍条件。", "讲者本人说明条件。", "讲者自己提出问题。", "讲者详细地介绍课程。"])
def test_plural_roles_pronouns_and_modifier_particle_are_generic(text):
    source, facts = bank()
    assert not api().inspect_quality(draft(text), facts, [source]).has_issues


def test_known_verbatim_identity_with_adverb_keeps_the_name_binding():
    source, facts = bank("王若林：说明条件。", name="王若林")
    report = api().inspect_quality(draft("讲者王若林详细介绍条件。"), facts, [source])
    assert not report.has_issues
    assert report.identities[0].surface == "王若林"


def test_longer_role_bound_name_cannot_use_known_literal_prefix_as_confirmation():
    source, facts = bank("王明：说明条件。", name="王明")
    text = "讲者王明确介绍课程。"
    report = api().inspect_quality(draft(text), facts, [source])
    issue = next(item for item in report.issues if item.reason == "unconfirmed_identity")
    assert issue.surface == "王明确"
    assert (issue.output_start, issue.output_end) == (2, 5)
    assert text[issue.output_start:issue.output_end] == "王明确"


@pytest.mark.parametrize("text", [
    "讲者名为王明介绍课程。", "讲者叫做王明指出条件。",
    "讲者名字是王明。", "讲者名为王明", "讲者名为“王明”介绍课程。",
])
def test_explicit_naming_stops_at_predicate_or_boundary_without_duplicate_candidate(text):
    source, facts = bank("王明：说明条件。", name="王明")
    normalized = draft(text)
    before = asdict(normalized)
    report = api().inspect_quality(normalized, facts, [source])
    assert not report.has_issues
    assert len(report.identities) == 1
    assert report.identities[0].surface == "王明"
    assert text[report.identities[0].output_start:report.identities[0].output_end] == "王明"
    assert asdict(normalized) == before


@pytest.mark.parametrize("text,name", [
    ("讲者王明详细介绍课程。", "王明"),
    ("老师张三明确表示条件。", "张三"),
    ("讲者王明确介绍课程。", "王明确"),
])
def test_known_full_literal_is_preserved_when_adverb_spelling_overlaps_name(text, name):
    source, facts = bank(f"{name}：说明条件。", name=name)
    report = api().inspect_quality(draft(text), facts, [source])
    assert not report.has_issues
    assert report.identities[0].surface == name


def test_unconfirmed_explicit_naming_with_predicate_reports_name_once():
    source, facts = bank("王明：说明条件。", name="王明")
    text = "讲者名为许晨介绍课程。"
    report = api().inspect_quality(draft(text), facts, [source])
    assert [(issue.reason, issue.surface, issue.output_start, issue.output_end)
            for issue in report.issues] == [("unconfirmed_identity", "许晨", 4, 6)]


def test_explicit_naming_modifier_does_not_extend_a_verified_name():
    source, facts = bank("王明：说明条件。", name="王明")
    text = "讲者名为王明详细介绍课程。"

    report = api().inspect_quality(draft(text), facts, [source])

    assert not report.has_issues
    assert [(identity.surface, text[identity.output_start:identity.output_end])
            for identity in report.identities] == [("王明", "王明")]


def test_explicit_naming_modifier_does_not_confirm_an_unknown_alias():
    source, facts = bank("王明：说明条件。", name="王明")
    text = "讲者名为许晨详细介绍课程。"

    report = api().inspect_quality(draft(text), facts, [source])

    assert [(issue.reason, issue.surface, issue.output_start, issue.output_end)
            for issue in report.issues] == [("unconfirmed_identity", "许晨", 4, 6)]
    assert text[report.issues[0].output_start:report.issues[0].output_end] == "许晨"


@pytest.mark.parametrize("name", ["王明详细", "王明确"])
def test_explicit_naming_preserves_verified_names_ending_in_modifier_words(name):
    source, facts = bank(f"{name}：说明条件。", name=name)
    text = f"讲者名为{name}介绍课程。"

    report = api().inspect_quality(draft(text), facts, [source])

    assert not report.has_issues
    assert [(identity.surface, text[identity.output_start:identity.output_end])
            for identity in report.identities] == [(name, name)]


@pytest.mark.parametrize("text", [
    "讲者认为条件成立并介绍操作。",
    "老师指出条件变化后介绍措施。",
    "讲者介绍操作并说明条件。",
])
def test_attached_candidates_starting_with_predicates_are_not_names(text):
    source, facts = bank(text, name="source")

    report = api().inspect_quality(draft(text), facts, [source])

    assert not report.has_issues


@pytest.mark.parametrize("text,name", [
    ("讲者陈文辉介绍操作。", "陈文辉"),
    ("讲者廖某指出情况后介绍措施。", "廖某"),
    ("讲者名为陈文辉介绍操作。", "陈文辉"),
])
def test_predicate_filter_keeps_unconfirmed_real_looking_names(text, name):
    source, facts = bank(text, name="source")

    report = api().inspect_quality(draft(text), facts, [source])

    issue = next(item for item in report.issues if item.reason == "unconfirmed_identity")
    assert (issue.surface, issue.output_start, issue.output_end) == (
        name, text.index(name), text.index(name) + len(name))


@pytest.mark.parametrize("source_text,name,text", [
    ("认为：说明条件。", "认为", "讲者认为详细介绍操作。"),
    ("认为条件成立并：介绍操作。", "认为条件成立并", "讲者认为条件成立并介绍操作。"),
])
def test_predicate_filter_preserves_an_exact_verified_identity_or_modifier(source_text, name, text):
    source, facts = bank(source_text, name=name)

    report = api().inspect_quality(draft(text), facts, [source])

    assert not report.has_issues
    assert any(identity.surface == name and text[identity.output_start:identity.output_end] == name
               for identity in report.identities)


def test_candidate_from_different_text_cannot_exempt_core_theme_gap():
    first, facts1 = bank()
    second, facts2 = bank("BOB RAY: Explain outcomes.", name="BOB RAY", source_id="C2", offset=103)
    normalized = draft("Omitted conditions.", points=(DraftItem("P1", "Explain outcomes.", "Outcomes"),),
        themes=(ThemeHint(1, "Outcomes", "Explain outcomes.", hint_ids=(facts2[0].id,)),))
    stale = CandidateSummary((SummaryClaim("S1", "Explain conditions.", (facts1[0].id,)),), ())
    report = api().inspect_quality(normalized, (*facts1, *facts2), [first, second], require_theme_plan=True, candidate=stale)
    assert "candidate_draft_mismatch" in reasons(report)
    assert any(issue.reason == "core_theme_gap" and issue.fact_ids == (facts1[0].id,) for issue in report.issues)


def test_generic_fact_with_tampered_hash_is_source_error_before_output_diagnostic():
    source, facts = bank("Explain conditions.", name="source")
    with pytest.raises(FactValidationError, match="invalid_fact_trace"):
        api().inspect_quality(draft("讲者王若林介绍课程。"), (replace(facts[0], source_sha256="tampered"),), [source])


def test_theme_count_mismatch_keeps_extra_theme_and_point_text_intact():
    source, facts = bank()
    normalized = draft("Conditions.", points=(DraftItem("P1", "Original point.", "Conditions"),), themes=(
        ThemeHint(1, "Conditions", "Conditions.", hint_ids=(facts[0].id,)),
        ThemeHint(2, "Outcomes", "Original extra theme.", hint_ids=()),))
    before = asdict(normalized)
    assert "theme_point_count_mismatch" in reasons(api().inspect_quality(normalized, facts, [source], require_theme_plan=True))
    assert asdict(normalized) == before


def test_plain_unbound_name_is_outside_bounded_detector_scope():
    source, facts = bank()
    # This remains the semantic audit's responsibility, not a universal NER claim.
    assert not api().inspect_quality(draft("王若林在这所学校工作。"), facts, [source]).has_issues


def test_malformed_theme_arrays_are_diagnosed_without_typeerror():
    source, facts = bank()
    theme = ThemeHint(1, "Conditions", "Conditions.", conditions=None, hint_ids=(facts[0].id,))
    normalized = draft("Conditions.", points=(DraftItem("P1", "Conditions.", "Conditions"),), themes=(theme,))
    assert "invalid_theme_shape" in reasons(api().inspect_quality(normalized, facts, [source], require_theme_plan=True))


def test_nonstring_point_text_is_diagnosed_without_silently_coercing_content():
    source, facts = bank()
    normalized = draft("Conditions.", points=(DraftItem("P1", 12, "Conditions"),))
    assert reasons(api().inspect_quality(normalized, facts, [source])) == ["invalid_quality_input"]


class UnhashableReference(str):
    __hash__ = None


@pytest.mark.parametrize("bad_ref", [[], {}, UnhashableReference("FC11"), 12])
def test_malformed_summary_reference_returns_diagnostic_instead_of_typeerror(bad_ref):
    source, facts = bank()
    normalized = draft("Explain conditions.")
    candidate = CandidateSummary((SummaryClaim("S1", "Explain conditions.", (bad_ref,)),), ())
    assert reasons(api().inspect_quality(normalized, facts, [source], candidate=candidate)) == ["candidate_draft_mismatch"]


@pytest.mark.parametrize("context_in_summary", [True, False])
def test_shared_actual_context_references_do_not_conflict_with_distinct_primary_owners(context_in_summary):
    first, context = bank()
    second, primary1 = bank("BOB RAY: Explain outcomes.", name="BOB RAY", source_id="C2", offset=103)
    third, primary2 = bank("CAROL MAY: Explain alternatives.", name="CAROL MAY", source_id="C3", offset=203)
    context_id, first_id, second_id = context[0].id, primary1[0].id, primary2[0].id
    summary_text = "Explain shared conditions and independent outcomes."
    points = (DraftItem("P1", "Given shared conditions, explain outcomes.", "Outcomes"),
              DraftItem("P2", "Given shared conditions, explain alternatives.", "Alternatives"))
    first_owner = (first_id,) if context_in_summary else (context_id, first_id)
    normalized = draft(summary_text, points=points, themes=(
        ThemeHint(1, "Outcomes", "Explain outcomes.", hint_ids=first_owner),
        ThemeHint(2, "Alternatives", "Explain alternatives.", hint_ids=(second_id,))))
    candidate = CandidateSummary((SummaryClaim("S1", summary_text,
        (context_id,) if context_in_summary else (first_id,)),), (
        SummaryPoint("P1", "Outcomes", points[0].text, (context_id, first_id)),
        SummaryPoint("P2", "Alternatives", points[1].text, (context_id, second_id))))
    before = asdict(candidate)
    assert not api().inspect_quality(normalized, (*context, *primary1, *primary2),
        [first, second, third], require_theme_plan=True, candidate=candidate).has_issues
    assert asdict(candidate) == before
