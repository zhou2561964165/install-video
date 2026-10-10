import json
from pathlib import Path

import pytest

from app.services.summary_facts import FactLimits
from app.services.summary_normalization import DraftItem, NormalizationError, ThemeHint, normalize_composition


# Captured from docs/acceptance-reports/2026-10-07-grounded-summary-organization/
# results/organization-slots-en-medium.json (the stored compose result).
SAVED_SUMMARY = (
    "讲者廖浩翔介绍日常评分系统：因人际互动会留下印象并受评价，且学生持续一致努力即可展现良好中文能力，"
    "故对每节课给予评价。课后通常就课堂表现提供书面反馈，涵盖语言与文化行为，借助Engrade网站录入成绩并"
    "私下留言，学生登录账户即可查看，以明确下节课改进方向。评语依表现而定，可简可详，例如提醒发音，或让"
    "学生思考中文里如何应对赞美。"
)


def _theme_payload(conditions, consequences):
    return {
        "summary": ["Summary."],
        "theme_plan": {
            "theme_1": {
                "topic": "Topic",
                "principle": "Principle.",
                "conditions": conditions,
                "consequences": consequences,
                "fact_ids": [],
            }
        },
    }


def test_stored_summary_paragraph_remains_one_complete_claim():
    draft = normalize_composition({"summary": SAVED_SUMMARY, "key_points": []}, FactLimits())

    assert len(draft.summary) == 1
    assert draft.summary[0].id == "S1"
    assert draft.summary[0].text == SAVED_SUMMARY
    assert draft.summary[0].topic == ""
    assert draft.summary[0].hint_ids == ()


def test_array_claims_and_points_keep_text_topics_and_suggested_ids():
    draft = normalize_composition(
        {
            "summary": [
                "First statement.",
                {"text": "Second statement.", "fact_ids": ["UNKNOWN", "F2"]},
            ],
            "key_points": [
                "A point as plain text.",
                {"topic": "Topic B", "text": "A point with a topic.", "fact_ids": "hint-9"},
            ],
        },
        FactLimits(),
    )

    assert draft.summary == (
        DraftItem("S1", "First statement."),
        DraftItem("S2", "Second statement.", hint_ids=("UNKNOWN", "F2")),
    )
    assert draft.key_points == (
        DraftItem("P1", "A point as plain text."),
        DraftItem("P2", "A point with a topic.", "Topic B", ("hint-9",)),
    )
    assert draft.transformations == ("single_hint_id_wrapped",)


def test_frozen_numbered_points_and_themes_preserve_all_text_and_ids():
    points = [f"Frozen point {index}." for index in range(1, 6)]
    payload = {
        "summary": SAVED_SUMMARY,
        "theme_plan": {
            f"theme_{index}": {
                "topic": f"Topic {index}",
                "principle": f"Principle {index}.",
                "conditions": [f"Condition {index}."],
                "consequences": [f"Consequence {index}."],
                "fact_ids": f"unverified-{index}",
            }
            for index in range(1, 6)
        },
        **{f"point_{index}": {"text": text, "fact_ids": [f"unknown-{index}"]}
           for index, text in enumerate(points, 1)},
        "point_6": None,
        "point_7": None,
    }

    draft = normalize_composition(payload, FactLimits())

    assert tuple(item.text for item in draft.key_points) == tuple(points)
    assert tuple(item.id for item in draft.key_points) == ("P1", "P2", "P3", "P4", "P5")
    assert tuple(item.hint_ids for item in draft.key_points) == tuple((f"unknown-{i}",) for i in range(1, 6))
    assert draft.theme_hints == tuple(
        ThemeHint(i, f"Topic {i}", f"Principle {i}.", (f"Condition {i}.",),
                  (f"Consequence {i}.",), (f"unverified-{i}",))
        for i in range(1, 6)
    )
    assert draft.transformations == ("summary_paragraph_wrapped", "numbered_points_collected",
                                     "single_hint_id_wrapped", "theme_plan_mapped_to_hints",
                                     "trailing_null_slots_removed")


def test_nonempty_theme_scalar_text_is_wrapped_without_editing_or_splitting_it():
    condition = "  Keep punctuation! split?;  "
    consequence = "If A, then B: preserve the whole string."

    draft = normalize_composition(
        _theme_payload(condition, consequence), FactLimits()
    )

    assert draft.theme_hints[0].conditions == (condition,)
    assert draft.theme_hints[0].consequences == (consequence,)
    assert "theme_scalar_text_wrapped" in draft.transformations


def test_exact_empty_theme_scalar_becomes_no_text_and_is_recorded():
    draft = normalize_composition(_theme_payload("", []), FactLimits())

    assert draft.theme_hints[0].conditions == ()
    assert draft.theme_hints[0].consequences == ()
    assert "theme_scalar_empty_text_omitted" in draft.transformations


