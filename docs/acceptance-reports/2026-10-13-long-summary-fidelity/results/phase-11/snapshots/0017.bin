"""Pure, deterministic source association suggestions, never entailment proofs.

Only caller-validated facts may enter this module. A resolved reference still
requires the original source, core-coverage and semantic audit checks before
publication. Draft wording and the fact bank are never changed here.
"""

from collections.abc import Sequence
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

from .summary_facts import CandidateSummary, GroundedFact, SummaryClaim, SummaryPoint

if TYPE_CHECKING:
    from .summary_normalization import DraftItem, NormalizedDraft


class ReferenceResolutionError(ValueError):
    """A bounded reason code without model or source text."""


@dataclass(frozen=True)
class ReferenceSuggestion:
    fact_id: str
    score: float
    shared_terms: tuple[str, ...]
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceBinding:
    item_id: str
    fact_ids: tuple[str, ...]
    method: str
    score: float
    suggestions: tuple[ReferenceSuggestion, ...] = ()


@dataclass(frozen=True)
class InvalidHint:
    item_id: str
    hint_id: str
    reason: str


@dataclass(frozen=True)
class ReferenceResolution:
    candidate: CandidateSummary
    bindings: tuple[ReferenceBinding, ...]
    unresolved: tuple[str, ...] = ()
    ambiguous: tuple[str, ...] = ()
    invalid_hints: tuple[InvalidHint, ...] = ()

    @property
    def has_unresolved(self) -> bool:
        """Final callers must reject either kind of unresolved association."""
        return bool(self.unresolved or self.ambiguous)


# A small language stop list excludes grammatical and generic boilerplate.
# No synonyms, embeddings, topic taxonomy or rubric-specific answers are used.
_STOP_EN = frozenset("a an the and or but as at by for from in into of on to with is are was were be been being this that these those it its they their we our you your can could may might will would should do does did has have had important useful method system information result results".split())
_STOP_ZH = ("这个", "那个", "这些", "那些", "我们", "你们", "他们", "可以", "能够", "应该", "需要", "因此", "所以", "通过", "进行", "一个", "方法", "重要", "有用")
_EN = re.compile(r"[a-z]+(?:'[a-z]+)?", re.I)
_ZH = re.compile(r"[\u3400-\u9fff]+")
_NUMBER = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?:%|％)?")
_NEGATION = re.compile(r"\b(?:no|not|never|cannot|without|\w+n't)\b|不(?!同(?:的|任务|类型|位置|语言))|未|无(?!论)|没|禁止|避免", re.I)
_WULUN_CONCESSION = re.compile(r"无论(?:[\u3400-\u9fff]{1,4}(?:如何|怎样|怎么|是否)|如何|怎样|怎么|是否)[^。！？；;\n]{0,40}(?:都|也|总是)")
_DIFFERENCE_HEAD = re.compile(r"(?:不同|多种)(?:的)?(?P<head>[\u3400-\u9fff]{2})")
_SAMENESS_HEAD = re.compile(r"(?:同样|相同|一样)(?:的)?(?P<head>[\u3400-\u9fff]{2})")
_SEGMENT = re.compile(r"\.(?!\d)|[!?。！？;；\n]+")
_MIN_SCORE = 0.28
_AMBIGUITY_MARGIN = 0.08


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def _has_negation(text: str) -> bool:
    if _NEGATION.search(text):
        return True
    return any(_WULUN_CONCESSION.match(text, marker.start()) is None
               for marker in re.finditer("无论", text))


def _negation_conflict(left: str, right: str) -> bool:
    if _has_negation(left) != _has_negation(right):
        return True
    left_differences = set(_DIFFERENCE_HEAD.findall(left))
    right_differences = set(_DIFFERENCE_HEAD.findall(right))
    left_sameness = set(_SAMENESS_HEAD.findall(left))
    right_sameness = set(_SAMENESS_HEAD.findall(right))
    left_exclusive_differences = left_differences - left_sameness
    right_exclusive_differences = right_differences - right_sameness
    left_exclusive_sameness = left_sameness - left_differences
    right_exclusive_sameness = right_sameness - right_differences
    return bool((left_exclusive_differences & right_exclusive_sameness)
                or (right_exclusive_differences & left_exclusive_sameness))


def _terms(text: str) -> frozenset[str]:
    english = {word for word in _EN.findall(text.casefold()) if word not in _STOP_EN and len(word) > 2}
    # Plurals share an anchor; no speculative synonym rewriting is performed.
    english = {word[:-1] if word.endswith("s") and not word.endswith("ss") and len(word) > 4 else word
               for word in english}
    chinese = text
    for stop in _STOP_ZH:
        chinese = chinese.replace(stop, " ")
    segments = _ZH.findall(chinese)
    return frozenset(english | {segment[index:index + width] for segment in segments
                               for width in (2, 3, 4) for index in range(len(segment) - width + 1)})


