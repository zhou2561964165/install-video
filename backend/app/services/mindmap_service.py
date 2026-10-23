"""Validate a bounded plain text topic tree, independent of provider HTTP details."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..config import settings
from .llm_service import LLMServiceError, generate_mindmap_text


class MindMapNode(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    children: list[MindMapNode] = Field(max_length=8)

    @field_validator("label")
    @classmethod
    def plain_text(cls, label: str) -> str:
        if (not label.strip() or any(unicodedata.category(char).startswith("C") for char in label)
                or any(char in label for char in "<>`")
                or re.search(r"!?\[[^\]]*\]\s*\(", label)):
            raise ValueError("node labels must be plain text")
        return label


class _MindMapPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    root: MindMapNode


@dataclass(frozen=True)
class MindMapResult:
    root: MindMapNode
    provider: str
    model: str


def validate_mindmap_configuration() -> None:
    """Reject unavailable/invalid profiles before subtitle or model I/O."""
    if not settings.llm_base_url.strip() or not settings.llm_model.strip():
        raise LLMServiceError("llm_unconfigured", "AI 功能尚未启用，请联系管理员")
    for name, maximum in (("mindmap_max_source_chars", 60000),
                          ("mindmap_max_output_tokens", 4096),
                          ("mindmap_max_nodes", 64), ("mindmap_max_depth", 4)):
        value = getattr(settings, name, None)
        if type(value) is not int or not 1 <= value <= maximum:
            raise LLMServiceError("llm_unconfigured", "思维导图资源配置无效")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate JSON field")
        result[name] = value
    return result


def _invalid_constant(value: str):
    raise ValueError("non-JSON constant")


def generate_mindmap(
    text: str, *, title: str, output_language: str, client: httpx.Client | None = None,
) -> MindMapResult:
    validate_mindmap_configuration()
    transport_options = {"client": client} if client is not None else {}
    response = generate_mindmap_text(text, title=title, output_language=output_language, **transport_options)
    try:
        if len(response.text) > 65536:
            raise ValueError("oversized JSON")
        payload = json.loads(response.text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        # Check global bounds before recursive Pydantic validation, including deeply nested input.
        pending = [(payload["root"], 1)]
        count = 0
        while pending:
            node, depth = pending.pop()
            count += 1
            if count > settings.mindmap_max_nodes or depth > settings.mindmap_max_depth:
                raise ValueError("tree budget exceeded")
            if not isinstance(node, dict) or not isinstance(node.get("children"), list):
                raise ValueError("invalid node")
            if len(node["children"]) > 8:
                raise ValueError("child budget exceeded")
            pending.extend((child, depth + 1) for child in node["children"])
        tree = _MindMapPayload.model_validate(payload)
    except (KeyError, TypeError, ValueError, RecursionError, ValidationError) as exc:
        raise LLMServiceError("llm_invalid_response", "模型返回的思维导图格式无效或超出限制") from exc
    return MindMapResult(tree.root, response.provider, response.model)
