"""Bounded subtitle timelines and plain SRT/VTT serialization via pysubs2."""

from __future__ import annotations

import html
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4

import pysubs2
from pysubs2.formats.subrip import MAX_REPRESENTABLE_TIME


@dataclass(frozen=True)
class SubtitleSegment:
    start: float
    end: float
    text: str


class TimingError(ValueError):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type


def _check_count(count: int, max_cues: int) -> None:
    if count > max_cues:
        raise TimingError("subtitle_too_large", "字幕时间轴超过段数限制")


def _plain(text: str) -> str:
    """Normalize cue whitespace without interpreting already plain text."""
    return re.sub(r"\s+", " ", text).strip()


def _source_plain(text: str) -> str:
    # Only source markup is stripped. Encoded literal angles must be decoded
    # afterwards, so `vector&lt;int&gt;` remains `vector<int>`.
    return _plain(html.unescape(re.sub(r"<[^>]*>", "", text)))


def _number(value) -> float:
    if type(value) not in (int, float):
        raise TimingError("subtitle_invalid", "字幕时间格式无效")
    try:
        valid = math.isfinite(value) and value >= 0
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise TimingError("subtitle_invalid", "字幕时间必须为有限非负数")
    return value


def _validated(segments: Iterable[SubtitleSegment], max_cues: int) -> list[SubtitleSegment]:
    result = []
    previous = 0.0
    for count, cue in enumerate(segments, 1):
        _check_count(count, max_cues)
        start, end = _number(cue.start), _number(cue.end)
        if end < start or start < previous:
            raise TimingError("subtitle_invalid", "字幕时间轴顺序无效")
        previous = start
        text = _plain(cue.text)
        if text:
            result.append(SubtitleSegment(start, end, text))
    return result


