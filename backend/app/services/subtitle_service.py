"""字幕轨道选择、获取与文本化；不直接依赖 yt-dlp。"""

from __future__ import annotations

import html
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..config import settings
from . import network_retry
from . import ytdlp_service
from .bilibili_session import SessionError, cookie_jar_for_url, is_bilibili_url
from .bilibili_subtitle_source import apply_session_cookies
from .outbound_httpx import ControlledHttpError
from .outbound_policy import OutboundError, OutboundPurpose, OutboundUnavailableError
from .source_network import SourceNetworkContext, current_source_network, source_headers, source_network_scope
from .subtitle_timing import SubtitleSegment, TimingError, parse_segments

_FORMAT_PRIORITY = {"vtt": 0, "srt": 1, "json3": 2, "ttml": 3, "srv3": 4, "bilibili_json": 5}
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
    segments: list[SubtitleSegment] = field(default_factory=list)


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


def _is_finite_timestamp(value: Any) -> bool:
    if type(value) not in {int, float}:
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def parse_subtitle_text(raw: str, ext: str) -> str:
    normalized_ext = ext.lower().lstrip(".")
    if normalized_ext == "bilibili_json":
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SubtitleServiceError("subtitle_invalid", "字幕 JSON 格式无效") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("body"), list):
            raise SubtitleServiceError("subtitle_invalid", "字幕 JSON 结构无效")
        lines = []
        for cue in payload["body"]:
            if (not isinstance(cue, dict) or not isinstance(cue.get("content"), str)
                    or any(not _is_finite_timestamp(cue.get(k)) for k in ("from", "to"))
                    or not 0 <= cue["from"] <= cue["to"]):
                raise SubtitleServiceError("subtitle_invalid", "字幕 JSON 结构无效")
            lines.extend(cue["content"].splitlines())
        text = _dedupe_lines(lines)
    elif normalized_ext == "json3":
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
    network: SourceNetworkContext | None = None,
) -> SubtitleDocument:
    with source_network_scope(network) as active:
        if active is not None and client is not None:
            raise OutboundUnavailableError() from None
        return _fetch_subtitle_document(video_url, language, client=client)


def _fetch_subtitle_document(video_url: str, language: str | None, *, client) -> SubtitleDocument:
    try:
        payload = ytdlp_service.extract_subtitle_tracks(video_url)
    except SessionError as exc:
        raise SubtitleServiceError("verification_required", ytdlp_service.public_error_message(exc)) from None
    try:
        return _document_from_tracks(payload, language, video_url=video_url, client=client)
    except (OutboundError, ControlledHttpError):
        raise
    except SubtitleServiceError as native_error:
        if native_error.error_type == "verification_required" or payload.get("_source") != "public":
            raise
        if current_source_network() is None:
            return _legacy_document_fallback(video_url, language, client, native_error)
    # The generic yt-dlp handler is not guarded yet. Fail after leaving the
    # exception suite so source/parser exception context is not retained.
    raise OutboundUnavailableError() from None


def _legacy_document_fallback(video_url, language, client, native_error):
    # Native captions can expire or lack the requested language. Try the narrow
    # generic entrypoint once, retaining the native error if it cannot help.
    try:
        generic = ytdlp_service.extract_subtitle_tracks(video_url, use_public_sources=False)
        return _document_from_tracks(generic, language, video_url=video_url, client=client)
    except (OutboundError, ControlledHttpError):
        raise
    except SessionError as exc:
        raise SubtitleServiceError("verification_required", ytdlp_service.public_error_message(exc)) from None
    except SubtitleServiceError as exc:
        if exc.error_type == "verification_required":
            raise
        raise native_error from None
    except Exception:
        raise native_error from None


