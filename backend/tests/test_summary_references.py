"""Hand-derived reference association cases; none assert semantic entailment."""

from dataclasses import FrozenInstanceError, asdict
import importlib
import importlib.util

import pytest

from app.services.summary_facts import FactLimits, SourcePart, parse_facts


def api():
    spec = importlib.util.find_spec("app.services.summary_references")
    assert spec is not None, "reference resolver feature is missing"
    module = importlib.import_module("app.services.summary_references")
    assert callable(getattr(module, "resolve_references", None)), "reference resolver feature is missing"
    return module


def draft(text, *, hints=(), points=(), themes=()):
    normalizer = importlib.import_module("app.services.summary_normalization")
    return normalizer.NormalizedDraft(
        (normalizer.DraftItem("S1", text, hint_ids=hints),), points, themes
    )


def facts(*claims):
    source = SourcePart("C1", "\n".join(claims), 17)
    return parse_facts({"facts": [
        {"topic": "Evidence", "claim": claim, "evidence": [index],
         "attribution": "source", "importance": "core"}
        for index, claim in enumerate(claims, 1)
    ]}, source, FactLimits(), "F")


def test_exact_claim_prefers_actual_text_over_unrelated_known_hint():
    module = api()
    result = module.resolve_references(draft("  CACHE reduces request latency.  ", hints=("F2",)),
                                       facts("Cache reduces request latency.", "Indexes accelerate database lookups."))
    assert result.candidate.summary[0].text == "  CACHE reduces request latency.  "
    assert result.candidate.summary[0].fact_ids == ("F1",)
    assert result.bindings[0].method == "exact_claim_suggestion"
    assert not result.has_unresolved
    assert [(hint.hint_id, hint.reason) for hint in result.invalid_hints] == [("F2", "unrelated_hint")]


def test_positive_clause_is_not_rejected_by_a_different_negative_source_clause():
    claim = "学生课前收到weekly schedule，知道每天准备哪些环节；没准备的练习会使学生转用英文，备课与上课任务必须一致。"
    text = "学生课前收到weekly schedule，知道每天准备哪些环节。"
    result = api().resolve_references(draft(text), facts(claim))
    assert result.candidate.summary[0].fact_ids == ("F1",)
    assert not result.has_unresolved


def test_real_marker_audit_positive_preparation_clause_keeps_its_source_association():
    import json
    from pathlib import Path
    from app.services.summary_facts import parse_extraction, prepare_audit_facts
    from app.services.summary_normalization import normalize_composition, normalize_extraction
    directory = Path(__file__).resolve().parents[2] / "docs/acceptance-reports/2026-10-08-grounded-summary-marker/results"
    paths = [directory / "normalized-marker-zh-short-trace.json", directory / "responses/01.json",
             directory / "responses/04.json"]
    originals = [path.read_bytes() for path in paths]
    trace, extract, audit = [json.loads(raw) for raw in originals]
    saved = trace["events"][0]["sources"][0]
    source = SourcePart(saved["id"], saved["text"], saved["global_start"])
    limits = FactLimits(max_summary_chars=800)
    normalized, _ = normalize_extraction(extract["content"])
    bank = parse_extraction(normalized, source, limits, "F1_")
    envelope = json.loads(audit["content"])
    combined = prepare_audit_facts(envelope["additional_facts"], [source], bank, limits)
    normalized = normalize_composition(envelope["output"], limits, final=True)
    result = api().resolve_references(normalized, combined)
    assert "S3" not in result.unresolved and "P5" not in result.unresolved
    assert next(binding for binding in result.bindings if binding.item_id == "P5").fact_ids == ("F1_4",)
    assert [item.text for item in result.candidate.summary] == [item.text for item in normalized.summary]
    assert [path.read_bytes() for path in paths] == originals


def test_exact_quote_does_not_replace_existing_claim_or_source():
    from dataclasses import replace

    module = api()
    bank = facts("A cache avoids repeated database requests.")
    bank = (replace(bank[0], claim="Caching reduces database load."),)
    before = asdict(bank[0])
    result = module.resolve_references(draft("A cache avoids repeated database requests."), bank)
    assert result.bindings[0].method == "exact_quote_suggestion"
    assert result.candidate.summary[0].fact_ids == ("F1",)
    assert asdict(bank[0]) == before
    with pytest.raises(FrozenInstanceError):
        result.unresolved = ("S1",)


