"""Pydantic owns summary field types/schema; no HTTP, settings or semantic claims.

Normalization and finite business budgets stay in the LLM service. Field order
expresses a points-first generation request, not a provider execution guarantee.
"""
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr, create_model


class _CoreSummaryPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    key_points: list[StrictStr]
    summary: StrictStr


class SummaryPayload(_CoreSummaryPayload):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)

    title: StrictStr = ""
    conclusion: StrictStr = ""


class _StrictSummaryPayload(SummaryPayload):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


def decode_payload(payload: Any, *, strict: bool = False) -> SummaryPayload:
    model = _StrictSummaryPayload if strict else SummaryPayload
    return model.model_validate(payload)


def output_schema(max_points: int, point_char_limit: int | None, *, include_editorial: bool = False) -> dict[str, Any]:
    """Generate the existing strict JSON schema using the installed library."""
    constraints = {"min_length": 1}
    if point_char_limit is not None:
        constraints["max_length"] = point_char_limit
    point_type = Annotated[StrictStr, Field(**constraints)]
    schema_model = create_model(
        "VideoSummaryOutput",
        __base__=_StrictSummaryPayload if include_editorial else _CoreSummaryPayload,
        key_points=(Annotated[list[point_type], Field(min_length=1, max_length=max_points)], ...),
        summary=(Annotated[StrictStr, Field(min_length=1)], ...),
    )
    return schema_model.model_json_schema()


class PointsPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    key_points: list[StrictStr]


class OverviewPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    summary: Annotated[StrictStr, Field(min_length=1)]


def stage_model(role: str, max_points: int, point_char_limit: int | None = None) -> type[BaseModel]:
    if role == "overview":
        return OverviewPayload
    if role != "points":
        raise ValueError("invalid_summary_role")
    constraints = {"min_length": 1}
    if point_char_limit is not None:
        constraints["max_length"] = point_char_limit
    point_type = Annotated[StrictStr, Field(**constraints)]
    return create_model(
        "VideoSummaryPoints", __base__=PointsPayload,
        key_points=(Annotated[list[point_type], Field(min_length=1, max_length=max_points)], ...),
    )


def stage_schema(role: str, max_points: int, point_char_limit: int | None = None) -> dict[str, Any]:
    return stage_model(role, max_points, point_char_limit).model_json_schema()
