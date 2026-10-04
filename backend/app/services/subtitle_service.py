"""字幕轨道选择、获取与文本化；不直接依赖 yt-dlp。"""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import settings
from . import ytdlp_service

_FORMAT_PRIORITY = {"vtt": 0, "srt": 1, "json3": 2, "ttml": 3, "srv3": 4}
_LANGUAGE_PRIORITY = ("zh-hans", "zh-cn", "zh", "en", "en-us")
_TIMESTAMP_RE = re.compile(
    r"^\s*(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{1,3}\s*-->\s*(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{1,3}(?=\s|$)"
)
_TAG_RE = re.compile(r"<[^>]+>")


class SubtitleServiceError(RuntimeError):
    def __init__(self, error_type: str, message: str, *, available_languages: list[str] | None = None):
        super().__init__(message)
        self.error_type = error_type
        self.available_languages = available_languages or []


@dataclass(frozen=True)
class SubtitleDocument:
    title: str
    language: str
    is_auto: bool
    available_languages: list[str]
    text: str


def _dedupe_lines(lines: list[str]) -> str:
    result: list[str] = []
    for line in lines:
        cleaned = re.sub(r"\s+", " ", html.unescape(line)).strip()
        if cleaned and (not result or result[-1] != cleaned):
            result.append(cleaned)
    return "\n".join(result)


def _parse_timed_text(raw: str) -> str:
    lines: list[str] = []
    normalized = raw.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    for block in re.split(r"\n\s*\n", normalized):
        block_lines = block.strip().splitlines()
        if not block_lines or block_lines[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        timestamp = next((index for index, line in enumerate(block_lines) if _TIMESTAMP_RE.match(line)), None)
        if timestamp is None:
            continue
        # Cue IDs and headers precede the timestamp; only its payload is speech.
        lines.extend(_TAG_RE.sub("", line) for line in block_lines[timestamp + 1:])
    return _dedupe_lines(lines)


def _parse_json3(raw: str) -> str:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SubtitleServiceError("subtitle_invalid", "字幕 JSON 格式无效") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise SubtitleServiceError("subtitle_invalid", "字幕 JSON 结构无效")
    lines = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            raise SubtitleServiceError("subtitle_invalid", "字幕 JSON 结构无效")
        segments = event.get("segs") or []
        if not isinstance(segments, list) or any(
            not isinstance(seg, dict) or not isinstance(seg.get("utf8", ""), str) for seg in segments
        ):
            raise SubtitleServiceError("subtitle_invalid", "字幕 JSON 结构无效")
        text = "".join(seg.get("utf8", "") for seg in segments)
        lines.extend(text.splitlines())
    return _dedupe_lines(lines)


def _parse_ttml(raw: str) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise SubtitleServiceError("subtitle_invalid", "字幕 XML 格式无效") from exc
    lines = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "p":
            for child in node.iter():
                if child.tag.rsplit("}", 1)[-1] == "br":
                    child.text = " "
            lines.append("".join(node.itertext()))
    return _dedupe_lines(lines)


def parse_subtitle_text(raw: str, ext: str) -> str:
    normalized_ext = ext.lower().lstrip(".")
    if normalized_ext == "json3":
        text = _parse_json3(raw)
    elif normalized_ext in {"ttml", "srv3"}:
        text = _parse_ttml(raw)
    else:
        text = _parse_timed_text(raw)
    if not text:
        raise SubtitleServiceError("subtitle_invalid", "字幕内容为空或无法解析")
    return text


def _available_languages(tracks: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(track["language"] for track in tracks))


def _select_track(tracks: list[dict[str, Any]], language: str | None) -> dict[str, Any]:
    available = _available_languages(tracks)
    if not tracks:
        raise SubtitleServiceError("subtitle_unavailable", "该视频没有可用字幕")
    if language:
        target = language.casefold()
        exact = [track for track in tracks if track["language"].casefold() == target]
        prefix = [
            track for track in tracks
            if track["language"].casefold().split("-", 1)[0] == target.split("-", 1)[0]
        ]
        candidates = exact or prefix
        if not candidates:
            raise SubtitleServiceError(
                "subtitle_unavailable",
                f"没有 {language} 字幕",
                available_languages=available,
            )
        return sorted(candidates, key=lambda item: item["is_auto"])[0]

    def rank(track: dict[str, Any]) -> tuple[int, int]:
        lang = track["language"].casefold()
        try:
            language_rank = _LANGUAGE_PRIORITY.index(lang)
        except ValueError:
            language_rank = len(_LANGUAGE_PRIORITY)
        return int(track["is_auto"]), language_rank

    return sorted(tracks, key=rank)[0]


def _select_format(track: dict[str, Any]) -> dict[str, Any]:
    return sorted(
        track["formats"],
        key=lambda item: _FORMAT_PRIORITY.get(item["ext"].lower(), len(_FORMAT_PRIORITY)),
    )[0]


def fetch_subtitle_document(
    video_url: str,
    language: str | None = None,
    *,
    client: httpx.Client | None = None,
) -> SubtitleDocument:
    payload = ytdlp_service.extract_subtitle_tracks(video_url)
    tracks = payload["tracks"]
    selected = _select_track(tracks, language)
    selected_format = _select_format(selected)
    owns_client = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=float(settings.subtitle_timeout_seconds))
    try:
        with http.stream("GET", selected_format["url"], headers=selected_format["http_headers"]) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                if len(content) + len(chunk) > settings.subtitle_max_bytes:
                    raise SubtitleServiceError("subtitle_too_large", "字幕文件超过大小限制")
                content.extend(chunk)
            raw = content.decode(response.encoding or "utf-8", errors="replace")
    except httpx.HTTPError as exc:
        raise SubtitleServiceError("subtitle_fetch_failed", f"字幕获取失败：{exc}") from exc
    finally:
        if owns_client:
            http.close()

    return SubtitleDocument(
        title=payload["title"],
        language=selected["language"],
        is_auto=bool(selected["is_auto"]),
        available_languages=_available_languages(tracks),
        text=parse_subtitle_text(raw, selected_format["ext"]),
    )