@pytest.mark.parametrize("text, claim", [
    ("Caching lowers repeated database requests.", "A cache reduces repeated database requests."),
    ("数据库索引能够加快查询速度。", "建立数据库索引可以提升查询速度。"),
])
def test_bilingual_lexical_association_without_model_ids(text, claim):
    result = api().resolve_references(draft(text), facts(claim, "Video subtitles provide timestamps."))
    assert result.candidate.summary[0].fact_ids == ("F1",)
    assert result.bindings[0].method == "lexical_suggestion"
    assert result.bindings[0].suggestions[0].shared_terms
    assert 0 < result.bindings[0].score <= 1


@pytest.mark.parametrize("text", ["This is important for the system.", "这个方法很重要。", "Cache."])
def test_low_information_cannot_bind_all_facts_even_with_hints(text):
    result = api().resolve_references(draft(text, hints=("F1", "F2")),
                                      facts("The cache improves system performance.", "The system records important events."))
    assert result.candidate.summary[0].fact_ids == ()
    assert result.unresolved == ("S1",)
    assert result.has_unresolved


def test_unknown_ids_are_preserved_as_diagnostics_not_spelling_corrected():
    result = api().resolve_references(draft("Cache reduces request latency.", hints=("f1", "F99", "F99")),
                                      facts("Cache reduces request latency."))
    assert result.candidate.summary[0].fact_ids == ("F1",)
    assert [(entry.item_id, entry.hint_id, entry.reason) for entry in result.invalid_hints] == [
        ("S1", "f1", "unknown_fact"), ("S1", "F99", "unknown_fact")]


def test_tied_equivalent_candidates_require_content_related_hint_to_disambiguate():
    bank = facts("Redis cache reduces request latency.", "Memory cache reduces request latency.")
    module = api()
    unresolved = module.resolve_references(draft("Cache reduces request latency."), bank)
    assert unresolved.ambiguous == ("S1",)
    assert unresolved.candidate.summary[0].fact_ids == ()
    selected = module.resolve_references(draft("Cache reduces request latency.", hints=("F2",)), bank)
    assert selected.candidate.summary[0].fact_ids == ("F2",)
    assert selected.bindings[0].method == "hint_disambiguated_suggestion"


def test_multiple_independent_facts_can_associate_to_one_unchanged_paragraph():
    text = "Caching reduces repeated database requests. Indexes speed up selective column lookups."
    result = api().resolve_references(draft(text), facts(
        "A cache reduces repeated database requests.",
        "Indexes accelerate selective column lookups.",
        "Video subtitles provide timestamps.",
    ))
    assert result.candidate.summary[0].text == text
    assert result.candidate.summary[0].fact_ids == ("F1", "F2")
    assert not result.has_unresolved


def test_fact_order_does_not_change_rank_or_selected_ids():
    module = api()
    bank = facts("A cache reduces repeated database requests.", "Indexes accelerate selective column lookups.")
    item = draft("Caching reduces repeated database requests. Indexes speed up selective column lookups.")
    assert module.resolve_references(item, bank) == module.resolve_references(item, tuple(reversed(bank)))


@pytest.mark.parametrize("text,claim,conflict", [
    ("Cache reduces request latency by 90 percent.", "Cache reduces request latency by 30 percent.", "numeric_conflict"),
    ("Cache reduces request latency.", "Cache does not reduce request latency.", "negation_conflict"),
    ("缓存不能减少数据库请求。", "缓存能够减少数据库请求。", "negation_conflict"),
])
def test_numbers_and_negation_do_not_turn_similarity_into_support(text, claim, conflict):
    result = api().resolve_references(draft(text, hints=("F1",)), facts(claim))
    assert result.candidate.summary[0].fact_ids == ()
    assert result.unresolved == ("S1",)
    assert conflict in result.bindings[0].suggestions[0].conflicts


