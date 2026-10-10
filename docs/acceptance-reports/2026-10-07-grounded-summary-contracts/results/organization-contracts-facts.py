"""Pure evidence contracts for the summary pipeline.

The model selects caller-assigned sentence IDs instead of verbatim-copying
substrings; the caller resolves those IDs to exact cleaned-input spans. Spans
address the cleaned summary input, not subtitle timestamps. Exact sentence
selection establishes traceability; it does not establish semantic entailment.
"""

from dataclasses import dataclass
import hashlib
import json
import re
from collections.abc import Sequence


class FactValidationError(ValueError):
    """A bounded reason code, never raw source text or model payload."""


@dataclass(frozen=True)
class SourcePart:
    id: str
    text: str
    global_start: int = 0

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Sentence:
    """A caller-split unit of a SourcePart. ``start``/``end`` are relative to the part."""

    id: str
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class FactLimits:
    max_facts_per_chunk: int = 12
    max_evidence_sentences: int = 128
    max_point_chars: int = 240
    max_topic_chars: int = 120
    max_claim_chars: int = 600
    max_attribution_chars: int = 120
    max_summary_chars: int = 4000
    max_items: int = 7

    def __post_init__(self):
        ceilings = {"max_facts_per_chunk": 48, "max_evidence_sentences": 256,
                    "max_point_chars": 4000, "max_topic_chars": 1000,
                    "max_claim_chars": 4000, "max_attribution_chars": 1000,
                    "max_summary_chars": 20000, "max_items": 7}
        for name, value in vars(self).items():
            minimum = 1
            if type(value) is not int or not minimum <= value <= ceilings[name]:
                raise FactValidationError("invalid_limits")


@dataclass(frozen=True)
class GroundedFact:
    id: str
    source_id: str
    source_sha256: str
    start: int
    end: int
    quote: str
    topic: str
    claim: str
    evidence_indices: tuple[int, ...]
    attribution: str
    importance: str
    attribution_start: int | None = None
    attribution_end: int | None = None


@dataclass(frozen=True)
class SummaryClaim:
    id: str
    text: str
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class SummaryPoint:
    id: str
    topic: str
    text: str
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class CandidateSummary:
    summary: tuple[SummaryClaim, ...]
    key_points: tuple[SummaryPoint, ...]

    @property
    def public_summary(self) -> str:
        return " ".join(claim.text for claim in self.summary)

    @property
    def public_key_points(self) -> tuple[str, ...]:
        return tuple(point.text for point in self.key_points)


@dataclass(frozen=True)
class ThemePlan:
    id: str
    topic: str
    principle: str
    conditions: tuple[str, ...]
    consequences: tuple[str, ...]
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class PlannedComposition:
    candidate: CandidateSummary
    themes: tuple[ThemePlan, ...]


@dataclass(frozen=True)
class AuditCheck:
    item_id: str
    supported: bool
    qualifiers_preserved: bool
    attribution_preserved: bool
    scope_preserved: bool


@dataclass(frozen=True)
class AuditResult:
    facts: tuple[GroundedFact, ...]
    candidate: CandidateSummary
    checks: tuple[AuditCheck, ...]


def split_sentences(part: SourcePart) -> tuple[Sentence, ...]:
    """Deterministic caller sentence split: one non-empty cleaned line each.

    The cleaned input is newline-joined deduped caption lines, so each line is
    the natural, rubric-aligned evidence unit. Sentence ``text`` is an exact
    slice of ``part.text``; IDs are caller-generated and never model-chosen.
    """
    sentences = []
    index = 1
    start = 0
    for line in part.text.split("\n"):
        if line:
            sentences.append(Sentence(f"{part.id}_s{index}", line, start, start + len(line)))
            index += 1
        start += len(line) + 1
    return tuple(sentences)


