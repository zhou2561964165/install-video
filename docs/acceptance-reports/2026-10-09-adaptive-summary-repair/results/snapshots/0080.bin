"""Pure, lossless normalization of model-produced summary structures."""

from dataclasses import dataclass
import json
import re

from .summary_facts import FactLimits


_REASON_CODES = frozenset({
    "invalid_json", "duplicate_json_field", "invalid_payload", "unknown_fields",
    "missing_fields", "invalid_text", "invalid_hint_ids", "invalid_count",
    "summary_too_long", "point_too_long", "too_many_summary_items",
    "too_many_points", "slot_hole", "invalid_theme_plan", "theme_too_long",
    "topic_too_long",
    "too_many_themes", "inconsistent_points", "invalid_limits",
})


class NormalizationError(ValueError):
    """A bounded format error that never stores model or source text."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code if reason_code in _REASON_CODES else "invalid_payload"
        super().__init__(self.reason_code)


@dataclass(frozen=True)
class DraftItem:
    id: str
    text: str
    topic: str = ""
    hint_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThemeHint:
    point_index: int
    topic: str = ""
    principle: str = ""
    conditions: tuple[str, ...] = ()
    consequences: tuple[str, ...] = ()
    hint_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.point_index) is not int or self.point_index <= 0:
            raise ValueError("point_index must be a positive one-based index")


@dataclass(frozen=True)
class NormalizedDraft:
    summary: tuple[DraftItem, ...]
    key_points: tuple[DraftItem, ...]
    theme_hints: tuple[ThemeHint, ...] = ()
    transformations: tuple[str, ...] = ()


def normalize_extraction(payload: dict | str) -> tuple[dict, tuple[str, ...]]:
    """Normalize only the extraction JSON envelope, leaving facts untouched.

    Some providers echo the configured response_format as a top-level marker.
    Only its exact, content-free json_object value is recognized. All other
    fields and marker values reach the existing strict provenance codec intact.
    """
    transformations = []
    obj = _decode_object(payload, transformations)
    if obj.get("type") == "json_object":
        obj = {key: value for key, value in obj.items() if key != "type"}
        transformations.append("json_object_transport_marker_removed")
    return obj, tuple(transformations)


def normalize_composition(
    payload: dict | str, limits: FactLimits, *, final: bool = False
) -> NormalizedDraft:
    """Normalize summary and array point forms without changing their text."""
    if not isinstance(limits, FactLimits) or type(final) is not bool:
        raise NormalizationError("invalid_limits")
    transformations = []
    obj = _decode_object(payload, transformations)
    point_slots = {f"point_{index}" for index in range(1, limits.max_items + 1)}
    _check_keys(obj, {"summary", "key_points", "theme_plan", *point_slots}, required={"summary"})
    summary_limit = limits.max_summary_chars if final else 2 * limits.max_summary_chars
    summary_count = limits.max_items if final else limits.max_items * 2
    point_limit = limits.max_point_chars if final else max(limits.max_claim_chars, limits.max_point_chars)
    summary_records = _summary_records(obj["summary"], summary_count)
    summaries = tuple(
        DraftItem(f"S{index}", _text(record[0], summary_limit, "summary_too_long"), hint_ids=record[1])
        for index, record in enumerate(summary_records, 1)
    )
    if sum(len(item.text) for item in summaries) + max(0, len(summaries) - 1) > summary_limit:
        raise NormalizationError("summary_too_long")
    if isinstance(obj["summary"], str):
        transformations.append("summary_paragraph_wrapped")
    point_forms = []
    if "key_points" in obj:
        point_records = _point_records(obj["key_points"], limits.max_items)
        point_forms.append(_make_points(point_records, point_limit, limits.max_topic_chars))
    slots_present = any(key.startswith("point_") for key in obj)
    trailing_null = False
    if slots_present:
        point_slots_raw, trailing_null = _slot_records(obj, "point", limits.max_items, "slot_hole")
        point_records = _point_records(point_slots_raw, limits.max_items)
        point_forms.append(_make_points(point_records, point_limit, limits.max_topic_chars))
        transformations.append("numbered_points_collected")
    if len(point_forms) == 2:
        if point_forms[0] != point_forms[1]:
            raise NormalizationError("inconsistent_points")
        points = point_forms[0]
        transformations.append("duplicate_point_representations_collapsed")
    elif point_forms:
        points = point_forms[0]
    else:
        points = ()
    if _has_string_hint(obj):
        transformations.append("single_hint_id_wrapped")
    themes, theme_null_tail, theme_transformations = _theme_hints(
        obj.get("theme_plan", _MISSING), limits
    )
    transformations.extend(theme_transformations)
    if "theme_plan" in obj:
        transformations.append("theme_plan_mapped_to_hints")
    if trailing_null or theme_null_tail:
        transformations.append("trailing_null_slots_removed")
    return NormalizedDraft(
        summary=summaries,
        key_points=points,
        theme_hints=themes,
        transformations=tuple(transformations),
    )


def _decode_object(payload, transformations):
    if isinstance(payload, str):
        candidate = payload.strip()
        fence = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", candidate, re.DOTALL)
        if fence is not None:
            payload = fence.group(1)
            transformations.append("outer_json_fence_removed")
        try:
            payload = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        except NormalizationError:
            raise
        except (ValueError, TypeError, RecursionError):
            raise NormalizationError("invalid_json") from None
    if not isinstance(payload, dict):
        raise NormalizationError("invalid_payload")
    return payload


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise NormalizationError("duplicate_json_field")
        result[key] = value
    return result


def _reject_constant(_value):
    raise NormalizationError("invalid_json")


def _check_keys(value, allowed, *, required=frozenset()):
    if not required <= set(value):
        raise NormalizationError("missing_fields")
    if not set(value) <= allowed:
        raise NormalizationError("unknown_fields")


def _text(value, maximum, length_error="invalid_text"):
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError("invalid_text")
    if len(value) > maximum:
        raise NormalizationError(length_error)
    return value


def _hint_ids(record):
    if "fact_ids" not in record:
        return (), False
    value = record["fact_ids"]
    if isinstance(value, str):
        return (value,), True
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise NormalizationError("invalid_hint_ids")
    return tuple(value), False


def _summary_records(value, maximum):
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        raise NormalizationError("invalid_payload")
    if not values:
        raise NormalizationError("invalid_count")
    if len(values) > maximum:
        raise NormalizationError("too_many_summary_items")
    result = []
    for item in values:
        if isinstance(item, str):
            result.append((item, ()))
            continue
        if not isinstance(item, dict):
            raise NormalizationError("invalid_text")
        _check_keys(item, {"text", "fact_ids"}, required={"text"})
        hints, _ = _hint_ids(item)
        result.append((item["text"], hints))
    return result


def _point_records(value, maximum):
    if not isinstance(value, list):
        raise NormalizationError("invalid_payload")
    if len(value) > maximum:
        raise NormalizationError("too_many_points")
    result = []
    for item in value:
        if isinstance(item, str):
            result.append((item, "", ()))
            continue
        if not isinstance(item, dict):
            raise NormalizationError("invalid_text")
        _check_keys(item, {"topic", "text", "fact_ids"}, required={"text"})
        hints, _ = _hint_ids(item)
        result.append((item["text"], item.get("topic", ""), hints))
    return result


def _make_points(records, text_limit, topic_limit):
    return tuple(
        DraftItem(f"P{index}", _text(text, text_limit, "point_too_long"),
                  _optional_text(topic, topic_limit, "topic_too_long"), hint_ids)
        for index, (text, topic, hint_ids) in enumerate(records, 1)
    )


_MISSING = object()


def _slot_records(container, prefix, maximum, hole_reason):
    if f"{prefix}_1" not in container:
        raise NormalizationError(hole_reason)
    values = []
    has_null_tail = False
    unused = False
    for index in range(1, maximum + 1):
        name = f"{prefix}_{index}"
        value = container.get(name)
        if value is None:
            if name in container:
                has_null_tail = True
            unused = True
            continue
        if unused:
            raise NormalizationError(hole_reason)
        values.append(value)
    return values, has_null_tail


def _theme_hints(value, limits):
    if value is _MISSING:
        return (), False, ()
    if not isinstance(value, dict):
        raise NormalizationError("invalid_theme_plan")
    allowed = {f"theme_{index}" for index in range(1, limits.max_items + 1)}
    _check_keys(value, allowed, required={"theme_1"})
    records, has_null_tail = _slot_records(value, "theme", limits.max_items, "slot_hole")
    themes = []
    transformations = []
    fields = {"topic", "principle", "conditions", "consequences", "fact_ids"}
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise NormalizationError("invalid_theme_plan")
        _check_keys(record, fields, required=fields)
        topic = _text(record["topic"], limits.max_topic_chars, "theme_too_long")
        principle = _text(record["principle"], limits.max_claim_chars, "theme_too_long")
        conditions, condition_transformation = _theme_text_list(record["conditions"], limits)
        consequences, consequence_transformation = _theme_text_list(record["consequences"], limits)
        for transformation in (condition_transformation, consequence_transformation):
            if transformation is not None and transformation not in transformations:
                transformations.append(transformation)
        hint_ids, _ = _hint_ids(record)
        themes.append(ThemeHint(index, topic, principle, conditions, consequences, hint_ids))
    return tuple(themes), has_null_tail, tuple(transformations)


def _optional_text(value, maximum, length_reason):
    if not isinstance(value, str):
        raise NormalizationError("invalid_text")
    if len(value) > maximum:
        raise NormalizationError(length_reason)
    return value


def _theme_text_list(value, limits):
    transformation = None
    if isinstance(value, str):
        if value == "":
            return (), "theme_scalar_empty_text_omitted"
        values = [value]
        transformation = "theme_scalar_text_wrapped"
    elif isinstance(value, list):
        values = value
    else:
        raise NormalizationError("invalid_theme_plan")
    if len(values) > limits.max_items:
        raise NormalizationError("too_many_themes")
    normalized = tuple(_text(item, limits.max_point_chars, "theme_too_long") for item in values)
    return normalized, transformation


def _has_string_hint(value):
    def has_string_hint(records):
        return isinstance(records, list) and any(
            isinstance(record, dict) and isinstance(record.get("fact_ids"), str)
            for record in records
        )

    if has_string_hint(value.get("summary")) or has_string_hint(value.get("key_points")):
        return True
    if any(
        key.startswith("point_") and isinstance(record, dict)
        and isinstance(record.get("fact_ids"), str)
        for key, record in value.items()
    ):
        return True
    themes = value.get("theme_plan")
    return isinstance(themes, dict) and any(
        isinstance(record, dict) and isinstance(record.get("fact_ids"), str)
        for record in themes.values()
    )
