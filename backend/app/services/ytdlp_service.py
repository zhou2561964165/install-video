import math
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
import httpx
from yt_dlp.extractor.bilibili import BiliBiliIE
from yt_dlp.utils import (
    MEDIA_EXTENSIONS, DownloadError, ExtractorError, GeoRestrictedError, UnsupportedError,
    ext2mimetype, mimetype2ext, url_or_none,
)

from ..config import settings
from .subtitle_sources import InvalidVideoPartError, resolve_public_subtitles

ERROR_INVALID_URL = "invalid_url"
ERROR_UNSUPPORTED = "unsupported_site"
ERROR_AGE = "age_restricted"
ERROR_GEO = "geo_blocked"
ERROR_DRM = "drm"
ERROR_LOGIN = "login_required"
ERROR_FFMPEG = "ffmpeg_missing"
ERROR_NETWORK = "network"
ERROR_QUOTA = "quota"
ERROR_VERIFICATION = "verification_required"


class _BiliBiliVerificationError(ExtractorError):
    def __init__(self):
        super().__init__(
            "B站触发了安全校验，暂未提供视频流。请稍后重试，避免连续反复解析。",
            expected=True,
        )


class _BiliBiliVerificationIE(BiliBiliIE):
    """Retain upstream extraction while recognizing its unhandled voucher response."""

    IE_NAME = BiliBiliIE.IE_NAME

    @classmethod
    def ie_key(cls):
        # Replace the existing key in place so redirects and playlists use the same adapter.
        return BiliBiliIE.ie_key()

    def _download_playinfo(self, bvid, cid, headers=None, query=None, fatal=True):
        play_info = super()._download_playinfo(bvid, cid, headers=headers, query=query, fatal=fatal)
        # Extra qn probes are optional; upstream retains the primary formats if one is blocked.
        if not (query or {}).get("qn") and isinstance(play_info, dict) and play_info.get("v_voucher"):
            if not any(url_or_none(fmt.get("url")) for fmt in self.extract_formats(play_info)):
                raise _BiliBiliVerificationError()
        return play_info


def _youtube_dl(opts: dict):
    ydl = yt_dlp.YoutubeDL(opts)
    # The public registration interface preserves yt-dlp's normal extractor selection.
    ydl.add_info_extractor(_BiliBiliVerificationIE())
    return ydl

_PATTERNS = [
    (ERROR_DRM, re.compile(r"drm|widevine|protected content|encrypted")),
    (ERROR_AGE, re.compile(r"age[-_ ]?restricted|confirm your age|age verification|adult")),
    (ERROR_LOGIN, re.compile(r"sign in|login required|private video|members.?only|authentication|premium")),
    (ERROR_GEO, re.compile(r"geo[-_ ]?restricted|not available in your country|geoblock|country")),
    (ERROR_FFMPEG, re.compile(r"ffmpeg|ffprobe")),
    (ERROR_UNSUPPORTED, re.compile(r"unsupported url|no suitable extractor|unsupported website|not supported")),
    (ERROR_NETWORK, re.compile(r"timed out|timeout|connection|network|unreachable|ssl|certificate|refused|temporary failure|unable to download")),
]