@pytest.mark.parametrize("text,claim", [
    ("\u8bbe\u5907\u652f\u6301\u591a\u79cd\u4efb\u52a1", "\u8bbe\u5907\u652f\u6301\u4e0d\u540c\u4efb\u52a1"),
    ("\u8bbe\u5907\u80fd\u8bfb\u53d6\u6570\u636e", "\u8bbe\u5907\u65e0\u8bba\u4f4d\u7f6e\u5982\u4f55\u90fd\u80fd\u8bfb\u53d6\u6570\u636e"),
    ("设备能读取数据", "设备无论条件如何都能读取数据"),
    ("设备能读取数据", "设备无论怎样都能读取数据"),
    ("设备能读取数据", "设备无论怎么都能读取数据"),
    ("设备支持多种任务", "设备支持不同的任务"),
    ("设备支持多种类型的任务", "设备支持不同类型的任务"),
    ("设备能读取多个位置的数据", "设备能读取不同位置的数据"),
    ("程序支持多种语言", "程序支持不同语言"),
])
def test_nonnegative_zh_phrases_do_not_conflict_with_positive_text(text, claim):
    result = api().resolve_references(draft(text), facts(claim))
    assert result.candidate.summary[0].fact_ids == ("F1",)
    assert not result.has_unresolved
    assert "negation_conflict" not in result.bindings[0].suggestions[0].conflicts


@pytest.mark.parametrize("text,claim", [
    ("管理人员同意导出数据", "管理人员不同意导出数据"),
    ("设备同步用户数据", "设备不同步用户数据"),
    ("管理人员同情申请人", "管理人员不同情申请人"),
    ("新成员同化于主流文化", "新成员不同化于主流文化"),
])
def test_chinese_different_verb_still_counts_as_negation(text, claim):
    result = api().resolve_references(draft(text), facts(claim))
    assert result.candidate.summary[0].fact_ids == ()
    assert result.unresolved == ("S1",)
    assert "negation_conflict" in result.bindings[0].suggestions[0].conflicts


@pytest.mark.parametrize("text,claim", [
    ("设备设置与默认设置相同", "设备设置不同于默认设置"),
    ("设备采用同样任务", "设备采用不同任务"),
    ("设备采用不同任务", "设备采用同样任务"),
    ("设备采用相同类型", "设备采用不同类型"),
    ("设备采用不同类型", "设备采用相同类型"),
    ("设备支持一样的任务", "设备支持多种任务"),
])
def test_explicit_difference_and_sameness_conflict_in_either_direction(text, claim):
    result = api().resolve_references(draft(text), facts(claim))
    assert result.candidate.summary[0].fact_ids == ()
    assert result.unresolved == ("S1",)
    assert "negation_conflict" in result.bindings[0].suggestions[0].conflicts


def test_mixed_same_heads_do_not_cross_pair_across_distinct_subjects():
    text = "甲设备会采用不同任务，乙设备会采用相同任务"
    claim = "甲设备采用不同任务，乙设备采用相同任务"
    result = api().resolve_references(draft(text), facts(claim))
    assert result.candidate.summary[0].fact_ids == ("F1",)
    assert not result.has_unresolved
    assert "negation_conflict" not in result.bindings[0].suggestions[0].conflicts


@pytest.mark.parametrize("text,claim", [
    ("方案有论据支持", "方案无论据支持"),
    ("方案有论证依据", "方案无论证依据"),
])
def test_lack_of_evidence_is_not_a_concessive_wulun_clause(text, claim):
    result = api().resolve_references(draft(text), facts(claim))
    assert result.candidate.summary[0].fact_ids == ()
    assert result.unresolved == ("S1",)
    assert "negation_conflict" in result.bindings[0].suggestions[0].conflicts


def test_parameter_wulun_clause_with_totalizer_is_nonnegative():
    text = "系统输出状态总是稳定"
    claim = "系统无论输入取值如何，输出状态总是稳定"
    result = api().resolve_references(draft(text), facts(claim))
    assert result.candidate.summary[0].fact_ids == ("F1",)
    assert not result.has_unresolved
    assert "negation_conflict" not in result.bindings[0].suggestions[0].conflicts


