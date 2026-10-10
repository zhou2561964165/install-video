"""Pure, bounded identity and theme-ownership diagnostics.

These checks establish literal source bindings and explicit DTO relationships,
never semantic entailment, universal name recognition or thematic distinctness.
They do not rewrite text, infer aliases, change references or make model calls.
"""

from collections.abc import Sequence
from dataclasses import dataclass
import re

from .summary_facts import CandidateSummary, FactValidationError, GroundedFact, SourcePart
from .summary_normalization import DraftItem, NormalizedDraft, ThemeHint


@dataclass(frozen=True)
class QualityIssue:
    reason: str
    item_id: str
    fact_ids: tuple[str, ...] = ()
    output_start: int | None = None
    output_end: int | None = None
    surface: str = ""
    related_item_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttributionLiteral:
    surface: str
    source_id: str
    source_sha256: str
    source_start: int
    source_end: int
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class AttributionPolicy:
    literals: tuple[AttributionLiteral, ...]
    generic_allowed: bool = True


@dataclass(frozen=True)
class IdentityBinding:
    item_id: str
    surface: str
    output_start: int
    output_end: int
    source_id: str
    source_sha256: str
    source_start: int
    source_end: int
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class QualityReport:
    issues: tuple[QualityIssue, ...]
    identities: tuple[IdentityBinding, ...]
    attribution_policy: AttributionPolicy

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


def derive_attribution_policy(
    facts: Sequence[GroundedFact], sources: Sequence[SourcePart]
) -> AttributionPolicy:
    """Export only caller-verified attribution spellings and global source spans.

    The original source codec remains authoritative for the full fact bank.
    This helper independently checks the identity fields it exports; a corrupt
    bank raises existing SOURCE reason codes rather than an output diagnostic.
    Literal occurrence is not proof of who expressed a particular claim.
    """
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)) or not sources:
        raise FactValidationError("invalid_sources")
    source_map = {}
    for source in sources:
        if (not isinstance(source, SourcePart) or not isinstance(source.id, str)
                or not isinstance(source.text, str) or type(source.global_start) is not int
                or source.global_start < 0):
            raise FactValidationError("invalid_source")
        if source.id in source_map:
            raise FactValidationError("duplicate_source_id")
        source_map[source.id] = source
    if not isinstance(facts, Sequence) or isinstance(facts, (str, bytes)) or not facts:
        raise FactValidationError("invalid_facts")
    records, seen = {}, set()
    for fact in facts:
        if not isinstance(fact, GroundedFact) or not isinstance(fact.id, str):
            raise FactValidationError("invalid_facts")
        if fact.id in seen:
            raise FactValidationError("duplicate_fact_id")
        seen.add(fact.id)
        source = source_map.get(fact.source_id)
        if source is None:
            raise FactValidationError("unknown_source")
        if fact.source_sha256 != source.sha256:
            raise FactValidationError("invalid_fact_trace")
        if fact.attribution == "source":
            if fact.attribution_start is not None or fact.attribution_end is not None:
                raise FactValidationError("invalid_fact_trace")
            continue
        if not isinstance(fact.attribution, str) or not fact.attribution.strip():
            raise FactValidationError("attribution_not_found")
        start = source.text.find(fact.attribution)
        if start < 0:
            raise FactValidationError("attribution_not_found")
        start += source.global_start
        end = start + len(fact.attribution)
        if (type(fact.attribution_start) is not int or type(fact.attribution_end) is not int
                or (fact.attribution_start, fact.attribution_end) != (start, end)):
            raise FactValidationError("invalid_fact_trace")
        key = (fact.attribution, source.id, source.sha256, start, end)
        records.setdefault(key, []).append(fact.id)
    return AttributionPolicy(tuple(AttributionLiteral(*key, tuple(ids)) for key, ids in records.items()))