def _network_retry_options() -> dict:
    backoff_seconds = settings.network_retry_backoff_seconds

    def exponential_backoff(n: int) -> float:
        return backoff_seconds * (2 ** max(0, n))

    return {
        "retries": settings.network_retries,
        "extractor_retries": settings.network_retries,
        "retry_sleep_functions": {
            "http": exponential_backoff,
            "extractor": exponential_backoff,
        },
    }


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def extract_info(url: str) -> dict:
    opts = {
        **_network_retry_options(),
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    with _youtube_dl(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _is_caption(language: str, item: dict) -> bool:
    return language not in {"live_chat", "danmaku"} and not str(item.get("protocol", "")).startswith("youtube_live_chat")


def extract_subtitle_tracks(url: str, *, use_public_sources: bool = True) -> dict:
    """返回规范化字幕轨道；这是项目其余层读取 yt-dlp 字幕信息的唯一入口。"""
    # Platform-native captions are sufficient for AI content analysis. Avoid unnecessary
    # video page extraction when a public source adapter can already supply the content.
    fallback_error = None
    if use_public_sources:
        try:
            fallback = resolve_public_subtitles(url)
            if fallback["tracks"]:
                return {**fallback, "_source": "public"}
        except InvalidVideoPartError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            fallback_error = error
    info = extract_info(url)
    tracks: list[dict] = []
    is_bilibili = urlparse(url).hostname in {"bilibili.com", "www.bilibili.com"}
    for source_key, is_auto in (("subtitles", False), ("automatic_captions", True)):
        for language, formats in (info.get(source_key) or {}).items():
            normalized_formats = []
            for item in formats or []:
                if not _is_caption(language, item):
                    continue
                track_url = item.get("url")
                inline = item.get("data")
                if isinstance(inline, str) and inline:
                    normalized_formats.append({
                        "data": inline, "ext": str(item.get("ext") or "vtt").lower(),
                        "name": item.get("name"), "http_headers": {},
                    })
                    continue
                if not track_url or not str(track_url).startswith(("http://", "https://")):
                    continue
                normalized_formats.append({
                    "url": str(track_url),
                    "ext": str(item.get("ext") or "vtt").lower(),
                    "name": item.get("name"),
                    "http_headers": {**(info.get("http_headers") or {}), **(item.get("http_headers") or {})},
                })
            if normalized_formats:
                automatic_language = is_bilibili and str(language).startswith("ai-")
                tracks.append({
                    "language": str(language)[3:] if automatic_language else str(language),
                    "is_auto": is_auto or automatic_language,
                    "formats": normalized_formats,
                })
    if not tracks:
        if fallback_error:
            raise fallback_error
        return {"title": info.get("title") or "", "tracks": []}
    return {"title": info.get("title") or "", "tracks": tracks}


def classify_error(exc: Exception) -> str:
    original = exc.exc_info[1] if isinstance(exc, DownloadError) and exc.exc_info else exc
    if isinstance(original, _BiliBiliVerificationError):
        return ERROR_VERIFICATION
    if isinstance(exc, InvalidVideoPartError):
        return ERROR_INVALID_URL
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
    opts = {
        **_network_retry_options(),
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    with _youtube_dl(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        for f in info.get("formats") or []:
            if str(f.get("format_id")) == str(format_id):
                direct = f.get("url")
                if direct and str(direct).startswith("http"):
                    return str(direct), f.get("http_headers") or {}
    return None, {}


def download(url: str, format_id: str, outtmpl: str, progress_hook) -> str:
    opts = {
        **_network_retry_options(),
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
    with _youtube_dl(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        out_dir = Path(os.path.dirname(outtmpl) or ".").resolve()

        def validated_output(
            candidate: str,
            *,
            missing_ok: bool = False,
            format_metadata: dict | None = None,
            allow_unknown_mime_video: bool = False,
        ) -> str | None:
            if not isinstance(candidate, (str, os.PathLike)) or not os.fspath(candidate):
                raise FileNotFoundError("下载产物路径无效")
            path = Path(candidate).resolve()
            try:
                path.relative_to(out_dir)
            except ValueError as exc:
                raise FileNotFoundError("下载产物路径超出任务目录") from exc
            extension = path.suffix.lower().lstrip(".")
            mime_type = ext2mimetype(extension)
            is_video_container = extension in MEDIA_EXTENSIONS.video or (
                isinstance(mime_type, str) and mime_type.lower().startswith("video/")
            )
            metadata = format_metadata or {}
            video_codec = metadata.get("vcodec")
            if isinstance(video_codec, str) and video_codec.strip().lower() == "none":
                raise FileNotFoundError("下载产物不是视频文件")
            if not is_video_container:
                is_sidecar_extension = (
                    extension in {"part", "ytdl", "tmp", "temp"}
                    or extension in MEDIA_EXTENSIONS.subtitles
                    or extension in MEDIA_EXTENSIONS.thumbnails
                    or extension in MEDIA_EXTENSIONS.manifests
                    or extension in MEDIA_EXTENSIONS.storyboards
                )
                if is_sidecar_extension or not allow_unknown_mime_video:
                    raise FileNotFoundError("下载产物不是视频文件")
                if mime_type and mime_type.lower() not in {"application/octet-stream", "binary/octet-stream"}:
                    raise FileNotFoundError("下载产物不是视频文件")
                selected_ext = metadata.get("ext")
                if not isinstance(selected_ext, str) or selected_ext.strip().lower().lstrip(".") != extension:
                    raise FileNotFoundError("下载产物扩展名与所选格式不符")

                height = metadata.get("height")
                has_video_metadata = (
                    isinstance(video_codec, str) and bool(video_codec.strip())
                    or isinstance(height, (int, float))
                    and not isinstance(height, bool)
                    and math.isfinite(height)
                    and height > 0
                )
                if not has_video_metadata:
                    generic_direct = (
                        metadata.get("extractor_key") == "Generic"
                        and metadata.get("direct") is True
                        and isinstance(metadata.get("format_id"), str)
                    )
                    if generic_direct:
                        inferred_ext = mimetype2ext(f"video/{metadata['format_id']}")
                        inferred_mime = ext2mimetype(inferred_ext) if inferred_ext else None
                        has_video_metadata = inferred_ext in MEDIA_EXTENSIONS.video or (
                            isinstance(inferred_mime, str) and inferred_mime.lower().startswith("video/")
                        )
                if not has_video_metadata:
                    raise FileNotFoundError("下载产物缺少视频格式元数据")
            if not path.is_file():
                if missing_ok:
                    return None
                raise FileNotFoundError("下载产物缺失")
            return str(path)

        # yt-dlp stores the processed per-download dictionaries here. Their filepath is
        # updated by post-processing and MoveFilesAfterDownloadPP to the terminal output.
        final_path = info.get("filepath") if isinstance(info, dict) else None
        requested_downloads = info.get("requested_downloads") if isinstance(info, dict) else None
        format_metadata = info if isinstance(info, dict) else {}
        if isinstance(requested_downloads, (list, tuple)) and len(requested_downloads) == 1:
            request_info = requested_downloads[0]
            if isinstance(request_info, dict):
                format_metadata = {**format_metadata, **request_info}
        if final_path is not None:
            return validated_output(
                final_path,
                format_metadata=format_metadata,
                allow_unknown_mime_video=True,
            )
        if requested_downloads:
            if not isinstance(requested_downloads, (list, tuple)) or len(requested_downloads) != 1:
                raise FileNotFoundError("下载产物路径不唯一")
            request_info = requested_downloads[0]
            if not isinstance(request_info, dict):
                raise FileNotFoundError("下载产物路径无效")
            format_metadata = {**format_metadata, **request_info}
            final_path = request_info.get("filepath")
            if final_path is not None:
                return validated_output(
                    final_path,
                    format_metadata=format_metadata,
                    allow_unknown_mime_video=True,
                )

        # Compatibility path for older extractors that do not return a terminal filepath.
        prepared_filename = ydl.prepare_filename(info)
        if not prepared_filename:
            raise FileNotFoundError("下载产物缺失")
        candidates: list[str] = []
        requested_formats = info.get("requested_formats") if isinstance(info, dict) else None
        merge_ext = opts.get("merge_output_format")
        if (
            isinstance(requested_formats, (list, tuple))
            and len(requested_formats) > 1
            and isinstance(merge_ext, str)
            and merge_ext.lower() in MEDIA_EXTENSIONS.video
        ):
            candidates.append(str(Path(prepared_filename).with_suffix(f".{merge_ext.lower()}")))
        if prepared_filename not in candidates:
            candidates.append(str(prepared_filename))
        for candidate in candidates:
            selected = validated_output(candidate, missing_ok=True, format_metadata=format_metadata)
            if selected:
                return selected
        raise FileNotFoundError("下载产物缺失")