@pytest.mark.parametrize("field", ["conditions", "consequences"])
def test_whitespace_only_theme_scalar_still_uses_nonempty_text_validation(field):
    payload = _theme_payload(["condition"], ["consequence"])
    payload["theme_plan"]["theme_1"][field] = " \t "

    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition(payload, FactLimits())

    assert exc_info.value.reason_code == "invalid_text"


@pytest.mark.parametrize("value", [0, False, {}, None])
def test_nontext_theme_scalars_remain_invalid_and_are_not_coerced(value):
    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition(_theme_payload(value, []), FactLimits())

    assert exc_info.value.reason_code == "invalid_theme_plan"


def test_theme_scalar_text_uses_passed_fact_limit_without_truncation():
    limits = FactLimits(max_point_chars=4)

    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition(_theme_payload("12345", []), limits)

    assert exc_info.value.reason_code == "theme_too_long"


def test_complete_outer_json_fence_is_removed_before_decoding():
    payload = '```json\n{"summary":"Whole paragraph.","key_points":[]}\n```'

    draft = normalize_composition(payload, FactLimits())

    assert draft.summary[0].text == "Whole paragraph."
    assert "outer_json_fence_removed" in draft.transformations


def test_identical_array_and_slot_points_collapse_without_losing_ids():
    point = {"topic": "Topic", "text": "Same point.", "fact_ids": ["F1"]}
    payload = {"summary": "Whole paragraph.", "key_points": [point], "point_1": point}

    draft = normalize_composition(payload, FactLimits())

    assert draft.key_points == (DraftItem("P1", "Same point.", "Topic", ("F1",)),)
    assert "duplicate_point_representations_collapsed" in draft.transformations


def test_json_looking_text_is_not_reparsed_as_a_nested_object():
    point_text = '{"text":"do not coerce","fact_ids":["F1"]}'

    draft = normalize_composition({"summary": "Whole paragraph.", "point_1": point_text}, FactLimits())

    assert draft.key_points == (DraftItem("P1", point_text),)


def test_original_failed_compose_response_preserves_paragraph_five_points_themes_and_hints():
    artifact = (Path(__file__).resolve().parents[2]
                / "docs/acceptance-reports/2026-10-08-grounded-summary-prefix/results/responses/02.json")
    envelope = json.loads(artifact.read_text(encoding="utf-8"))
    raw_content = envelope["content"]
    original = json.loads(raw_content)

    assert isinstance(original["summary"], str)
    assert all(f"point_{index}" in original for index in range(1, 6))
    assert all(f"theme_{index}" in original["theme_plan"] for index in range(1, 6))

    draft = normalize_composition(raw_content, FactLimits())

    assert len(draft.summary) == 1
    assert draft.summary[0].text == original["summary"]
    assert tuple(item.id for item in draft.key_points) == ("P1", "P2", "P3", "P4", "P5")
    for index, item in enumerate(draft.key_points, 1):
        source = original[f"point_{index}"]
        expected_ids = (source["fact_ids"],) if isinstance(source["fact_ids"], str) else tuple(source["fact_ids"])
        assert item.text == source["text"]
        assert item.topic == source["topic"]
        assert item.hint_ids == expected_ids
    assert len(draft.theme_hints) == 5
    for index, theme in enumerate(draft.theme_hints, 1):
        source = original["theme_plan"][f"theme_{index}"]
        expected_ids = (source["fact_ids"],) if isinstance(source["fact_ids"], str) else tuple(source["fact_ids"])
        assert theme.point_index == index
        assert theme.topic == source["topic"]
        assert theme.principle == source["principle"]
        assert theme.conditions == tuple(source["conditions"])
        assert theme.consequences == tuple(source["consequences"])
        assert theme.hint_ids == expected_ids


