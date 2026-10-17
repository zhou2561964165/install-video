"""Local structured review feedback using the installed LCEL output parser.

No clients, tracing, source IDs, fact contracts or semantic success certificate.
"""
import json
import re
from functools import lru_cache
from typing import Literal

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, ConfigDict, Field, StrictStr, create_model, field_validator, model_validator


class SummaryReviewFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback: StrictStr

    @field_validator("feedback")
    @classmethod
    def nonempty_feedback(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Review feedback must be nonempty")
        return value.strip()


_PARSER = PydanticOutputParser(pydantic_object=SummaryReviewFeedback)


def parse_feedback(payload: dict) -> str:
    """The caller decodes JSON losslessly and rejects duplicate keys first."""
    return _PARSER.parse(json.dumps(payload, ensure_ascii=False)).feedback


def feedback_schema() -> dict:
    return SummaryReviewFeedback.model_json_schema()


class SourceCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessment: Literal["supported", "needs_correction", "uncertain"]
    source_quote: StrictStr = Field(min_length=1, max_length=120)
    finding: StrictStr = Field(min_length=1, max_length=80)


class SubjectCheck(BaseModel):
    """One bounded check; its fields bind evidence mechanically, not semantically."""

    model_config = ConfigDict(extra="forbid")
    assessment: Literal["supported", "needs_correction", "uncertain"]
    scope_relation: Literal["same", "draft_broader", "draft_narrower", "uncertain"]
    source_subject: StrictStr | None = Field(min_length=1, max_length=64)
    draft_subject: StrictStr | None = Field(min_length=1, max_length=64)
    source_quote: StrictStr | None = Field(min_length=1, max_length=120)
    finding: StrictStr = Field(min_length=1, max_length=80)

    @field_validator("source_subject", "draft_subject", "source_quote")
    @classmethod
    def optional_text_is_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Optional evidence fields must be null or nonempty")
        return value

    @field_validator("finding")
    @classmethod
    def finding_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Finding must be nonempty")
        return value

    @model_validator(mode="after")
    def supported_requires_bound_same_scope_evidence(self):
        if self.source_subject is not None and self.source_quote is None:
            raise ValueError("A source subject must be bound to a source quote")
        if self.assessment == "supported" and (
                self.scope_relation != "same" or self.source_subject is None
                or self.draft_subject is None or self.source_quote is None):
            raise ValueError("Supported requires a same-scope comparison with bound subjects and source quote")
        return self


def _validate_point_count(point_count: int) -> None:
    if type(point_count) is not int or not 1 <= point_count <= 32:
        raise ValueError("Invalid point count for a complete source review")


@lru_cache(maxsize=32)
def checks_model(point_count: int):
    _validate_point_count(point_count)
    return create_model(f"CompleteSourceChecks{point_count}",
        __config__=ConfigDict(extra="forbid"),
        **{f"target_{i}": (SourceCheck, ...) for i in range(point_count + 1)})


def checks_schema(point_count: int) -> dict:
    return checks_model(point_count).model_json_schema()


def checks_output_tokens(point_count: int) -> int:
    """Finite review allowance; the caller checks its configured ceiling."""
    _validate_point_count(point_count)
    return 128 + 256 * (point_count + 1)


def parse_checks(payload: dict, *, source: str, draft: dict) -> str:
    """Verify coverage and quote origin, never certify semantic correctness."""
    targets = [draft["summary"], *draft["key_points"]]
    parsed = PydanticOutputParser(pydantic_object=checks_model(len(targets) - 1)).parse(json.dumps(payload, ensure_ascii=False))
    def whitespace(text):
        return re.sub(r"\s+", " ", text).strip()
    original = whitespace(source)
    feedback = []
    for index, target in enumerate(targets):
        check = getattr(parsed, f"target_{index}")
        if (not whitespace(check.source_quote) or whitespace(check.source_quote) not in original
                or not check.finding.strip()):
            raise ValueError("Source review quote does not belong to its bound source")
        feedback.append(f"Target {index}:\nDraft assertion: {target}\nAssessment: {check.assessment}\nOriginal evidence: {check.source_quote}\nFinding: {check.finding}")
    return "\n\n".join(feedback)


@lru_cache(maxsize=32)
def subject_checks_model(point_count: int):
    _validate_point_count(point_count)
    return create_model(f"CompleteSubjectChecks{point_count}",
        __config__=ConfigDict(extra="forbid"),
        **{f"target_{i}": (SubjectCheck, ...) for i in range(point_count + 1)})


def subject_checks_schema(point_count: int) -> dict:
    return subject_checks_model(point_count).model_json_schema()


def subject_checks_output_tokens(point_count: int) -> int:
    """Finite allowance for six fields per source/draft target comparison."""
    _validate_point_count(point_count)
    return 128 + 512 * (point_count + 1)


def parse_subject_checks(payload: dict, *, source: str, draft: dict) -> str:
    """Bind target subjects and contiguous source quotes; never certify meaning."""
    targets = [draft["summary"], *draft["key_points"]]
    parsed = PydanticOutputParser(
        pydantic_object=subject_checks_model(len(targets) - 1)
    ).parse(json.dumps(payload, ensure_ascii=False))

    def line_breaks_to_space(text: str) -> str:
        return re.sub(r"\r\n|[\r\n\v\f\x85\u2028\u2029]", " ", text)

    original = line_breaks_to_space(source)
    feedback = []
    for index, target in enumerate(targets):
        check = getattr(parsed, f"target_{index}")
        if check.source_quote is not None and line_breaks_to_space(check.source_quote) not in original:
            raise ValueError("Source review quote does not belong to its bound source")
        if (check.source_subject is not None and
                (check.source_quote is None or
                 line_breaks_to_space(check.source_subject) not in line_breaks_to_space(check.source_quote))):
            raise ValueError("Source review subject is not bound to its quoted source clause")
        if check.draft_subject is not None and line_breaks_to_space(check.draft_subject) not in line_breaks_to_space(target):
            raise ValueError("Source review subject does not belong to its bound draft target")
        feedback.append(
            f"Target {index}:\nDraft assertion: {target}\nAssessment: {check.assessment}"
            f"\nScope relation (draft vs source): {check.scope_relation}"
            f"\nSource subject: {check.source_subject if check.source_subject is not None else 'null'}"
            f"\nDraft subject: {check.draft_subject if check.draft_subject is not None else 'null'}"
            f"\nOriginal evidence: {check.source_quote if check.source_quote is not None else 'null'}"
            f"\nFinding: {check.finding}"
        )
    return "\n\n".join(feedback)
