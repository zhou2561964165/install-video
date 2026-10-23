import math
import os
import re
import time
from contextlib import contextmanager
from http.cookiejar import DefaultCookiePolicy
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import BaseHandler

import yt_dlp
from yt_dlp.downloader import get_suitable_downloader
from yt_dlp.downloader.http import HttpFD
from yt_dlp.networking._urllib import UrllibRH, RedirectHandler
import httpx
from yt_dlp.extractor.bilibili import BiliBiliIE
from yt_dlp.utils import (
    MEDIA_EXTENSIONS, DownloadError, ExtractorError, GeoRestrictedError, UnsupportedError,
    ext2mimetype, mimetype2ext, url_or_none,
)

from ..config import settings
from .subtitle_sources import InvalidVideoPartError, resolve_public_subtitles
from .asr_errors import ASRError
from .bilibili_session import SessionError, cookie_jar_for_url, is_bilibili_url, session_enabled
from .bilibili_api_source import BilibiliApiError, extract_api_video, safe_media_url, video_identity

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
VERIFICATION_ERROR_MESSAGE = "B站触发了安全校验，暂未提供视频流。请稍后重试，避免连续反复解析。"


def _is_bilibili_verification_signal(message: str) -> bool:
    """Only documented upstream denial signals, within a known Bilibili context."""
    return bool(re.search(
        r"\bhttp error 412\b|\bunable to download video info:\s*(?:401|352)\b"
        r"|\byou have exceeded the rate limit\b",
        message.lower(),
    ))


class DownloadQuotaError(Exception):
    """A local download storage limit, including failures wrapped by yt-dlp."""