def _library_segments(raw: str, ext: str, max_cues: int) -> list[SubtitleSegment]:
    # pysubs2 uses SSA escape sequences for physical newlines. Protect source
    # backslashes before parsing so literal code '\n' is distinguishable.
    marker = uuid4().hex
    while marker in raw:
        marker = uuid4().hex
    raw = raw.replace("\\", marker)
    if ext == "ttml":
        root = ET.fromstring(raw)
        nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "p"]
        _check_count(len(nodes), max_cues)
        if any("begin" not in node.attrib or not any(k in node.attrib for k in ("end", "dur", "duration")) for node in nodes):
            return []
        # pysubs2 1.9 calls the TTML duration attribute "duration". Normalize
        # the standard spelling at this compatibility boundary, without parsing time.
        for node in root.iter():
            if "dur" in node.attrib:
                node.set("duration", node.attrib["dur"])
        raw = ET.tostring(root, encoding="unicode")
        events = pysubs2.SSAFile.from_string(raw, format_=ext)
        if len(events) != len(nodes):
            return []  # unsupported TTML layout; never return a partial timeline
    else:
        # Strip VTT metadata and cue identifiers before pysubs2's shared SRT
        # reader, which otherwise includes a nonnumeric next cue ID in speech.
        blocks = []
        normalized = raw.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        for block in re.split(r"\n\s*\n", normalized):
            lines = block.strip().splitlines()
            if not lines or lines[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
                continue
            index = next((i for i, line in enumerate(lines) if "-->" in line), None)
            if index is None:
                continue
            stamp = lines[index]
            parts = re.fullmatch(
                r"\s*((?:\d+:)?\d{2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d+:)?\d{2}:\d{2}[.,]\d{1,3})(?:\s+[^\r\n]*)?", stamp)
            if parts is None or any(int(part) >= 60 for time in parts.groups()
                                    for part in re.split(r"[.,]", time)[0].split(":")[-2:]):
                raise TimingError("subtitle_invalid", "字幕时间格式无效")
            stamp = re.sub(r"([.,])(\d{1,3})(?=\s|$)", lambda m: m[1] + m[2].ljust(3, "0"), stamp)
            blocks.append("\n".join([stamp, *lines[index + 1:]]))
            _check_count(len(blocks), max_cues)
        events = pysubs2.SSAFile.from_string("\n\n".join(blocks), format_=ext, keep_html_tags=True)
        if len(events) != len(blocks):
            raise TimingError("subtitle_invalid", "字幕时间格式无效")
    cues = []
    for event in events:
        text = event.text.replace(r"\N", " ").replace(r"\n", " ").replace(marker, "\\")
        # XML parsing has already removed actual elements and decoded entities.
        # SRT/VTT retain source markup via keep_html_tags and need one clean pass.
        text = _source_plain(text) if ext in {"srt", "vtt"} else _plain(text)
        cues.append(SubtitleSegment(event.start / 1000, event.end / 1000, text))
    return _validated(cues, max_cues)


def parse_segments(raw: str, ext: str, *, max_cues: int) -> list[SubtitleSegment]:
    """Parse source timestamps; any untimed spoken cue disables the whole timeline."""
    ext = ext.lower().lstrip(".")
    try:
        if ext in {"srt", "vtt", "ttml"}:
            return _library_segments(raw, ext, max_cues)
        if ext == "json3":
            payload = json.loads(raw)
            cues = []
            missing = False
            count = 0
            for event in payload["events"]:
                text = _plain("".join(seg.get("utf8", "") for seg in (event.get("segs") or [])))
                if not _plain(text):
                    continue
                count += 1
                _check_count(count, max_cues)
                if "tStartMs" not in event or "dDurationMs" not in event:
                    missing = True
                    continue
                start, duration = _number(event["tStartMs"]), _number(event["dDurationMs"])
                cues.append(SubtitleSegment(start / 1000, (start + duration) / 1000, text))
        elif ext == "bilibili_json":
            cues = [SubtitleSegment(_number(cue["from"]), _number(cue["to"]), _plain(cue["content"]))
                    for cue in json.loads(raw)["body"]]
            missing = False
        elif ext == "srv3":
            cues = []
            missing = False
            count = 0
            for node in ET.fromstring(raw).iter():
                if node.tag.rsplit("}", 1)[-1] != "p":
                    continue
                text = "".join(node.itertext())
                if not _plain(text):
                    continue
                count += 1
                _check_count(count, max_cues)
                if "t" not in node.attrib or "d" not in node.attrib:
                    missing = True
                    continue
                start, duration = _number(float(node.attrib["t"])), _number(float(node.attrib["d"]))
                cues.append(SubtitleSegment(start / 1000, (start + duration) / 1000, text))
        else:
            return []
        result = _validated(cues, max_cues)
        return [] if missing else result
    except TimingError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, ET.ParseError) as exc:
        raise TimingError("subtitle_invalid", "字幕时间格式无效") from exc
    except NotImplementedError:
        return []  # e.g. TTML frame-based timing unsupported by pysubs2


def export_segments(segments: Iterable[SubtitleSegment], format: str) -> str:
    """Serialize plain-text segments; never reinterpret markup or HTML entities."""
    if format not in {"srt", "vtt"}:
        raise TimingError("subtitle_invalid", "不支持的字幕导出格式")
    from ..config import settings
    cues = _validated(segments, settings.subtitle_max_cues)
    if not cues:
        raise TimingError("subtitle_timing_unavailable", "此字幕来源没有可用时间轴")
    # pysubs2's SSA intermediate syntax treats literal backslashes as newline/
    # space commands even with styling disabled. Shield them only while writing.
    marker = uuid4().hex
    while any(marker in cue.text for cue in cues):
        marker = uuid4().hex
    subs = pysubs2.SSAFile()
    for cue in cues:
        if cue.end * 1000 > MAX_REPRESENTABLE_TIME:
            raise TimingError("subtitle_invalid", "字幕时间超出导出格式范围")
        subs.append(pysubs2.SSAEvent(start=round(cue.start * 1000), end=round(cue.end * 1000),
                                    text=cue.text.replace("\\", marker)))
    return subs.to_string(format, apply_styles=False, keep_ssa_tags=True).replace(marker, "\\")


def safe_export_filename(title: str, format: str) -> str:
    if format not in {"srt", "vtt"}:
        raise TimingError("subtitle_invalid", "不支持的字幕导出格式")
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", title).strip(" .")[:120].rstrip(" .")
    if not stem or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", stem):
        stem = "subtitle"
    return f"{stem}.{format}"