@pytest.mark.parametrize("text,claim", [
    ("设备有用户数据访问权并能读取用户数据", "设备无用户数据访问权并能读取用户数据"),
    ("方案有数据记录并支持查询", "方案无数据记录并支持查询"),
    ("设备无论位置如何都能读取数据", "设备无论位置如何都不能读取数据"),
])
def test_real_wu_negation_and_negative_concession_still_conflict(text, claim):
    result = api().resolve_references(draft(text), facts(claim))
    assert result.candidate.summary[0].fact_ids == ()
    assert result.unresolved == ("S1",)
    assert "negation_conflict" in result.bindings[0].suggestions[0].conflicts


@pytest.mark.parametrize("text,claim", [
    ("设备支持任务", "设备不支持任务"),
    ("设备支持任务", "设备未支持任务"),
    ("设备能读取数据", "设备没有读取数据"),
    ("设备能读取数据", "设备不可读取数据"),
    ("设备能读取数据", "设备不能读取数据"),
    ("系统允许设备访问数据", "系统禁止设备访问数据"),
])
def test_chinese_negation_cues_still_reject_opposite_polarity(text, claim):
    result = api().resolve_references(draft(text), facts(claim))
    assert result.candidate.summary[0].fact_ids == ()
    assert result.unresolved == ("S1",)
    assert "negation_conflict" in result.bindings[0].suggestions[0].conflicts


def test_theme_hint_helps_related_point_but_does_not_supply_unwritten_claims():
    module = api()
    normalizer = importlib.import_module("app.services.summary_normalization")
    bank = facts("Redis cache reduces request latency.", "Memory cache reduces request latency.")
    point = normalizer.DraftItem("P1", "Cache reduces request latency.", "Caching")
    theme = normalizer.ThemeHint(1, "Redis cache", "Reduces request latency", (), (), ("F1",))
    result = module.resolve_references(draft(bank[0].claim, points=(point,), themes=(theme,)), bank)
    assert result.candidate.key_points[0].fact_ids == ("F1",)
    assert result.candidate.key_points[0].topic == "Caching"
    unrelated = normalizer.DraftItem("P1", "A useful method.", "Caching")
    result = module.resolve_references(draft(bank[0].claim, points=(unrelated,), themes=(theme,)), bank)
    assert result.candidate.key_points[0].fact_ids == ()
    assert "P1" in result.unresolved


def test_invalid_fact_bank_raises_bounded_error_without_raw_text():
    module = api()
    bank = facts("Private unique evidence not for errors.")
    with pytest.raises(module.ReferenceResolutionError, match="^duplicate_fact_id$"):
        module.resolve_references(draft("Private unique evidence not for errors."), bank + bank)


def test_chinese_adjacent_digits_cannot_escape_numeric_conflict_guard():
    result = api().resolve_references(draft("缓存让数据库请求减少90%。", hints=("F1",)),
                                      facts("缓存让数据库请求减少30%。"))
    assert result.candidate.summary[0].fact_ids == ()
    assert "numeric_conflict" in result.bindings[0].suggestions[0].conflicts


def test_theme_text_can_disambiguate_existing_related_candidates_without_ids():
    normalizer = importlib.import_module("app.services.summary_normalization")
    bank = facts("Redis cache reduces request latency.", "Memory cache reduces request latency.")
    point = normalizer.DraftItem("P1", "Cache reduces request latency.")
    theme = normalizer.ThemeHint(1, "Redis cache", "Reduces request latency", (), (), ())
    result = api().resolve_references(draft(bank[0].claim, points=(point,), themes=(theme,)), bank)
    assert result.candidate.key_points[0].fact_ids == ("F1",)
    assert result.bindings[1].method == "theme_disambiguated_suggestion"


def test_exact_duplicate_facts_remain_ambiguous_without_single_related_hint():
    bank = facts("Cache reduces request latency.", "Cache reduces request latency.")
    result = api().resolve_references(draft("Cache reduces request latency.", hints=("F1", "F2")), bank)
    assert result.ambiguous == ("S1",)
    assert result.candidate.summary[0].fact_ids == ()