def test_quality_final_scalar_theme_text_responses_preserve_all_text_and_hints():
    results = (Path(__file__).resolve().parents[2]
               / "docs/acceptance-reports/2026-10-08-summary-quality-final/results/responses")

    for ordinal in (2, 3):
        envelope = json.loads((results / f"{ordinal:02d}.json").read_text(encoding="utf-8"))
        original = json.loads(envelope["content"])

        assert isinstance(original["summary"], str)
        assert all(f"point_{index}" in original for index in range(1, 6))
        assert all(isinstance(original["theme_plan"][f"theme_{index}"][field], str)
                   for index in range(1, 6) for field in ("conditions", "consequences"))

        draft = normalize_composition(envelope["content"], FactLimits())

        assert len(draft.summary) == 1
        assert draft.summary[0].text == original["summary"]
        assert draft.summary[0].hint_ids == ()
        assert tuple(item.id for item in draft.key_points) == ("P1", "P2", "P3", "P4", "P5")
        assert len(draft.theme_hints) == 5
        for index, item in enumerate(draft.key_points, 1):
            source = original[f"point_{index}"]
            expected_ids = (source["fact_ids"],) if isinstance(source["fact_ids"], str) else tuple(source["fact_ids"])
            assert item.text == source["text"]
            assert item.topic == source["topic"]
            assert item.hint_ids == expected_ids
        for index, theme in enumerate(draft.theme_hints, 1):
            source = original["theme_plan"][f"theme_{index}"]
            expected_ids = (source["fact_ids"],) if isinstance(source["fact_ids"], str) else tuple(source["fact_ids"])
            assert theme.point_index == index
            assert theme.topic == source["topic"]
            assert theme.principle == source["principle"]
            assert theme.conditions == ((source["conditions"],) if source["conditions"] else ())
            assert theme.consequences == ((source["consequences"],) if source["consequences"] else ())
            assert theme.hint_ids == expected_ids
        assert "theme_scalar_text_wrapped" in draft.transformations


@pytest.mark.parametrize("payload", [
    ('{"summary":"A","summary":"B","key_points":[]}', "duplicate_json_field"),
    ('prefix {"summary":"A","key_points":[]} suffix', "invalid_json"),
    ('[{"summary":"A"}]', "invalid_payload"),
])
def test_duplicate_fields_prose_wrappers_and_nonobject_roots_are_rejected(payload):
    payload, reason = payload
    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition(payload, FactLimits())
    assert exc_info.value.reason_code == reason
    assert str(exc_info.value) == reason


@pytest.mark.parametrize(("payload", "reason"), [
    ({"summary": "ok", "key_points": [], "unexpected": 1}, "unknown_fields"),
    ({"summary": [{"text": "ok", "extra": 1}]}, "unknown_fields"),
    ({"summary": "ok", "theme_plan": '{"theme_1":{}}'}, "invalid_theme_plan"),
    ({"summary": "ok", "theme_plan": {"theme_1": {"topic": "topic", "principle": "p",
                                                       "conditions": [], "consequences": []}}},
     "missing_fields"),
    ({"summary": "ok", "point_2": {"text": "gap"}}, "slot_hole"),
    ({"summary": "ok", "point_1": None, "point_2": {"text": "after gap"}}, "slot_hole"),
    ({"summary": "ok", "key_points": ["different"], "point_1": {"text": "point"}},
     "inconsistent_points"),
    ({"summary": 42}, "invalid_payload"),
    ({"summary": [{"text": {"nested": "object"}}]}, "invalid_text"),
    ({"summary": "ok", "key_points": [{"text": "point", "topic": 9}]}, "invalid_text"),
    ({"summary": "ok", "key_points": [{"text": "point", "topic": None}]}, "invalid_text"),
    ({"summary": "ok", "key_points": [{"text": "point", "fact_ids": 7}]}, "invalid_hint_ids"),
    ({"summary": "ok", "key_points": [{"text": "point", "fact_ids": ["F1", 7]}]},
     "invalid_hint_ids"),
])
def test_malformed_or_unrecognized_shapes_are_rejected_without_coercion(payload, reason):
    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition(payload, FactLimits())
    assert exc_info.value.reason_code == reason
    assert "nested" not in str(exc_info.value)


def test_candidate_and_final_limits_reject_without_truncating_or_dropping():
    candidate_limits = FactLimits(max_summary_chars=800)
    candidate = normalize_composition({"summary": ["x"] * 14}, candidate_limits)
    assert len(candidate.summary) == 14

    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition({"summary": ["x"] * 15}, candidate_limits)
    assert exc_info.value.reason_code == "too_many_summary_items"
    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition({"summary": "x" * 1601}, candidate_limits)
    assert exc_info.value.reason_code == "summary_too_long"

    default_limit_candidate = normalize_composition({"summary": "x" * 8000}, FactLimits())
    assert len(default_limit_candidate.summary[0].text) == 8000
    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition({"summary": "x" * 8001}, FactLimits())
    assert exc_info.value.reason_code == "summary_too_long"

    final_limits = FactLimits(max_summary_chars=800)
    candidate_with_final_limit = normalize_composition(
        {"summary": "x" * 1600}, final_limits, final=False
    )
    assert candidate_with_final_limit.summary[0].text == "x" * 1600
    final = normalize_composition({"summary": "x" * 800}, final_limits, final=True)
    assert final.summary[0].text == "x" * 800
    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition({"summary": ["x"] * 8}, final_limits, final=True)
    assert exc_info.value.reason_code == "too_many_summary_items"
    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition({"summary": "x" * 801}, final_limits, final=True)
    assert exc_info.value.reason_code == "summary_too_long"