def parse_candidate(payload: dict | str, facts: Sequence[GroundedFact], limits: FactLimits,
                    *, final: bool = True, require_core_coverage: bool = False) -> CandidateSummary:
    known = _fact_index(facts)
    obj = _object(payload, {"summary", "key_points"})
    # The one planned audit can shorten bounded preliminary wording. Final
    # output always keeps the configured hard ceiling; no text is truncated.
    summary_limit = limits.max_summary_chars if final else 2 * limits.max_summary_chars
    summary_items = limits.max_items if final else 2 * limits.max_items
    statements, points = [], []
    for index, record in enumerate(_list(obj["summary"], 1, summary_items), 1):
        item = _object(record, {"text", "fact_ids"})
        statements.append(SummaryClaim(f"S{index}", _text(item["text"], summary_limit),
                                       _references(item["fact_ids"], known)))
    if len(" ".join(item.text for item in statements)) > summary_limit:
        raise FactValidationError("summary_too_long")
    if len({_normalized(item.text) for item in statements}) != len(statements):
        raise FactValidationError("duplicate_summary")
    seen_text, seen_refs = set(), set()
    for index, record in enumerate(_list(obj["key_points"], 1, limits.max_items), 1):
        item = _object(record, {"topic", "text", "fact_ids"})
        text = _text(item["text"], limits.max_point_chars if final else max(limits.max_claim_chars, limits.max_point_chars))
        refs = _references(item["fact_ids"], known)
        if _normalized(text) in seen_text or not set(refs) - seen_refs:
            raise FactValidationError("duplicate_point")
        seen_text.add(_normalized(text))
        seen_refs.update(refs)
        points.append(SummaryPoint(f"P{index}", _text(item["topic"], limits.max_topic_chars), text, refs))
    result = CandidateSummary(tuple(statements), tuple(points))
    if require_core_coverage:
        used = {identifier for item in (*result.summary, *result.key_points) for identifier in item.fact_ids}
        if any(item.importance == "core" and item.id not in used for item in known.values()):
            raise FactValidationError("missing_core_fact")
    return result


def parse_composition(payload: dict | str, facts: Sequence[GroundedFact], limits: FactLimits,
                      *, require_core_coverage: bool = False) -> CandidateSummary:
    """Resolve fixed model slots without discarding unknown or invalid points."""
    slots = [f"point_{index}" for index in range(1, limits.max_items + 1)]
    obj = _object(payload, {"summary", *slots})
    points, unused = [], False
    for slot in slots:
        item = obj[slot]
        if item is None:
            unused = True
        elif unused:
            raise FactValidationError("nontrailing_empty_slot")
        else:
            points.append(item)
    return parse_candidate({"summary": obj["summary"], "key_points": points}, facts, limits,
                           final=False, require_core_coverage=require_core_coverage)


def parse_planned_composition(payload: dict | str, facts: Sequence[GroundedFact],
                              limits: FactLimits) -> PlannedComposition:
    """Validate global themes, then preserve the original candidate contract.

    Allocating a fact to a theme does not prove its meaning appears in the
    candidate text. Missing core references remain for the one planned audit.
    """
    slots = [f"point_{index}" for index in range(1, limits.max_items + 1)]
    obj = _object(payload, {"summary", "theme_plan", *slots})
    if not isinstance(obj["theme_plan"], dict):
        raise FactValidationError("invalid_fields")
    if not isinstance(obj["summary"], list) or any(not isinstance(item, dict) for item in obj["summary"]):
        raise FactValidationError("invalid_fields")
    if any(obj[slot] is not None and not isinstance(obj[slot], dict) for slot in slots):
        raise FactValidationError("invalid_fields")
    theme_slots = [f"theme_{index}" for index in range(1, limits.max_items + 1)]
    plan = _object(obj["theme_plan"], set(theme_slots))
    known = _fact_index(facts)
    themes, unused = [], False
    fields = {"topic", "principle", "conditions", "consequences", "fact_ids"}
    for index, slot in enumerate(theme_slots, 1):
        record = plan[slot]
        if record is None:
            unused = True
        elif unused:
            raise FactValidationError("nontrailing_empty_slot")
        else:
            if not isinstance(record, dict):
                raise FactValidationError("invalid_fields")
            item = _object(record, fields)
            themes.append(ThemePlan(
                f"T{index}", _text(item["topic"], limits.max_topic_chars),
                _text(item["principle"], limits.max_claim_chars),
                tuple(_text(text, limits.max_point_chars)
                      for text in _list(item["conditions"], 0, limits.max_items)),
                tuple(_text(text, limits.max_point_chars)
                      for text in _list(item["consequences"], 0, limits.max_items)),
                _references(item["fact_ids"], known)))
    candidate = parse_composition({"summary": obj["summary"],
                                   **{slot: obj[slot] for slot in slots}}, facts, limits)
    if len(themes) != len(candidate.key_points):
        raise FactValidationError("theme_point_count_mismatch")
    for theme, point in zip(themes, candidate.key_points):
        if not set(point.fact_ids) <= set(theme.fact_ids):
            raise FactValidationError("point_outside_theme")
    return PlannedComposition(candidate, tuple(themes))


