import os
import re
from urllib.parse import urlparse

import yt_dlp
import httpx
from yt_dlp.utils import GeoRestrictedError, UnsupportedError

from ..config import settings
from .subtitle_sources import resolve_public_subtitles

ERROR_INVALID_URL = "invalid_url"
ERROR_UNSUPPORTED = "unsupported_site"
ERROR_AGE = "age_restricted"
ERROR_GEO = "geo_blocked"
ERROR_DRM = "drm"
ERROR_LOGIN = "login_required"
ERROR_FFMPEG = "ffmpeg_missing"
ERROR_NETWORK = "network"
ERROR_QUOTA = "quota"

_PATTERNS = [
    (ERROR_DRM, re.compile(r"drm|widevine|protected content|encrypted")),
    (ERROR_AGE, re.compile(r"age[-_ ]?restricted|confirm your age|age verification|adult")),
    (ERROR_LOGIN, re.compile(r"sign in|login required|private video|members.?only|authentication|premium")),
    (ERROR_GEO, re.compile(r"geo[-_ ]?restricted|not available in your country|geoblock|country")),
    (ERROR_FFMPEG, re.compile(r"ffmpeg|ffprobe")),
    (ERROR_UNSUPPORTED, re.compile(r"unsupported url|no suitable extractor|unsupported website|not supported")),
    (ERROR_NETWORK, re.compile(r"timed out|timeout|connection|network|unreachable|ssl|certificate|refused|temporary failure|unable to download")),
]


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def extract_info(url: str) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _is_caption(language: str, item: dict) -> bool:
    return language not in {"live_chat", "danmaku"} and not str(item.get("protocol", "")).startswith("youtube_live_chat")


def extract_subtitle_tracks(url: str) -> dict:
    """返回规范化字幕轨道；这是项目其余层读取 yt-dlp 字幕信息的唯一入口。"""
    # Platform-native captions are sufficient for AI content analysis. Avoid unnecessary
    # video page extraction when a public source adapter can already supply the content.
    fallback_error = None
    try:
        fallback = resolve_public_subtitles(url)
        if fallback["tracks"]:
            return fallback
    except (httpx.HTTPError, ValueError) as error:
        fallback_error = error
    info = extract_info(url)
    tracks: list[dict] = []
    for source_key, is_auto in (("subtitles", False), ("automatic_captions", True)):
        for language, formats in (info.get(source_key) or {}).items():
            normalized_formats = []
            for item in formats or []:
                if not _is_caption(language, item):
                    continue
                track_url = item.get("url")
                if not track_url or not str(track_url).startswith(("http://", "https://")):
                    continue
                normalized_formats.append({
                    "url": str(track_url),
                    "ext": str(item.get("ext") or "vtt").lower(),
                    "name": item.get("name"),
                    "http_headers": {**(info.get("http_headers") or {}), **(item.get("http_headers") or {})},
                })
            if normalized_formats:
                tracks.append({
                    "language": str(language),
                    "is_auto": is_auto,
                    "formats": normalized_formats,
                })
    if not tracks:
        if fallback_error:
            raise fallback_error
        return {"title": info.get("title") or "", "tracks": []}
    return {"title": info.get("title") or "", "tracks": tracks}


def classify_error(exc: Exception) -> str:
    if isinstance(exc, GeoRestrictedError):
        return ERROR_GEO
    if isinstance(exc, UnsupportedError):
        return ERROR_UNSUPPORTED
    msg = str(exc).lower()
    for error_type, pattern in _PATTERNS:
        if pattern.search(msg):
            return error_type
    return ERROR_NETWORK


HEIGHT_TIERS = [2160, 1440, 1080, 720, 480, 360]

# ffmpeg 合并（音视频分离流）只对 >= 此分辨率的档位开放；
# 低于此分辨率的档位只用渐进式直链，无直链则跳过该档（不触发 ffmpeg）。
FFMPEG_MIN_HEIGHT = 1080


def _format_duration(seconds) -> str:
    if not seconds:
        return "00:00"
    hours, rem = divmod(int(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_filesize(size) -> str:
    if not size:
        return "未知大小"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f}KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}MB"
    return f"{size / (1024 * 1024 * 1024):.2f}GB"


def _is_video(fmt: dict) -> bool:
    return bool(fmt.get("height")) and fmt.get("vcodec") not in (None, "none")