class _BiliBiliVerificationError(ExtractorError):
    def __init__(self):
        super().__init__(
            VERIFICATION_ERROR_MESSAGE,
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
        primary = not (query or {}).get("qn")
        try:
            # Upstream suppresses primary business denials with fatal=False, losing the
            # reason before its generic no-formats failure. Preserve other fallback behavior.
            play_info = super()._download_playinfo(
                bvid, cid, headers=headers, query=query, fatal=True if primary else fatal,
            )
        except ExtractorError as error:
            if primary and _is_bilibili_verification_signal(str(error)):
                if fatal:
                    raise _BiliBiliVerificationError() from error
                # The upstream caller may still have usable window.__playinfo__ data.
                self._primary_verification_pending = True
                return None
            if fatal:
                raise
            self.report_warning(str(error))
            return None
        # Extra qn probes are optional; upstream retains the primary formats if one is blocked.
        if primary and isinstance(play_info, dict) and play_info.get("v_voucher"):
            if not any(url_or_none(fmt.get("url")) for fmt in super().extract_formats(play_info)):
                if fatal:
                    raise _BiliBiliVerificationError()
                self._primary_verification_pending = True
                return None
        return play_info

    def extract_formats(self, play_info):
        formats = super().extract_formats(play_info)
        if getattr(self, "_primary_verification_pending", False):
            self._primary_verification_pending = False
            # Upstream reaches this with either the API result or its webpage fallback.
            # A previous denial is relevant only when neither supplied any usable stream.
            if not any(url_or_none(fmt.get("url")) for fmt in formats):
                raise _BiliBiliVerificationError()
        return formats

    def _real_extract(self, url):
        self._primary_verification_pending = False
        try:
            return super()._real_extract(url)
        except ExtractorError as error:
            if _is_bilibili_verification_signal(str(error)):
                raise _BiliBiliVerificationError() from error
            raise
        finally:
            self._primary_verification_pending = False


class _BiliBiliApiIE(BiliBiliIE):
    """Keep upstream selection and format conversion; replace only extraction."""
    IE_NAME = BiliBiliIE.IE_NAME

    @classmethod
    def ie_key(cls):
        return BiliBiliIE.ie_key()

    def _real_extract(self, url):
        info = extract_api_video(url)
        info['formats'] = self.extract_formats(info.pop('play_info'))
        if (not any(f.get('vcodec') not in {None, 'none'} for f in info['formats'])
                or not any(f.get('acodec') not in {None, 'none'} for f in info['formats'])):
            raise BilibiliApiError()
        return info


class _BiliApiRequestGuard(BaseHandler):
    # Run after HTTPCookieProcessor (500), including any Set-Cookie response jar.
    handler_order = 1000

    def https_request(self, request):
        if safe_media_url(request.full_url) != request.full_url:
            raise BilibiliApiError('unsupported_site')
        for headers in (request.headers, request.unredirected_hdrs):
            for name in list(headers):
                if name.lower() in {'cookie', 'cookie2', 'authorization', 'proxy-authorization'}:
                    del headers[name]
        request.add_header('Accept-Encoding', 'identity')
        return request

    http_request = https_request


class _BiliApiResponseGuard(BaseHandler):
    # Upstream HTTPHandler (500) eagerly decompresses some responses. Reject
    # encoded media before that handler can allocate or read outside our budget.
    handler_order = 400

    def https_response(self, request, response):
        if response.headers.get('Content-Encoding', '').strip().lower() not in {'', 'identity'}:
            response.close()
            raise BilibiliApiError('network')
        return response

    http_response = https_response


class _BiliApiUrllibRH(UrllibRH):
    def _create_instance(self, *args, **kwargs):
        opener = super()._create_instance(*args, **kwargs)
        opener.add_handler(_BiliApiRequestGuard())
        opener.add_handler(_BiliApiResponseGuard())
        def deny_redirect(*args, **kwargs):
            raise BilibiliApiError('network')
        for handler in opener.handlers:
            if isinstance(handler, RedirectHandler):
                handler.redirect_request = deny_redirect
        return opener

    def _send(self, request):
        if safe_media_url(request.url) != request.url:
            raise BilibiliApiError('unsupported_site')
        def guard():
            if time.monotonic() >= self._api_deadline:
                raise BilibiliApiError('network')
        guard()
        response = super()._send(request)
        guard()
        # HttpFD asks for a full block. HTTPResponse.read(n) may keep filling it
        # forever while a peer trickles data inside the socket timeout. read1
        # returns after one underlying socket read, allowing the total guard to
        # run between reads. The shared deadline covers all selected streams.
        reader = getattr(response.fp, 'read1', None)
        if not callable(reader):
            response.close()
            raise BilibiliApiError('unsupported_site')
        def bounded_read(amt=None):
            if response.closed:
                return b''
            try:
                guard()
                data = reader(-1 if amt is None else amt)
                guard()
                if not data:
                    response.close()
                return data
            except Exception:
                response.close()
                raise
        response.read = bounded_read
        return response


def _api_mode(url: str) -> bool:
    if not settings.bilibili_api_enabled:
        return False
    try:
        # Include malformed official URLs (userinfo/ports) in the fail-closed
        # API boundary so they cannot reach yt-dlp's generic webpage extractor.
        host = urlparse(url).hostname or ''
        return any(host == root or host.endswith('.' + root) for root in ('bilibili.com', 'b23.tv'))
    except ValueError:
        return False


def _youtube_dl(opts: dict):
    ydl = yt_dlp.YoutubeDL(opts)
    # The public registration interface preserves yt-dlp's normal extractor selection.
    ydl.add_info_extractor(_BiliBiliApiIE() if settings.bilibili_api_enabled else _BiliBiliVerificationIE())
    return ydl


class _PrivateBilibiliLogger:
    """yt-dlp logs can contain cookie material and signed CDN URLs."""

    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


class _BilibiliSourceError(RuntimeError):
    def __init__(self, category: str):
        self.category = category
        super().__init__({
            ERROR_VERIFICATION: VERIFICATION_ERROR_MESSAGE,
            ERROR_LOGIN: 'B站视频需要登录权限，请管理员更新访问凭据后重试。',
            ERROR_GEO: 'B站视频受地区限制，暂时无法访问。',
            ERROR_AGE: 'B站视频存在年龄限制，暂时无法访问。',
            ERROR_DRM: 'B站视频受版权保护，无法下载。',
            ERROR_UNSUPPORTED: '暂不支持此B站视频。',
            ERROR_FFMPEG: '服务器音视频合并工具不可用，请联系管理员。',
            ERROR_QUOTA: '文件或音视频流合计超过大小上限。',
        }.get(category, 'B站视频访问失败，请稍后重试或联系管理员更新访问凭据。'))


def requires_server_download(url: str) -> bool:
    return _api_mode(url) or session_enabled(url)


def public_error_message(exc: Exception) -> str:
    """Credential contexts have already replaced upstream errors at their boundary."""
    if not isinstance(exc, SessionError) and classify_error(exc) == ERROR_VERIFICATION:
        return VERIFICATION_ERROR_MESSAGE
    return str(exc)


@contextmanager
def _source_youtube_dl(url: str, opts: dict):
    api_mode = _api_mode(url)
    if not api_mode and not session_enabled(url):
        with _youtube_dl(opts) as ydl:
            yield ydl
        return
    try:
        if api_mode:
            # Short-link/generic extractors must never issue a webpage request.
            video_identity(url)
        jar = cookie_jar_for_url(url)
        private_opts = {**opts, 'logger': _PrivateBilibiliLogger(),
                        'quiet': True, 'no_warnings': True, 'noprogress': True,
                        'http_headers': {**(opts.get('http_headers') or {}),
                                         'Referer': 'https://www.bilibili.com/'}}
        if api_mode:
            private_opts.update(retries=0, extractor_retries=0, fragment_retries=0,
                                file_access_retries=0, socket_timeout=8, proxy='')
        # Never pass cookiefile: yt-dlp writes that file back during close().
        with _youtube_dl(private_opts) as ydl:
            ydl.cookiejar.set_policy(DefaultCookiePolicy(
                strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain))
            for cookie in jar:
                ydl.cookiejar.set_cookie(cookie)
            # yt-dlp 2026.08.19: RequestsRH copies the jar into a requests jar
            # with a permissive policy, broadening host-only cookies. Use the
            # public director builder with only UrllibRH, which keeps this jar.
            # Installing it requires the narrowly scoped private cached slot;
            # keep the actual-handler regression when upgrading yt-dlp. A mere
            # handler preference would still allow unsafe fallback to Requests.
            previous_director = ydl.__dict__.get('_request_director')
            ydl._request_director = ydl.build_request_director([_BiliApiUrllibRH if api_mode else UrllibRH])
            if api_mode:
                deadline = time.monotonic() + settings.bilibili_api_download_timeout_seconds
                for handler in ydl._request_director.handlers.values():
                    handler._api_deadline = deadline
            if previous_director is not None:
                previous_director.close()
            process_info = ydl.process_info

            def native_process_info(info):
                # External downloaders may serialize cookies to argv or files.
                # Verified Bilibili DASH transfers are ordinary native HTTP files;
                # ffmpeg remains available afterwards for merging local inputs.
                streams = info.get('requested_formats') or [info]
                for stream in streams:
                    if (stream.get('protocol') not in {'http', 'https'}
                            or urlparse(stream.get('url') or '').scheme not in {'http', 'https'}
                            or stream.get('fragments') or stream.get('section_start') is not None
                            or stream.get('section_end') is not None
                            or get_suitable_downloader(stream, private_opts) is not HttpFD):
                        raise _BilibiliSourceError(ERROR_UNSUPPORTED)
                    if api_mode and safe_media_url(stream.get('url')) != stream.get('url'):
                        raise _BilibiliSourceError(ERROR_UNSUPPORTED)
                return process_info(info)

            ydl.process_info = native_process_info
            yield ydl
    except (SessionError, ASRError, DownloadQuotaError):
        raise
    except BilibiliApiError as error:
        raise _BilibiliSourceError(error.category) from None
    except Exception as error:
        category = (ERROR_VERIFICATION if _is_bilibili_verification_signal(str(error))
                    else classify_error(error))
        raise _BilibiliSourceError(category) from None

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
        # Per socket operation, not an overall extraction wall-clock deadline.
        "socket_timeout": settings.parse_socket_timeout_seconds,
        "extractor_retries": settings.parse_extractor_retries,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    with _source_youtube_dl(url, opts) as ydl:
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
        except (InvalidVideoPartError, SessionError):
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
    if isinstance(exc, SessionError):
        return ERROR_VERIFICATION
    if isinstance(exc, _BilibiliSourceError):
        return exc.category
    original = exc.exc_info[1] if isinstance(exc, DownloadError) and exc.exc_info else exc
    if isinstance(original, DownloadQuotaError):
        return ERROR_QUOTA
    if isinstance(original, _BiliBiliVerificationError):
        return ERROR_VERIFICATION
    message = str(exc)
    # yt-dlp can wrap ExtractorError repeatedly and discard our concrete subclass.
    # Accept only our complete local message in the explicit Bilibili context.
    if "[bilibili]" in message.lower() and (
        VERIFICATION_ERROR_MESSAGE in message or _is_bilibili_verification_signal(message)
    ):
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


HEIGHT_TIERS = [4320, 2160, 1440, 1080, 720, 480, 360]

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
    is_bilibili = str(info.get('extractor_key') or info.get('extractor') or '').lower() == 'bilibili'
    has_audio_stream = any(f.get('acodec') not in (None, 'none') for f in formats)
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
        elif h >= FFMPEG_MIN_HEIGHT or (is_bilibili and has_audio_stream):
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
    if not languages and not info.get('_bilibili_api'):
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


def restrict_format(url: str, format_id: str, max_height: int) -> str:
    """Resolve only server-generated choices; never trust arbitrary client selectors.

    Bound the actual download selector too, so metadata changes between validation
    and downloading cannot upgrade a free request beyond its entitlement.
    """
    info = extract_info(url)
    choices = build_format_options(info)
    choice = next((item for item in choices if item["format_id"] == format_id), None)
    if not choice or not isinstance(choice.get("height"), int) or choice["height"] > max_height:
        raise ValueError("Resolution requires VIP or cannot be verified")
    height = choice["height"]
    expected = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
    if format_id == expected:
        return format_id
    # Progressive direct formats are literal IDs supplied by the extractor.
    # Reject selector metacharacters even if a hostile extractor returns them.
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", format_id):
        raise ValueError("Unsafe format ID")
    return f"{format_id}[height<={max_height}]"


def get_direct_url(url: str, format_id: str) -> tuple[str | None, dict]:
    if requires_server_download(url):
        return None, {}
    bounded = re.fullmatch(r"([A-Za-z0-9_.-]+)\[height<=([0-9]+)\]", format_id)
    direct_id = bounded.group(1) if bounded else format_id
    height_limit = int(bounded.group(2)) if bounded else None
    opts = {
        **_network_retry_options(),
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    with _source_youtube_dl(url, opts) as ydl:
        info = ydl.extract_info(url, download=False)
        for f in info.get("formats") or []:
            if str(f.get("format_id")) == str(direct_id):
                if height_limit is not None and (not isinstance(f.get("height"), (int, float))
                        or isinstance(f.get("height"), bool) or not 0 < f["height"] <= height_limit):
                    continue
                direct = f.get("url")
                if direct and str(direct).startswith("http"):
                    return str(direct), f.get("http_headers") or {}
    return None, {}


def fetch_transcription_audio(url: str, directory: Path) -> tuple[Path, str]:
    """Acquire one bounded audio-only source; caller owns the temporary directory."""
    if not is_valid_url(url):
        raise ASRError('invalid_url', '无效链接')
    started = time.monotonic()
    def guard(progress):
        if time.monotonic() - started > settings.asr_timeout_seconds:
            raise ASRError('transcription_timeout', '音频获取超过处理时间限制')
        if max(progress.get('downloaded_bytes') or 0, progress.get('total_bytes') or 0,
               progress.get('total_bytes_estimate') or 0) > settings.asr_max_bytes:
            raise ASRError('transcription_too_large', '音频文件超过大小限制')
    opts = {
        'quiet': True, 'no_warnings': True, 'noplaylist': True,
        'format': 'bestaudio/best', 'outtmpl': str(directory / 'audio.%(ext)s'),
        'max_filesize': settings.asr_max_bytes, 'progress_hooks': [guard],
        'socket_timeout': settings.subtitle_timeout_seconds,
        'retries': 0, 'extractor_retries': 0, 'fragment_retries': 0,
    }
    try:
        with _source_youtube_dl(url, opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration') if isinstance(info, dict) else None
            if (not isinstance(info, dict) or info.get('_type') in {'playlist', 'multi_video'}
                    or info.get('is_live') or info.get('live_status') == 'is_live'):
                raise ASRError('transcription_source_unsupported', '转写仅支持单个非直播视频')
            if (type(duration) not in {int, float} or not math.isfinite(duration)
                    or not 0 < duration <= settings.asr_max_duration_seconds):
                raise ASRError('transcription_duration', '音频时长未知或超过转写时长上限')
            if (info.get('protocol') not in {'http', 'https'} or info.get('requested_formats')
                    or info.get('fragments') or info.get('section_start') is not None
                    or info.get('section_end') is not None
                    or get_suitable_downloader(info, opts) is not HttpFD):
                raise ASRError('transcription_source_unsupported', '此音轨协议暂不支持有限本地转写，请选择提供直连音轨的来源')
            guard({'total_bytes': info.get('filesize') or info.get('filesize_approx') or 0})
            # Download the validated selected stream without re-extracting metadata.
            ydl.process_info(info)
            downloaded = info
            guard({})
            candidates = []
            for request in (downloaded or {}).get('requested_downloads') or []:
                if request.get('filepath'):
                    candidates.append(request['filepath'])
            candidates.append(ydl.prepare_filename(downloaded))
            root = directory.resolve()
            for candidate in candidates:
                path = Path(candidate).resolve()
                if not path.is_relative_to(root):
                    raise ASRError('transcription_failed', '音频产物路径无效')
                if path.is_file():
                    if path.stat().st_size > settings.asr_max_bytes:
                        raise ASRError('transcription_too_large', '音频文件超过大小限制')
                    return path, str(info.get('title') or '视频内容')
            raise ASRError('transcription_failed', '未获取到可用音频文件')
    except ASRError:
        raise
    except (SessionError, _BilibiliSourceError) as error:
        raise ASRError(classify_error(error), public_error_message(error)) from None
    except Exception:
        raise ASRError('transcription_fetch_failed', '音频获取失败，请检查视频来源或稍后重试') from None


def download(url: str, format_id: str, outtmpl: str, progress_hook) -> str:
    # Keep separate audio/video transfers in one byte budget. This is a transfer
    # guard, not a disk quota: ffmpeg can temporarily retain inputs and output.
    stream_sizes: dict[str, int | float] = {}

    def byte_count(*values):
        return max((value for value in values if isinstance(value, (int, float))
                    and not isinstance(value, bool) and math.isfinite(value) and value >= 0), default=0)

    def bounded_progress(data):
        if data.get('status') in {'downloading', 'finished'}:
            size = byte_count(*(data.get(name) for name in ('downloaded_bytes', 'total_bytes', 'total_bytes_estimate')))
            metadata = data.get('info_dict') or {}
            stream = str(data.get('filename') or data.get('tmpfilename') or metadata.get('format_id') or 'default')
            stream_sizes[stream] = max(stream_sizes.get(stream, 0), size)
            if sum(stream_sizes.values()) > settings.max_file_size:
                raise DownloadQuotaError('文件或音视频流合计超过大小上限')
        progress_hook(data)

    opts = {
        **_network_retry_options(),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": format_id,
        "outtmpl": outtmpl,
        "progress_hooks": [bounded_progress],
        "max_filesize": settings.max_file_size,
        "merge_output_format": "mp4",
        "noprogress": True,
    }
    # ffmpeg 用于合并音视频流：默认 "ffmpeg" 表示在 PATH 上，交给 yt-dlp 自行查找；
    # 仅当显式配置了非默认路径时才传 ffmpeg_location，避免把裸名 "ffmpeg" 误当相对路径。
    if settings.ffmpeg_path and settings.ffmpeg_path != "ffmpeg":
        opts["ffmpeg_location"] = settings.ffmpeg_path
    with _source_youtube_dl(url, opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # yt-dlp may skip an oversized file without raising. Preserve the quota
        # category rather than reporting its absent output as a network failure.
        if isinstance(info, dict):
            selected = info.get('requested_formats') or [info]
            if isinstance(selected, (list, tuple)) and sum(
                byte_count(item.get('filesize'), item.get('filesize_approx'))
                for item in selected if isinstance(item, dict)
            ) > settings.max_file_size:
                raise DownloadQuotaError('文件或音视频流合计超过大小上限')
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