# Only explicit role/name/predicate or role/naming constructions are inspected.
# These are small language grammar rules, not a Chinese surname list or NER.
_ROLES_ZH = r"主讲人|演讲者|受访者|主持人|讲者|讲师|教师|教授|老师|作者"
_VERBS_ZH = r"介绍|指出|表示|认为|解释|强调|分享|讲解|讨论|提出|说明|建议"
_NAMING_ZH = r"名为|名字是|叫做|叫"
_ATTACHED_ZH = re.compile(
    rf"(?:{_ROLES_ZH})\s*(?!{_NAMING_ZH})(?P<name>[\u3400-\u9fff·]{{1,20}}?)\s*(?={_VERBS_ZH})"
)
_NAMED_ZH = re.compile(
    rf"(?:{_ROLES_ZH})\s*(?:{_NAMING_ZH})\s*[‘“\"]?(?P<name>[\u3400-\u9fff·]{{1,20}}?)"
    rf"(?=\s*(?:[’”\"，。！？；：、,.!?;:]|{_VERBS_ZH}|$))"
)
_NAMED_EN = re.compile(
    r"\b(?i:speaker|professor|instructor|lecturer|author|presenter|host)\s+"
    r"(?P<name>[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*){0,5})\s+"
    r"(?=(?i:introduces?|explains?|states?|says?|argues?|describes?|discusses?|notes?)\b)"
)
# Adverb sequences are normal role/predicate grammar, not named identities.
_MODIFIER_ZH = re.compile(
    r"(?:明确|详细|进一步|再次|主要|首先|随后|通常|同时|也|则|还|曾|已经|一直|反复|"
    r"直接|简单|认真|特别|在此|重点|简要|清楚|着重|继续|具体|分别|曾经|经常)+"
)
_MODIFIER_SUFFIX_ZH = re.compile(rf"{_MODIFIER_ZH.pattern}(?:地)?$")
_GENERIC_ZH = re.compile(r"^(?:们|本人|自己)$")
_RELATION_ZH = re.compile(r"^(?:对|把|将|在|从|向|以|为|通过|按照|根据)")


def _identity_candidates(text: str, bindings: Sequence[IdentityBinding]):
    seen = set()
    for grammar in (_NAMED_ZH, _ATTACHED_ZH, _NAMED_EN):
        for match in grammar.finditer(text):
            start, end = match.span("name")
            surface = text[start:end]
            if grammar is _ATTACHED_ZH and _RELATION_ZH.match(surface):
                continue
            if grammar in (_ATTACHED_ZH, _NAMED_ZH):
                modifier = _MODIFIER_SUFFIX_ZH.search(surface)
                if modifier is not None:
                    trimmed_end = start + modifier.start()
                    # Preserve a full verified spelling, and never cut through
                    # its occurrence merely because its tail resembles an adverb.
                    # This does not confirm the candidate; exact spans below do.
                    if not any(binding.output_start == start
                               and (binding.output_end == end
                                    or trimmed_end < binding.output_end <= end)
                               for binding in bindings):
                        end = trimmed_end
                        surface = text[start:end]
            if grammar is _ATTACHED_ZH:
                if not surface or _GENERIC_ZH.fullmatch(surface):
                    continue
            key = (start, end)
            if key not in seen:
                seen.add(key)
                yield start, end, surface


def _literal_spans(text: str, surface: str):
    cursor = 0
    while (start := text.find(surface, cursor)) >= 0:
        end = start + len(surface)
        cursor = end
        # Latin literal protection must not bind "Li" inside "Limits".
        if surface[0].isascii() and surface[0].isalnum() and start and text[start - 1].isalnum():
            continue
        if surface[-1].isascii() and surface[-1].isalnum() and end < len(text) and text[end].isalnum():
            continue
        yield start, end


def _label(value: str) -> str:
    return " ".join(value.split()).casefold()