def _progressive_direct(formats: list[dict], height: int) -> dict | None:
    for f in formats:
        if (
            f.get("height") == height
            and f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
        ):
            url = f.get("url")
            if url and str(url).startswith("http"):
                return f
    return None


def build_format_options(info: dict) -> list[dict]:
    formats = info.get("formats") or []
    heights = sorted({f["height"] for f in formats if _is_video(f)}, reverse=True)
    options: list[dict] = []
    seen: set[int] = set()
    for tier in HEIGHT_TIERS:
        h = next((x for x in heights if x <= tier), None)
        if h is None or h in seen:
            continue
        seen.add(h)
        direct_fmt = _progressive_direct(formats, h)
        if direct_fmt:
            ext = direct_fmt.get("ext") or "mp4"
            filesize = direct_fmt.get("filesize") or direct_fmt.get("filesize_approx")
            width = direct_fmt.get("width")
            options.append({
                "format_id": str(direct_fmt["format_id"]),
                "label": f"{h}p {ext.upper()} ({_format_filesize(filesize)})",
                "height": h,
                "ext": ext,
                "resolution": f"{width}x{h}" if width else f"{h}p",
                "filesize": filesize,
                "has_audio": True,
                "vcodec": direct_fmt.get("vcodec"),
                "acodec": direct_fmt.get("acodec"),
                "direct": True,
                "note": direct_fmt.get("format_note"),
            })
        elif h >= FFMPEG_MIN_HEIGHT:
            options.append({
                "format_id": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
                "label": f"{h}p 最佳 (视频+音频合并)",
                "height": h,
                "ext": "mp4",
                "resolution": f"{h}p",
                "filesize": None,
                "has_audio": True,
                "vcodec": None,
                "acodec": "merged",
                "direct": False,
                "note": None,
            })
    if not options:
        options.append({
            "format_id": "best",
            "label": "最佳",
            "height": None,
            "ext": "mp4",
            "resolution": None,
            "filesize": None,
            "has_audio": True,
            "vcodec": None,
            "acodec": "merged",
            "direct": False,
            "note": None,
        })
    return options


def parse_video(url: str) -> tuple[dict, list[dict]]:
    info = extract_info(url)
    languages = list(dict.fromkeys(
        language
        for source in ("subtitles", "automatic_captions")
        for language, tracks in (info.get(source) or {}).items()
        if any(_is_caption(language, item) for item in tracks or [])
    ))
    if not languages:
        # Caption metadata is an optional enhancement, and must not break video parsing/download.
        try:
            languages = list(dict.fromkeys(t["language"] for t in resolve_public_subtitles(url)["tracks"]))
        except (httpx.HTTPError, ValueError):
            pass
    meta = {
        "title": info.get("title") or "",
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "duration_string": _format_duration(info.get("duration")),
        "uploader": info.get("uploader") or info.get("channel"),
        "platform": info.get("extractor") or info.get("extractor_key"),
        "view_count": info.get("view_count"),
        "upload_date": info.get("upload_date"),
        "description": (info.get("description") or "")[:200],
        "subtitles": languages,
    }
    options = build_format_options(info)
    return meta, options


def get_direct_url(url: str, format_id: str) -> tuple[str | None, dict]:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        for f in info.get("formats") or []:
            if str(f.get("format_id")) == str(format_id):
                direct = f.get("url")
                if direct and str(direct).startswith("http"):
                    return str(direct), f.get("http_headers") or {}
    return None, {}


def download(url: str, format_id: str, outtmpl: str, progress_hook) -> str:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": format_id,
        "outtmpl": outtmpl,
        "progress_hooks": [progress_hook],
        "merge_output_format": "mp4",
        "noprogress": True,
    }
    # ffmpeg 用于合并音视频流：默认 "ffmpeg" 表示在 PATH 上，交给 yt-dlp 自行查找；
    # 仅当显式配置了非默认路径时才传 ffmpeg_location，避免把裸名 "ffmpeg" 误当相对路径。
    if settings.ffmpeg_path and settings.ffmpeg_path != "ffmpeg":
        opts["ffmpeg_location"] = settings.ffmpeg_path
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    filename = ydl.prepare_filename(info)
    # 合并后扩展名可能变化（如 .webm → .mp4）；取目录下最新文件作为产物
    out_dir = os.path.dirname(outtmpl)
    files = [os.path.join(out_dir, f) for f in os.listdir(out_dir)]
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        raise FileNotFoundError("下载产物缺失")
    return max(files, key=os.path.getmtime)