def test_other_clause_negation_does_not_block_independent_paragraph_association():
    text = "Cache does not prevent stale results. Indexes accelerate selective column lookups."
    result = api().resolve_references(draft(text), facts(
        "Cache does not prevent stale results.", "Indexes accelerate selective column lookups."))
    assert result.candidate.summary[0].fact_ids == ("F1", "F2")
    assert not result.has_unresolved


def test_chinese_contracted_negation_preserves_polarity_association():
    result = api().resolve_references(draft("学生没准备的内容会造成课堂任务错位。"),
                                      facts("学生没有准备的内容会造成课堂任务错位。"))
    assert result.candidate.summary[0].fact_ids == ("F1",)


def test_decimal_quantity_remains_one_number_during_lexical_association():
    result = api().resolve_references(draft("Cache lowers repeated database requests by 30.5 percent."),
                                      facts("Cache reduces repeated database requests by 30.5 percent."))
    assert result.candidate.summary[0].fact_ids == ("F1",)
    assert not result.bindings[0].suggestions[0].conflicts


def test_written_point_and_fact_topics_narrow_already_related_candidates():
    from dataclasses import replace

    normalizer = importlib.import_module("app.services.summary_normalization")
    bank = facts("Redis cache reduces request latency.", "Memory cache reduces request latency.")
    bank = (replace(bank[0], topic="Networked caching"), replace(bank[1], topic="Local caching"))
    point = normalizer.DraftItem("P1", "Cache reduces request latency.", "Networked caching")
    result = api().resolve_references(draft(bank[0].claim, points=(point,)), bank)
    assert result.candidate.key_points[0].fact_ids == ("F1",)
    assert result.bindings[1].method == "topic_disambiguated_suggestion"


def test_empty_point_topic_gets_matched_fact_metadata_or_stable_general_label():
    normalizer = importlib.import_module("app.services.summary_normalization")
    bank = facts("Cache reduces request latency.")
    points = (normalizer.DraftItem("P1", bank[0].claim),
              normalizer.DraftItem("P2", "Unrelated photographs depict mountain wildlife."))
    result = api().resolve_references(draft(bank[0].claim, points=points), bank)
    assert result.candidate.key_points[0].topic == "Evidence"
    assert result.candidate.key_points[1].topic == "General"
    assert points[0].topic == points[1].topic == ""
    assert result.candidate.key_points[1].fact_ids == ()


def test_saved_failed_paragraph_can_enter_association_without_changing_artifacts():
    """Historical contract-shape characterization, not a quality acceptance."""
    import hashlib
    import json
    from pathlib import Path

    from app.services.summary_facts import parse_extraction
    from app.services.summary_normalization import normalize_composition

    directory = (Path(__file__).resolve().parents[2]
                 / "docs/acceptance-reports/2026-10-08-grounded-summary-prefix/results")
    paths = [directory / "responses/01.json", directory / "responses/02.json",
             directory / "organization-prefix-zh-short-trace.json"]
    originals = [path.read_bytes() for path in paths]
    extract, compose, trace = [json.loads(raw) for raw in originals]
    stored_source = trace["events"][0]["sources"][0]
    source = SourcePart(stored_source["id"], stored_source["text"], stored_source["global_start"])
    assert source.sha256 == stored_source["sha256"]
    bank = parse_extraction(extract["content"], source, FactLimits(), "F1_")
    normalized = normalize_composition(compose["content"], FactLimits())
    result = api().resolve_references(normalized, bank)
    assert result.candidate.summary[0].text == json.loads(compose["content"])["summary"]
    assert len(result.candidate.key_points) == 5
    assert result.candidate.key_points[0].fact_ids == ("F1_1",)
    known = {fact.id for fact in bank}
    assert all(set(binding.fact_ids) <= known for binding in result.bindings)
    assert all(set(suggestion.fact_id for suggestion in binding.suggestions) <= known
               for binding in result.bindings)
    assert [hashlib.sha256(path.read_bytes()).digest() for path in paths] == [
        hashlib.sha256(raw).digest() for raw in originals]