def _theme_issues(draft, facts, candidate, required):
    themes, points = draft.theme_hints, draft.key_points
    if not themes:
        return [QualityIssue("missing_theme_plan", "P1")] if required else []
    issues = []
    if len(themes) != len(points):
        issues.append(QualityIssue("theme_point_count_mismatch", "P1"))
    known = {fact.id for fact in facts}
    labels, owners = {}, {}
    for position, theme in enumerate(themes, 1):
        item_id = f"P{position}"
        valid = (isinstance(theme, ThemeHint) and type(theme.point_index) is int
            and isinstance(theme.topic, str) and bool(theme.topic.strip())
            and isinstance(theme.principle, str) and bool(theme.principle.strip())
            and all(isinstance(values, tuple) and all(isinstance(value, str) and value.strip() for value in values)
                    for values in (theme.conditions, theme.consequences, theme.hint_ids)))
        if not valid:
            issues.append(QualityIssue("invalid_theme_shape", item_id))
            continue
        if theme.point_index != position or position > len(points) or points[position - 1].id != item_id:
            issues.append(QualityIssue("theme_point_mismatch", item_id))
        elif _label(points[position - 1].topic) != _label(theme.topic):
            issues.append(QualityIssue("theme_point_topic_mismatch", item_id))
        label = _label(theme.topic)
        if label in labels:
            issues.append(QualityIssue("duplicate_theme_label", item_id, related_item_ids=(labels[label],)))
        else:
            labels[label] = item_id
        if not theme.hint_ids:
            issues.append(QualityIssue("empty_theme_ownership", item_id))
        local = set()
        for identifier in theme.hint_ids:
            if identifier not in known:
                issues.append(QualityIssue("unknown_theme_fact", item_id, (identifier,)))
            elif identifier in owners:
                issues.append(QualityIssue("duplicate_theme_ownership", item_id, (identifier,),
                                          related_item_ids=(owners[identifier],)))
            else:
                owners[identifier] = item_id
            if identifier in local:
                issues.append(QualityIssue("duplicate_theme_fact", item_id, (identifier,)))
            local.add(identifier)
    # Only actual program-associated summary references can exempt a core fact.
    # Draft hint IDs alone never demonstrate even reference coverage.
    summary_ids = {identifier for item in candidate.summary for identifier in item.fact_ids} if candidate else set()
    for fact in facts:
        if fact.importance == "core" and fact.id not in owners and fact.id not in summary_ids:
            issues.append(QualityIssue("core_theme_gap", "S1", (fact.id,)))
    return issues


def inspect_quality(
    draft: NormalizedDraft,
    facts: Sequence[GroundedFact],
    sources: Sequence[SourcePart],
    *,
    require_theme_plan: bool = False,
    candidate: CandidateSummary | None = None,
) -> QualityReport:
    """Inspect explicit metadata relationships and bounded identity expressions.

    Identity output offsets are local to the item; source offsets are global to
    cleaned source input. Unknown role-bound surfaces are diagnostics, not a
    finding that the person cannot exist. Names outside the supported grammar
    remain for source-aware semantic audit. Different theme labels are never
    asserted to be different meanings, and ID coverage never proves clauses.
    """
    policy = derive_attribution_policy(facts, sources)
    if (not isinstance(draft, NormalizedDraft) or type(require_theme_plan) is not bool
            or not isinstance(draft.summary, tuple) or not isinstance(draft.key_points, tuple)
            or not isinstance(draft.theme_hints, tuple)
            or any(not isinstance(item, DraftItem) or not isinstance(item.id, str)
                   or not isinstance(item.text, str) or not isinstance(item.topic, str)
                   for item in (*draft.summary, *draft.key_points))
            or (candidate is not None and not isinstance(candidate, CandidateSummary))):
        return QualityReport((QualityIssue("invalid_quality_input", "S1"),), (), policy)
    candidate_issue = ()
    if candidate is not None:
        known = {fact.id for fact in facts}
        if (not isinstance(candidate.summary, tuple)
                or any(not hasattr(item, "id") or not hasattr(item, "text") or not hasattr(item, "fact_ids")
                       or not isinstance(item.fact_ids, tuple)
                       or any(type(identifier) is not str or identifier not in known
                              for identifier in item.fact_ids) for item in candidate.summary)
                or [(item.id, item.text) for item in candidate.summary] != [(item.id, item.text) for item in draft.summary]):
            candidate_issue = (QualityIssue("candidate_draft_mismatch", "S1"),)
            candidate = None
    issues = [*candidate_issue, *_theme_issues(draft, facts, candidate, require_theme_plan)]
    identities = []
    for item in (*draft.summary, *draft.key_points):
        bindings = []
        for literal in policy.literals:
            for start, end in _literal_spans(item.text, literal.surface):
                bindings.append(IdentityBinding(item.id, literal.surface, start, end,
                    literal.source_id, literal.source_sha256, literal.source_start,
                    literal.source_end, literal.fact_ids))
        identities.extend(sorted(bindings, key=lambda entry: (entry.output_start, entry.output_end, entry.source_id)))
        for start, end, surface in _identity_candidates(item.text, bindings):
            if not any((binding.output_start, binding.output_end) == (start, end) for binding in bindings):
                issues.append(QualityIssue("unconfirmed_identity", item.id, output_start=start,
                                          output_end=end, surface=surface))
    return QualityReport(tuple(issues), tuple(identities), policy)
