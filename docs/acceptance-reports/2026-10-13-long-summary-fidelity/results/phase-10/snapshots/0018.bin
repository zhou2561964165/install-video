"""Pure, bounded repair policy. Each summary owns its own attempt budget."""
from dataclasses import dataclass
from enum import Enum


class ErrorCategory(str, Enum):
    FORMAT = "format"
    SEMANTIC = "semantic"
    SOURCE = "source"
    CAPACITY = "capacity"
    PROVIDER = "provider"
    NETWORK = "network"
    CONFIG = "config"


@dataclass(frozen=True)
class RetryPolicy:
    format_retries: int = 1
    semantic_retries: int = 1
    max_extra_calls: int = 2

    def __post_init__(self):
        for value in (self.format_retries, self.semantic_retries, self.max_extra_calls):
            if type(value) is not int or not 0 <= value <= 2:
                raise ValueError("invalid_retry_policy")


@dataclass
class RetryBudget:
    policy: RetryPolicy
    format_used: int = 0
    semantic_used: int = 0

    @property
    def used(self) -> int:
        return self.format_used + self.semantic_used

    def allows(self, category: ErrorCategory) -> bool:
        if self.used >= self.policy.max_extra_calls:
            return False
        return ((category == ErrorCategory.FORMAT and self.format_used < self.policy.format_retries)
                or (category == ErrorCategory.SEMANTIC and self.semantic_used < self.policy.semantic_retries))

    def consume(self, category: ErrorCategory) -> bool:
        if not self.allows(category):
            return False
        if category == ErrorCategory.FORMAT:
            self.format_used += 1
            return True
        if category == ErrorCategory.SEMANTIC:
            self.semantic_used += 1
            return True
        return False


def classify_reason(reason: str, *, stage: str, scope: str) -> ErrorCategory:
    """Classify bounded codec reasons using the location where they arose.

    Unknown references in a normalized draft are unresolved suggestions, not
    manufactured evidence. An unknown source/evidence in the fact bank is
    terminal. Unknown failure codes fail closed rather than inviting a repair.
    """
    if scope == "source":
        return ErrorCategory.SOURCE
    if reason in {"missing_core_fact", "audit_not_supported", "unresolved_references",
                  "duplicate_point", "duplicate_summary", "summary_too_long"}:
        return ErrorCategory.SEMANTIC
    if stage == "audit" and reason in {"too_many_summary_items", "too_many_points", "text_too_long",
                                      "point_too_long"}:
        return ErrorCategory.SEMANTIC
    if reason in {"unknown_source", "invalid_sources", "duplicate_source_id", "invalid_source",
                  "invalid_fact_trace", "invalid_facts", "duplicate_fact_id", "invalid_evidence",
                  "unknown_evidence", "duplicate_evidence", "attribution_not_found", "unknown_fact",
                  "invalid_fact_bank"}:
        return ErrorCategory.SOURCE
    if reason == "invalid_limits":
        return ErrorCategory.CONFIG
    if scope == "normalization" or reason in {"invalid_json", "duplicate_json_field", "invalid_fields",
                                              "invalid_text", "invalid_count", "nontrailing_empty_slot",
                                              "duplicate_reference", "invalid_check_id"}:
        return ErrorCategory.FORMAT
    return ErrorCategory.SOURCE