def _fact_index(facts):
    if not isinstance(facts, (list, tuple)) or not facts:
        raise FactValidationError("invalid_facts")
    result = {}
    for item in facts:
        if not isinstance(item, GroundedFact):
            raise FactValidationError("invalid_facts")
        _validate_id(item.id)
        if item.id in result:
            raise FactValidationError("duplicate_fact_id")
        result[item.id] = item
    return result


def _references(value, known):
    refs = _list(value, 1, len(known))
    if any(not isinstance(ref, str) or ref not in known for ref in refs):
        raise FactValidationError("unknown_fact")
    if len(set(refs)) != len(refs):
        raise FactValidationError("duplicate_reference")
    return tuple(refs)


def parse_audit(payload: dict | str, sources: Sequence[SourcePart], facts: Sequence[GroundedFact],
                limits: FactLimits) -> AuditResult:
    """Validate grounding, coverage and the model's complete check report.

    Accepted check flags are the audit model's assertions, not independent
    proof of semantic truth or of whether every important fact was extracted.
    """
    original = _fact_index(facts)
    if not isinstance(sources, (list, tuple)) or not sources:
        raise FactValidationError("invalid_sources")
    source_map, sentence_map = {}, {}
    for source in sources:
        _validate_source(source)
        if source.id in source_map:
            raise FactValidationError("duplicate_source_id")
        source_map[source.id] = source
        sentence_map[source.id] = split_sentences(source)
    # The caller's already extracted facts remain grounded in these exact
    # sources. Audit additions cannot switch sources or manufacture offsets.
    for item in original.values():
        source = source_map.get(item.source_id)
        if source is None:
            raise FactValidationError("unknown_source")
        rebuilt = _parse_fact({"topic": item.topic, "claim": item.claim,
                               "evidence": list(item.evidence_indices), "attribution": item.attribution,
                               "importance": item.importance}, source, sentence_map[source.id], limits, item.id)
        if rebuilt != item:
            raise FactValidationError("invalid_fact_trace")
    obj = _object(payload, {"additional_facts", "output", "checks"})
    combined = list(original.values())
    for index, record in enumerate(_list(obj["additional_facts"], 0, limits.max_facts_per_chunk), 1):
        item = _object(record, _FACT_FIELDS | {"source_id"})
        source_id = item["source_id"]
        if not isinstance(source_id, str) or source_id not in source_map:
            raise FactValidationError("unknown_source")
        identifier = f"A{index}"
        if identifier in original:
            raise FactValidationError("duplicate_fact_id")
        combined.append(_parse_fact({key: item[key] for key in _FACT_FIELDS}, source_map[source_id],
                                    sentence_map[source_id], limits, identifier))
    candidate = parse_candidate(obj["output"], combined, limits, require_core_coverage=True)
    expected = {item.id for item in (*candidate.summary, *candidate.key_points)}
    checks, seen = [], set()
    fields = {"supported", "qualifiers_preserved", "attribution_preserved", "scope_preserved"}
    for record in _list(obj["checks"], len(expected), len(expected)):
        item = _object(record, fields | {"item_id"})
        identifier = item["item_id"]
        if not isinstance(identifier, str) or identifier not in expected or identifier in seen:
            raise FactValidationError("invalid_check_id")
        if any(item[field] is not True for field in fields):
            raise FactValidationError("audit_not_supported")
        seen.add(identifier)
        checks.append(AuditCheck(identifier, True, True, True, True))
    return AuditResult(tuple(combined), candidate, tuple(checks))