def _substantive(terms: set[str] | frozenset[str]) -> bool:
    english = {term for term in terms if _EN.fullmatch(term)}
    chinese = {term for term in terms if _ZH.fullmatch(term)}
    return (len(english) >= 2 or any(len(term) >= 4 for term in chinese)
            or (len({term for term in chinese if len(term) == 2}) >= 3
                and len(set("".join(chinese))) >= 5))


def _weight(terms: set[str] | frozenset[str]) -> int:
    return sum(min(len(term), 6) for term in terms)


def _lexical(text: str, evidence: str) -> tuple[float, frozenset[str]]:
    return _lexical_terms(_terms(text), _terms(evidence))


def _lexical_terms(left: frozenset[str], right: frozenset[str]) -> tuple[float, frozenset[str]]:
    shared = left & right
    if not _substantive(shared):
        return 0.0, shared
    coverage = _weight(shared)
    score = 0.75 * coverage / max(_weight(left), 1) + 0.25 * coverage / max(_weight(right), 1)
    return score, shared


def _suggestion(text: str, fact: GroundedFact) -> ReferenceSuggestion | None:
    # Clause views only select evidence associations; the returned text remains
    # the entire original paragraph. Comparing local views avoids another
    # clause's numbers or negation blocking an independent fact suggestion.
    segments = tuple(segment for segment in _SEGMENT.split(text) if segment.strip()) or (text,)
    matches = []
    evidence_views = []
    for original in (fact.claim, fact.quote):
        # Compare corresponding clauses on both sides. A negative clause
        # elsewhere in a compound fact must not negate a positive clause.
        # Caption line breaks alone do not establish a clause boundary.
        evidence = " ".join(original.splitlines())
        views = dict.fromkeys((evidence, *(part for part in _SEGMENT.split(evidence) if part.strip())))
        evidence_views.extend((view, _terms(view)) for view in views)
    for segment in segments:
        terms = _terms(segment)
        for view, evidence_terms in evidence_views:
            score, shared = _lexical_terms(terms, evidence_terms)
            matches.append((score, tuple(sorted(shared)), segment, view))
    score, shared, segment, evidence = max(matches, key=lambda entry: (entry[0], entry[1], entry[2], entry[3]))
    if score < _MIN_SCORE:
        return None
    conflicts = []
    numbers = set(_NUMBER.findall(segment))
    if numbers and not numbers <= set(_NUMBER.findall(evidence)):
        conflicts.append("numeric_conflict")
    if _negation_conflict(segment, evidence):
        conflicts.append("negation_conflict")
    return ReferenceSuggestion(fact.id, round(score, 6), shared, tuple(conflicts))


def _select(suggestions: tuple[ReferenceSuggestion, ...], hint_ids: frozenset[str]) -> tuple[tuple[str, ...], str]:
    eligible = [entry for entry in suggestions if not entry.conflicts]
    if not eligible:
        return (), "unresolved_suggestion"
    selected = [eligible[0]]
    ambiguous = False
    used_hint = False
    for entry in eligible[1:]:
        anchors = frozenset(entry.shared_terms)
        previous_anchors = frozenset(term for previous in selected for term in previous.shared_terms)
        if _substantive(anchors - previous_anchors) and _substantive(previous_anchors - anchors):
            selected.append(entry)
            continue
        rivals = [previous for previous in selected
                  if abs(previous.score - entry.score) <= _AMBIGUITY_MARGIN
                  and not _substantive(frozenset(previous.shared_terms) - anchors)]
        if not rivals:
            continue
        hinted = [candidate for candidate in (*rivals, entry) if candidate.fact_id in hint_ids]
        if len(hinted) == 1:
            for rival in rivals:
                selected.remove(rival)
            selected.append(hinted[0])
            used_hint = True
        else:
            ambiguous = True
    if ambiguous:
        return (), "ambiguous_suggestion"
    return tuple(sorted({entry.fact_id for entry in selected})), (
        "hint_disambiguated_suggestion" if used_hint else "lexical_suggestion")


