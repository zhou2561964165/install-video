"""Anonymous Bilibili subtitle metadata; no cookies or yt-dlp dependency."""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx

from ..config import settings
from . import network_retry


class InvalidVideoPartError(ValueError):
    """Explicit user part selection must never default to a different video."""


def _metadata(client: httpx.Client, endpoint: str, params: dict) -> dict:
    def get():
        with client.stream("GET", endpoint, params=params) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                if len(body) + len(chunk) > settings.subtitle_max_bytes:
                    raise ValueError("字幕来源元数据超过大小限制")
                body.extend(chunk)
        payload = json.loads(body)
        if not isinstance(payload, dict) or type(payload.get("code")) is not int:
            raise ValueError("字幕来源元数据结构无效")
        if payload["code"] != 0:
            raise ValueError("平台字幕元数据暂不可公开访问")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("字幕来源元数据结构无效")
        return data
    return network_retry.retry_get(get, max_retries=settings.network_retries, backoff_seconds=settings.network_retry_backoff_seconds)


def _caption_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("字幕来源地址无效")
    parsed = urlparse("https:" + value if value.startswith("//") else value)
    # AI captions use an extensionless production object on this dedicated host.
    # Keep its path boundary narrow rather than accepting arbitrary CDN resources.
    is_ai_caption = parsed.hostname == "aisubtitle.hdslb.com" and not parsed.params and re.fullmatch(
        r"/bfs/ai_subtitle/prod/[A-Za-z0-9_-]+", parsed.path
    )
    is_manual_caption = parsed.path.startswith("/bfs/subtitle/") and parsed.path.endswith(".json")
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or not parsed.hostname.endswith(".hdslb.com") or parsed.username or parsed.password
            or parsed.port not in {None, 80, 443}
            or not (is_manual_caption or is_ai_caption)):
        raise ValueError("字幕来源地址无效")
    return urlunparse(parsed._replace(scheme="https", netloc=parsed.hostname, fragment=""))


def bilibili_tracks(url: str) -> dict:
    parsed = urlparse(url)
    match = re.fullmatch(r"/video/(BV[A-Za-z0-9]{10})/?", parsed.path)
    if not match:
        return {"tracks": []}
    bvid = match.group(1)
    part_values = parse_qs(parsed.query, keep_blank_values=True).get("p", ["1"])
    if len(part_values) != 1 or not re.fullmatch(r"[1-9][0-9]*", part_values[0]):
        raise InvalidVideoPartError("视频分P编号无效")
    try:
        part = int(part_values[0])
    except ValueError as exc:
        raise InvalidVideoPartError("视频分P编号无效") from exc
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://www.bilibili.com/video/{bvid}"}
    with httpx.Client(timeout=settings.subtitle_timeout_seconds, headers=headers, follow_redirects=False) as client:
        view = _metadata(client, "https://api.bilibili.com/x/web-interface/view", {"bvid": bvid})
        if view.get("bvid") != bvid or type(view.get("aid")) is not int or view["aid"] <= 0 or not isinstance(view.get("title"), str):
            raise ValueError("视频元数据关联无效")
        pages = view.get("pages")
        if not isinstance(pages, list) or not pages or any(
            not isinstance(page, dict) or type(page.get("page")) is not int or page["page"] <= 0
            or type(page.get("cid")) is not int or page["cid"] <= 0 for page in pages
        ):
            raise ValueError("视频分P元数据无效")
        selected = [page for page in pages if type(page.get("page")) is int and page["page"] == part]
        if not selected:
            raise InvalidVideoPartError("视频分P不存在")
        if len(selected) != 1:
            raise ValueError("视频分P关联无效")
        player = _metadata(client, "https://api.bilibili.com/x/v2/dm/view", {"aid": view["aid"], "oid": selected[0]["cid"], "type": 1})
    if player.get("need_login_subtitle"):
        return {"tracks": []}
    subtitles = player.get("subtitle", {})
    if not isinstance(subtitles, dict) or not isinstance(subtitles.get("subtitles", []), list):
        raise ValueError("平台字幕轨道结构无效")
    groups = {}
    for caption in subtitles.get("subtitles", []):
        if not isinstance(caption, dict):
            raise ValueError("平台字幕轨道结构无效")
        lang = caption.get("lan")
        kind = caption.get("type", 0)
        if not isinstance(lang, str) or type(kind) is not int or kind not in {0, 1}:
            raise ValueError("平台字幕语言或类型无效")
        is_auto = lang.startswith("ai-") or kind == 1
        language = lang[3:] if lang.startswith("ai-") else lang
        if not re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*", language):
            raise ValueError("平台字幕语言无效")
        group = groups.setdefault((language, is_auto), {"language": language, "is_auto": is_auto, "formats": []})
        group["formats"].append({"url": _caption_url(caption.get("subtitle_url")), "ext": "bilibili_json", "name": language, "http_headers": headers})
    return {"title": view["title"], "tracks": list(groups.values())}