def parse_facts(payload: dict | str, source: SourcePart, limits: FactLimits,
                id_prefix: str) -> tuple[GroundedFact, ...]:
    _validate_source(source)
    _validate_id(id_prefix)
    sentences = split_sentences(source)
    obj = _object(payload, {"facts"})
    records = _list(obj["facts"], 1, limits.max_facts_per_chunk)
    _validate_id(f"{id_prefix}{len(records)}")
    return tuple(_parse_fact(record, source, sentences, limits, f"{id_prefix}{index}")
                 for index, record in enumerate(records, 1))


def parse_extraction(payload: dict | str, source: SourcePart, limits: FactLimits,
                     id_prefix: str) -> tuple[GroundedFact, ...]:
    """Resolve finite fact slots using the existing source and evidence contract."""
    slots = [f"fact_{index}" for index in range(1, limits.max_facts_per_chunk + 1)]
    obj = _object(payload, set(slots))
    records, unused = [], False
    for slot in slots:
        record = obj[slot]
        if record is None:
            unused = True
        elif unused:
            raise FactValidationError("nontrailing_empty_slot")
        else:
            if not isinstance(record, dict):
                raise FactValidationError("invalid_fields")
            records.append(record)
    return parse_facts({"facts": records}, source, limits, id_prefix)


def _validate_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value):
        raise FactValidationError("invalid_id")


def _validate_source(source):
    if not isinstance(source, SourcePart):
        raise FactValidationError("invalid_source")
    _validate_id(source.id)
    if not isinstance(source.text, str) or not source.text.strip():
        raise FactValidationError("invalid_source")
    if type(source.global_start) is not int or source.global_start < 0:
        raise FactValidationError("invalid_source")


def _object(payload, keys):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload, object_pairs_hook=_unique_object)
        except (ValueError, TypeError, RecursionError):
            raise FactValidationError("invalid_json") from None
    if not isinstance(payload, dict) or set(payload) != keys:
        raise FactValidationError("invalid_fields")
    return payload


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FactValidationError("duplicate_json_field")
        result[key] = value
    return result


def _list(value, minimum, maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise FactValidationError("invalid_count")
    return value


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise FactValidationError("invalid_text")
    return value.strip()


def _normalized(value):
    return " ".join(value.split())


_FACT_FIELDS = {"topic", "claim", "evidence", "attribution", "importance"}


def _parse_fact(record, source, sentences, limits, identifier):
    obj = _object(record, _FACT_FIELDS)
    topic = _text(obj["topic"], limits.max_topic_chars)
    claim = _text(obj["claim"], limits.max_claim_chars)
    evidence = _list(obj["evidence"], 1, limits.max_evidence_sentences)
    if any(type(e) is not int for e in evidence):
        raise FactValidationError("invalid_evidence")
    if any(e < 1 or e > len(sentences) for e in evidence):
        raise FactValidationError("unknown_evidence")
    if len(set(evidence)) != len(evidence):
        raise FactValidationError("duplicate_evidence")
    positions = sorted(evidence)
    selected = [sentences[i - 1] for i in positions]
    begin, end = selected[0].start, selected[-1].end
    quote = "\n".join(sentence.text for sentence in selected)
    attribution = _text(obj["attribution"], limits.max_attribution_chars)
    attribution_start, attribution_end = None, None
    if attribution != "source":
        # A header may identify the speaker outside a particular claim's
        # evidence. Bind that name to its first exact occurrence in this same
        # source part, never a different part. Lexical evidence does not prove
        # who made a particular statement; that judgment belongs to the audit.
        named_start = source.text.find(attribution)
        if named_start < 0:
            raise FactValidationError("attribution_not_found")
        named_end = named_start + len(attribution)
        attribution_start = source.global_start + named_start
        attribution_end = source.global_start + named_end
    importance = obj["importance"]
    if not isinstance(importance, str) or importance not in {"core", "support"}:
        raise FactValidationError("invalid_importance")
    return GroundedFact(identifier, source.id, source.sha256,
                        source.global_start + begin, source.global_start + end,
                        quote, topic, claim, tuple(positions), attribution, importance,
                        attribution_start, attribution_end)