def resolve_references(draft: "NormalizedDraft", facts: Sequence[GroundedFact]) -> ReferenceResolution:
    """Suggest known fact IDs from wording; hints never bypass content linkage.

    Empty references are a valid draft result for the existing audit, not a
    public final result. ``has_unresolved`` includes both no-match and ambiguity.
    ``suggestions`` retain bounded relevance scores, anchors and conflict codes
    for audit diagnostics; they never carry reconstructed source spans.
    """
    from .summary_normalization import NormalizedDraft

    if not isinstance(draft, NormalizedDraft):
        raise ReferenceResolutionError("invalid_draft")
    if not isinstance(facts, Sequence) or isinstance(facts, (str, bytes)) or not facts:
        raise ReferenceResolutionError("invalid_facts")
    known = {}
    for fact in facts:
        if (not isinstance(fact, GroundedFact) or not isinstance(fact.id, str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", fact.id)):
            raise ReferenceResolutionError("invalid_facts")
        if fact.id in known:
            raise ReferenceResolutionError("duplicate_fact_id")
        known[fact.id] = fact
    ordered = tuple(known[identifier] for identifier in sorted(known))
    themes = {f"P{theme.point_index}": theme for theme in draft.theme_hints}
    bindings, unresolved, ambiguous, invalid_hints = [], [], [], []
    for item in (*draft.summary, *draft.key_points):
        theme = themes.get(item.id)
        hints = tuple(dict.fromkeys((*item.hint_ids, *(theme.hint_ids if theme else ()))))
        exact_claim = [fact.id for fact in ordered if _normalized(item.text) == _normalized(fact.claim)]
        exact_quote = [fact.id for fact in ordered if _normalized(item.text) == _normalized(fact.quote)]
        exact = exact_claim or exact_quote
        if exact:
            suggestions = tuple(ReferenceSuggestion(identifier, 1.0, tuple(sorted(_terms(item.text)))) for identifier in exact)
        else:
            suggestions = tuple(sorted((suggestion for fact in ordered
                                        if (suggestion := _suggestion(item.text, fact)) is not None),
                                       key=lambda entry: (-entry.score, entry.fact_id)))
        associated = {suggestion.fact_id: suggestion for suggestion in suggestions}
        for hint in hints:
            if hint not in known:
                invalid_hints.append(InvalidHint(item.id, hint, "unknown_fact"))
            elif hint not in associated:
                invalid_hints.append(InvalidHint(item.id, hint, "unrelated_hint"))
            elif associated[hint].conflicts:
                invalid_hints.append(InvalidHint(item.id, hint, "conflicting_hint"))
        related_hints = frozenset(hint for hint in hints if hint in associated and not associated[hint].conflicts)
        if len(exact) == 1:
            references = tuple(exact)
            method = "exact_claim_suggestion" if exact_claim else "exact_quote_suggestion"
        elif exact:
            selected = tuple(identifier for identifier in exact if identifier in related_hints)
            references = selected if len(selected) == 1 else ()
            method = "hint_disambiguated_suggestion" if references else "ambiguous_suggestion"
        else:
            # A theme's written text can distinguish related candidates, but
            # cannot create a candidate lacking substantive item-text overlap.
            theme_choices = frozenset()
            if theme or item.topic:
                theme_text = " ".join((item.topic, *(
                    (theme.topic, theme.principle, *theme.conditions, *theme.consequences) if theme else ())))
                suggestions = tuple(sorted((ReferenceSuggestion(entry.fact_id,
                    round(min(1.0, entry.score + 0.1 * _lexical(theme_text,
                        " ".join((known[entry.fact_id].topic, known[entry.fact_id].claim)))[0]), 6),
                    entry.shared_terms, entry.conflicts) for entry in suggestions),
                    key=lambda entry: (-entry.score, entry.fact_id)))
                theme_terms = _terms(theme_text)
                matches = {entry.fact_id: theme_terms & (_terms(known[entry.fact_id].topic)
                           | _terms(known[entry.fact_id].claim)
                           | _terms(known[entry.fact_id].quote))
                           for entry in suggestions if not entry.conflicts}
                choices = []
                for identifier, anchors in matches.items():
                    others = frozenset(term for other_id, terms in matches.items()
                                       if other_id != identifier for term in terms)
                    # Distinctive written theme anchors can narrow candidates
                    # that already have substantive item-text association.
                    if anchors - others:
                        choices.append(identifier)
                if len(choices) == 1:
                    theme_choices = frozenset(choices)
            references, method = _select(suggestions, related_hints | theme_choices)
            if method == "hint_disambiguated_suggestion" and not related_hints:
                method = "theme_disambiguated_suggestion" if theme else "topic_disambiguated_suggestion"
        if method == "ambiguous_suggestion":
            ambiguous.append(item.id)
        elif not references:
            unresolved.append(item.id)
        score = max((entry.score for entry in suggestions if entry.fact_id in references), default=0.0)
        bindings.append(ReferenceBinding(item.id, references, method, score, suggestions))
    refs = {binding.item_id: binding.fact_ids for binding in bindings}
    candidate = CandidateSummary(
        tuple(SummaryClaim(item.id, item.text, refs[item.id]) for item in draft.summary),
        tuple(SummaryPoint(item.id, item.topic or (
            known[refs[item.id][0]].topic if refs[item.id] else "General"), item.text, refs[item.id])
            for item in draft.key_points))
    return ReferenceResolution(candidate, tuple(bindings), tuple(unresolved), tuple(ambiguous), tuple(invalid_hints))