def _document_from_tracks(
    payload: dict,
    language: str | None,
    *,
    video_url: str,
    client: httpx.Client | None,
) -> SubtitleDocument:
    tracks = payload["tracks"]
    selected = _select_track(tracks, language)
    selected_format = _select_format(selected)
    if "data" in selected_format:
        raw = selected_format["data"]
        if not isinstance(raw, str):
            raise SubtitleServiceError("subtitle_invalid", "字幕内容格式无效")
        if len(raw.encode("utf-8")) > settings.subtitle_max_bytes:
            raise SubtitleServiceError("subtitle_too_large", "字幕文件超过大小限制")
        return _build_document(payload, selected, tracks, raw, selected_format["ext"])
    network = current_source_network()
    if network is not None:
        headers = source_headers(selected_format['http_headers'])
        bili_source = is_bilibili_url(video_url)
        if bili_source:
            headers = {key: value for key, value in headers.items() if key.lower() != 'referer'}
            headers['Referer'] = f'https://www.bilibili.com{urlsplit(video_url).path}'
        # A CDN never needs to read the session file. Only a concrete official
        # caption URL may request a fresh, strictly scoped jar.
        cookies = cookie_jar_for_url(selected_format['url']) if bili_source and is_bilibili_url(selected_format['url']) else None
        with network.stream(selected_format['url'], purpose=OutboundPurpose.SUBTITLE,
                headers=headers, cookies=cookies,
                follow_redirects=not (bili_source or selected_format['ext'] == 'bilibili_json'),
                max_bytes=settings.subtitle_max_bytes, phase_seconds=settings.subtitle_timeout_seconds,
                io_timeout=settings.subtitle_timeout_seconds) as response:
            response.raise_for_status()
            content = response.read()
            # Preserve HTTPX's declared charset selection without exposing its
            # raw transport/request or using an HTTPX client for source I/O.
            encoding = httpx.Response(200, headers=response.headers, content=content).encoding
        return _build_document(payload, selected, tracks,
            content.decode(encoding or 'utf-8', errors='replace'), selected_format['ext'])
    owns_client = client is None
    bili_source = is_bilibili_url(video_url)
    try:
        cookies = cookie_jar_for_url(video_url)
    except SessionError as exc:
        raise SubtitleServiceError("verification_required", ytdlp_service.public_error_message(exc)) from None
    client_options = {"cookies": cookies,
                      "event_hooks": {"request": [lambda request: apply_session_cookies(request, cookies)]}} if bili_source else {}
    http = client or httpx.Client(follow_redirects=True, timeout=float(settings.subtitle_timeout_seconds), **client_options)
    # Extractor headers may contain credentials scoped to the original page.
    # Caption URLs can point to unrelated CDNs; only the domain-aware jar may
    # supply cookies, and no unscoped Authorization header crosses this boundary.
    headers = dict(selected_format["http_headers"])
    if bili_source:
        headers = {key: value for key, value in headers.items()
                   if key.lower() not in {"cookie", "cookie2", "authorization", "proxy-authorization"}}
        # User-controlled query parameters are unnecessary for anti-hotlinking.
        headers["Referer"] = f"https://www.bilibili.com{urlsplit(video_url).path}"

    @contextmanager
    def caption_response():
        if bili_source and not owns_client:
            # Work on a concrete request rather than changing shared client
            # hooks/cookies. This also removes any caller-level credentials.
            request = http.build_request("GET", selected_format["url"], headers=headers)
            apply_session_cookies(request, cookies)
            response = http.send(request, stream=True, follow_redirects=False, auth=None)
            try:
                yield response
            finally:
                response.close()
        else:
            redirect_options = {"follow_redirects": False} if bili_source or selected_format["ext"] == "bilibili_json" else {}
            with http.stream("GET", selected_format["url"], headers=headers, **redirect_options) as response:
                yield response
    try:
        def get_caption() -> tuple[bytes, str | None]:
            with caption_response() as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    if len(content) + len(chunk) > settings.subtitle_max_bytes:
                        raise SubtitleServiceError("subtitle_too_large", "字幕文件超过大小限制")
                    content.extend(chunk)
                return bytes(content), response.encoding

        content, encoding = network_retry.retry_get(
            get_caption,
            max_retries=settings.network_retries,
            backoff_seconds=settings.network_retry_backoff_seconds,
        )
        raw = content.decode(encoding or "utf-8", errors="replace")
    except httpx.HTTPError as exc:
        # Provider URLs can contain signed access keys. Never return HTTPX's
        # raw exception text through the API; retain only a safe status hint.
        message = (
            f"字幕获取失败（HTTP {exc.response.status_code}）"
            if isinstance(exc, httpx.HTTPStatusError)
            else "字幕获取失败：网络连接异常或请求超时，请稍后重试"
        )
        raise SubtitleServiceError("subtitle_fetch_failed", message) from exc
    finally:
        if owns_client:
            http.close()

    return _build_document(payload, selected, tracks, raw, selected_format["ext"])


def _build_document(payload: dict, selected: dict, tracks: list[dict], raw: str, ext: str) -> SubtitleDocument:
    text = parse_subtitle_text(raw, ext)
    try:
        segments = parse_segments(raw, ext, max_cues=settings.subtitle_max_cues)
    except TimingError as exc:
        raise SubtitleServiceError(exc.error_type, str(exc)) from exc
    return SubtitleDocument(
        title=payload["title"],
        language=selected["language"],
        is_auto=bool(selected["is_auto"]),
        available_languages=_available_languages(tracks),
        text=text,
        segments=segments,
    )