def test_summary_and_point_counts_follow_custom_fact_limits():
    limits = FactLimits(max_items=2, max_summary_chars=40)
    candidate = normalize_composition(
        {"summary": ["one", "two", "three", "four"], "key_points": ["p1", "p2"]}, limits
    )
    assert tuple(item.id for item in candidate.summary) == ("S1", "S2", "S3", "S4")
    assert tuple(item.id for item in candidate.key_points) == ("P1", "P2")

    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition({"summary": ["one", "two", "three", "four", "five"]}, limits)
    assert exc_info.value.reason_code == "too_many_summary_items"
    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition({"summary": "ok", "key_points": ["p1", "p2", "p3"]}, limits)
    assert exc_info.value.reason_code == "too_many_points"
    final = normalize_composition({"summary": ["one", "two"]}, limits, final=True)
    assert len(final.summary) == 2


def test_point_limits_follow_fact_limits_for_candidate_and_final():
    candidate = normalize_composition({"summary": "ok", "key_points": ["p" * 600]}, FactLimits())
    assert candidate.key_points[0].text == "p" * 600
    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition({"summary": "ok", "key_points": ["p" * 601]}, FactLimits())
    assert exc_info.value.reason_code == "point_too_long"

    limits = FactLimits(max_summary_chars=800, max_point_chars=240)
    final = normalize_composition({"summary": "ok", "key_points": ["p" * 240]}, limits, final=True)
    assert final.key_points[0].text == "p" * 240
    with pytest.raises(NormalizationError) as exc_info:
        normalize_composition({"summary": "ok", "key_points": ["p" * 241]}, limits, final=True)
    assert exc_info.value.reason_code == "point_too_long"

    custom = FactLimits(max_summary_chars=900, max_claim_chars=720, max_point_chars=260)
    candidate = normalize_composition(
        {"summary": "s" * 1800, "key_points": ["p" * 720]}, custom
    )
    assert len(candidate.summary[0].text) == 1800
    assert len(candidate.key_points[0].text) == 720
    final = normalize_composition(
        {"summary": "s" * 900, "key_points": ["p" * 260]}, custom, final=True
    )
    assert len(final.summary[0].text) == 900
    assert len(final.key_points[0].text) == 260


def test_dataclass_outputs_are_frozen_and_missing_optional_fields_have_stable_defaults():
    draft = normalize_composition({"summary": ["same", "same"]}, FactLimits())
    assert [item.id for item in draft.summary] == ["S1", "S2"]
    assert [item.text for item in draft.summary] == ["same", "same"]
    assert draft.key_points == ()
    assert draft.theme_hints == ()
    assert draft.transformations == ()
    assert draft.summary[0].topic == ""
    assert draft.summary[0].hint_ids == ()
    with pytest.raises((AttributeError, TypeError)):
        draft.summary[0].text = "changed"
    with pytest.raises(ValueError):
        ThemeHint(0)


def test_real_extraction_transport_marker_is_normalized_without_changing_facts():
    from app.services import summary_normalization as normalization
    from app.services.summary_facts import SourcePart, parse_extraction
    assert hasattr(normalization, "normalize_extraction"), "Extraction envelope normalizer is missing"
    results = Path(__file__).resolve().parents[2] / "docs/acceptance-reports/2026-10-08-grounded-summary-normalized/results"
    trace = json.loads((results / "normalized-retries-en-long-trace.json").read_text(encoding="utf-8"))["events"][-1]
    source = trace["sources"][0]
    part = SourcePart(source["id"], source["text"], source["global_start"])
    for ordinal in (7, 8):
        raw = json.loads((results / f"responses/{ordinal:02d}.json").read_text(encoding="utf-8"))["content"]
        original = json.loads(raw)
        normalized, transformations = normalization.normalize_extraction(raw)
        assert normalized == {key: value for key, value in original.items() if key != "type"}
        assert transformations == ("json_object_transport_marker_removed",)
        facts = parse_extraction(normalized, part, FactLimits(max_summary_chars=800), "F1_")
        assert len(facts) == 10
        assert [f.claim for f in facts] == [original[f"fact_{n}"]["claim"] for n in range(1, 11)]


def test_extraction_normalization_keeps_unknown_or_provenance_fields_for_strict_rejection():
    from app.services import summary_normalization as normalization
    assert hasattr(normalization, "normalize_extraction"), "Extraction envelope normalizer is missing"
    for marker in ("other", 1, None):
        raw = {"type": marker, "source_id": "invented", "fact_1": {"quote": "invented"}}
        normalized, changes = normalization.normalize_extraction(raw)
        assert normalized == raw and changes == ()
