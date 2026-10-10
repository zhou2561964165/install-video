"""Lossless audit protocol adaptation, without source or semantic judgments.

Read the complete object first, validate the source bank in the caller, then
adapt the protocol and run final normalization/reference/original audit checks.
Nested flags are the model's assertions. Mapping them never makes them true.
"""

from copy import deepcopy
from dataclasses import dataclass
import json
import re
from typing import Any, Literal

from .summary_facts import FactLimits, FactValidationError


_FLAGS = ("supported", "qualifiers_preserved", "attribution_preserved", "scope_preserved")
_REASONS = frozenset({
    "invalid_json", "duplicate_json_field", "invalid_payload", "invalid_fields",
    "invalid_limits", "invalid_count", "too_many_points", "nontrailing_empty_slot",
})


class AuditContractError(FactValidationError):
    """Only bounded reason codes; never raw model text or source contents."""

    def __init__(self, reason: str):
        super().__init__(reason if reason in _REASONS else "invalid_fields")


@dataclass(frozen=True)
class AuditEnvelope:
    """Frozen attributes containing fresh, caller-owned JSON payload copies.

    The contained lists/dicts intentionally retain the codecs' JSON shapes;
    they are detached from input, rather than claimed to be deeply immutable.
    """

    protocol: Literal["legacy", "compact"]
    additional_facts: list[dict[str, Any]]
    composition: dict[str, Any]
    checks: list[dict[str, str | bool]]


def read_audit_contract(payload: dict | str) -> dict[str, Any]:
    """Read an entire JSON object without discarding or interpreting fields.

    Unknown fields and malformed source records remain visible so the caller
    can validate additional_facts before considering output protocol errors.
    """
    if isinstance(payload, str):
        text = payload.strip()
        fence = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", text, re.DOTALL | re.IGNORECASE)
        if fence is not None:
            text = fence.group(1)
        try:
            payload = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        except AuditContractError:
            raise
        except (ValueError, RecursionError):
            raise AuditContractError("invalid_json") from None
    if not isinstance(payload, dict):
        raise AuditContractError("invalid_payload")
    try:
        return deepcopy(payload)
    except RecursionError:
        raise AuditContractError("invalid_payload") from None


def parse_audit_contract(payload: dict | str, limits: FactLimits) -> AuditEnvelope:
    """Adapt exact legacy/compact shapes while preserving model assertions.

    No source lookup, final text-length check, reference selection, or semantic
    approval occurs here. Slot overflow/holes fail; text is never shortened.
    """
    if not isinstance(limits, FactLimits):
        raise AuditContractError("invalid_limits")
    obj = read_audit_contract(payload)
    keys = set(obj)
    if keys not in ({"additional_facts", "output"}, {"additional_facts", "output", "checks"}):
        raise AuditContractError("invalid_fields")
    additions, output = obj["additional_facts"], obj["output"]
    if not isinstance(additions, list) or any(not isinstance(item, dict) for item in additions):
        raise AuditContractError("invalid_fields")
    if not isinstance(output, dict):
        raise AuditContractError("invalid_fields")
    if "checks" in obj:
        if _contains_assertions(output):
            raise AuditContractError("invalid_fields")
        checks = obj["checks"]
        if not isinstance(checks, list) or not checks:
            raise AuditContractError("invalid_count")
        for check in checks:
            if (not isinstance(check, dict) or set(check) != {*_FLAGS, "item_id"}
                    or not isinstance(check["item_id"], str)):
                raise AuditContractError("invalid_fields")
            _assertions({key: check[key] for key in _FLAGS})
        return AuditEnvelope("legacy", additions, output, checks)

    slots = {f"point_{index}" for index in range(1, limits.max_items + 1)}
    for key in output:
        if isinstance(key, str) and re.fullmatch(r"point_[1-9][0-9]*", key):
            # Compare decimal strings, avoiding arbitrary-length int conversion.
            suffix, ceiling = key[6:], str(limits.max_items)
            if len(suffix) > len(ceiling) or (len(suffix) == len(ceiling) and suffix > ceiling):
                raise AuditContractError("too_many_points")
    if "summary" not in output or not set(output) <= {"summary", *slots}:
        raise AuditContractError("invalid_fields")
    summary, summary_flags = _compact_item(output["summary"], point=False)
    composition: dict[str, Any] = {"summary": [summary]}
    checks = [{"item_id": "S1", **summary_flags}]
    unused, count = False, 0
    for index in range(1, limits.max_items + 1):
        slot = f"point_{index}"
        record = output.get(slot)
        if record is None:
            unused = True
            if slot in output:
                composition[slot] = None
            continue
        if unused:
            raise AuditContractError("nontrailing_empty_slot")
        point, flags = _compact_item(record, point=True)
        composition[slot] = point
        checks.append({"item_id": f"P{index}", **flags})
        count += 1
    if not count:
        raise AuditContractError("invalid_count")
    return AuditEnvelope("compact", additions, composition, checks)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditContractError("duplicate_json_field")
        result[key] = value
    return result


def _reject_constant(_value):
    raise AuditContractError("invalid_json")


def _assertions(value) -> dict[str, bool]:
    if (not isinstance(value, dict) or set(value) != set(_FLAGS)
            or any(type(value[flag]) is not bool for flag in _FLAGS)):
        raise AuditContractError("invalid_fields")
    return {flag: value[flag] for flag in _FLAGS}


def _compact_item(record, *, point: bool) -> tuple[dict[str, Any], dict[str, bool]]:
    required = {"text", "assertions", *({"topic"} if point else set())}
    if (not isinstance(record, dict) or not required <= set(record)
            or not set(record) <= required | {"fact_ids"}
            or not isinstance(record["text"], str)
            or (point and not isinstance(record["topic"], str))):
        raise AuditContractError("invalid_fields")
    flags = _assertions(record["assertions"])
    return {key: value for key, value in record.items() if key != "assertions"}, flags


def _contains_assertions(value) -> bool:
    if isinstance(value, dict):
        return "assertions" in value or any(_contains_assertions(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_assertions(item) for item in value)
    return False
