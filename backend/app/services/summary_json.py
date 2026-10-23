"""Decode summary JSON, repairing only missing terminal closing punctuation.

Pydantic's installed JSON parser supplies the partial candidate. Independent
string and punctuation checks prove that no field, value, or point was lost or
added; subsequent summary schemas still own types and business limits.
Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only through ytdlp_service; scene remains read-only. No runtime settings/HTTP.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic_core import from_json

_STRING = re.compile(r'"(?:\\.|[^"\\])*"')
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _tokens(text: str) -> tuple[list[str], str]:
    """Validate complete JSON strings; retain every remaining punctuation mark."""
    values, pieces, end = [], [], 0
    for match in _STRING.finditer(text):
        pieces.extend((text[end:match.start()], "S"))
        values.append(json.loads(match.group()))
        end = match.end()
    pieces.append(text[end:])
    skeleton = re.sub(r"\s+", "", "".join(pieces))
    if re.search(r"[^S{}\[\]:,]", skeleton):
        # Unclosed strings, bare literals, and malformed escapes cannot be
        # swallowed by allow_partial, even when the last valid value survived.
        raise ValueError("Invalid summary JSON")
    return values, skeleton


def _repair(text: str, error: json.JSONDecodeError) -> Any:
    if error.msg != "Expecting ',' delimiter" or error.pos < len(text) - 1:
        raise ValueError("Invalid summary JSON")
    misplaced_object_close = error.pos == len(text) - 1 and text.endswith("}")
    prefix = text[:-1].rstrip() if misplaced_object_close else text
    if not prefix.endswith(('"', "]")):
        # A dangling comma, property colon, or empty open array still promises
        # a value that the parser cannot recover without inventing a default.
        raise ValueError("Invalid summary JSON")
    tokens, skeleton = _tokens(prefix)
    try:
        candidate = from_json(prefix, allow_partial=True)
    except ValueError:
        raise ValueError("Invalid summary JSON") from None
    if (not isinstance(candidate, dict)
            or not {"summary", "key_points"} <= set(candidate) <= {"summary", "key_points", "title", "conclusion"}
            or not isinstance(candidate["summary"], str)
            or not isinstance(candidate["key_points"], list)
            or any(not isinstance(point, str) for point in candidate["key_points"])
            or any(not isinstance(candidate[key], str) for key in ("title", "conclusion") if key in candidate)):
        raise ValueError("Invalid summary JSON")
    restored_tokens, restored_skeleton = _tokens(json.dumps(candidate, ensure_ascii=True))
    suffix = restored_skeleton[len(skeleton):]
    if (tokens != restored_tokens or not restored_skeleton.startswith(skeleton)
            or not suffix or any(mark not in "]}" for mark in suffix)
            or misplaced_object_close and not suffix.startswith("]")):
        raise ValueError("Invalid summary JSON")
    return candidate


def decode_summary_json(content: str, *, allow_fences: bool = True) -> Any:
    """Preserve standard JSON behavior; only incomplete terminal closings repair.

    Paired JSON fences are optional when explicitly allowed. Valid JSON of any
    shape, including legacy extra fields, passes through json.loads unchanged.
    Rejected repairs expose a constant error message and never provider text.
    """
    text = content.strip()
    if text.startswith("```") or text.endswith("```"):
        fence = _FENCE.fullmatch(text) if allow_fences else None
        if fence is None:
            raise ValueError("Invalid summary JSON")
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        try:
            return _repair(text, error)
        except (json.JSONDecodeError, ValueError):
            raise ValueError("Invalid summary JSON") from None
