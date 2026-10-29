import math
import os
import re
import time
import io
import sys
import stat
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.cookiejar import DefaultCookiePolicy
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse
from urllib.request import BaseHandler

import yt_dlp
from yt_dlp import globals as _ytdlp_globals
from yt_dlp.networking.common import Request, RequestDirector, RequestHandler, Response
from yt_dlp.networking.exceptions import HTTPError, RequestError
from yt_dlp.downloader import get_suitable_downloader
from yt_dlp.downloader.http import HttpFD
from yt_dlp.networking._urllib import UrllibRH, RedirectHandler
import httpx
from yt_dlp.extractor.bilibili import BiliBiliIE
from yt_dlp.utils import (
    MEDIA_EXTENSIONS, DownloadError, ExtractorError, GeoRestrictedError, UnsupportedError,
    determine_protocol, ext2mimetype, mimetype2ext, url_or_none,
)

from ..config import settings
from .subtitle_sources import InvalidVideoPartError, resolve_public_subtitles
from .asr_errors import ASRError
from .bilibili_session import SessionError, cookie_jar_for_url, is_bilibili_url, session_enabled
from .bilibili_api_source import BilibiliApiError, extract_api_video, safe_media_url, video_identity
from .outbound_httpx import ControlledResponse, ControlledHttpError, ControlledHttpStatusError, ControlledHttpBusyError
from .outbound_policy import OutboundError, OutboundPurpose, OutboundUnavailableError, validate_url
from .source_network import (SourceNetworkContext, current_source_network, make_runtime_source_network,
                             source_headers, source_network_scope)

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


def safe_bilibili_error_category(error: Exception) -> str | None:
    """Stable broker classification without inspecting/logging any exception text."""
    if isinstance(error, SessionError):
        return ERROR_NETWORK
    if not isinstance(error, (_BilibiliSourceError, BilibiliApiError)):
        return None
    allowed = {ERROR_INVALID_URL, ERROR_UNSUPPORTED, ERROR_AGE, ERROR_GEO, ERROR_DRM,
               ERROR_LOGIN, ERROR_FFMPEG, ERROR_NETWORK, ERROR_QUOTA, ERROR_VERIFICATION}
    return error.category if error.category in allowed else ERROR_NETWORK


def requires_server_download(url: str) -> bool:
    return _api_mode(url) or session_enabled(url)


def public_error_message(exc: Exception) -> str:
    """Credential contexts have already replaced upstream errors at their boundary."""
    if not isinstance(exc, SessionError) and classify_error(exc) == ERROR_VERIFICATION:
        return VERIFICATION_ERROR_MESSAGE
    return str(exc)


def _bilibili_family(url: str) -> bool:
    """Host-only check, independent of settings; malformed official URLs also match."""
    try:
        host = (urlparse(url).hostname or '').lower()
    except ValueError:
        return False
    return any(host == root or host.endswith('.' + root) for root in ('bilibili.com', 'b23.tv'))


def _unwired_under_context() -> None:
    """Paths not yet wired to an explicit source context fail closed before any I/O."""
    if current_source_network() is not None:
        raise OutboundUnavailableError() from None


@contextmanager
def _guarded_metadata_source(url: str, network: SourceNetworkContext, *, limits=None):
    """Explicit-ctx metadata factory: one guarded anonymous-GET yt-dlp instance.

    Bilibili/session/API paths are refused before any Cookie helper or legacy
    construction. Only the real default extractors are added to this instance;
    caller opts are never merged into the fixed guarded params. limits (U5b) is
    only ever a download's own _YtdlpReadLimits; metadata callers keep the default.
    """
    validate_url(url, OutboundPurpose.METADATA, network.policy)
    if _api_mode(url) or _bilibili_family(url) or is_bilibili_url(url):
        raise OutboundUnavailableError() from None
    ydl = _GuardedMetadataYoutubeDL(network, purpose=OutboundPurpose.METADATA,
                                    limits=_METADATA_LIMITS if limits is None else limits)
    state = ydl._u4_state
    pending = False
    try:
        state.call(ydl.add_default_info_extractors, request_error=False)
        state.call(lambda: _restrict_extractors(ydl), request_error=False)
        yield ydl
        state.check(request_error=False)
    except BaseException:
        pending = True
        raise
    finally:
        try:
            ydl.close()
        except Exception:
            # A caller/source error already in flight is never replaced by close failure.
            if not pending:
                state.remember_terminal(OutboundUnavailableError())
        if not pending:
            state.check(request_error=False)


@contextmanager
def _source_youtube_dl(url: str, opts: dict):
    network = current_source_network()
    if network is not None:
        with _guarded_metadata_source(url, network) as ydl:
            yield ydl
        return
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
    except (OutboundError, ControlledHttpError):
        # Safety errors keep their own type; never re-categorize them as Bilibili failures.
        raise
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
    if current_source_network() is not None and _bilibili_family(url):
        return _controlled_bilibili_projection(url)
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
        except (OutboundError, ControlledHttpError, InvalidVideoPartError, SessionError):
            raise
        except (httpx.HTTPError, ValueError) as error:
            fallback_error = error
    # Public sources above already use the controlled channel under a context;
    # the yt-dlp caption path below is not wired yet, so it fails closed there.
    _unwired_under_context()
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
    if not languages and not info.get('_bilibili_api') and current_source_network() is None:
        # Caption metadata is an optional enhancement, and must not break video parsing/download.
        # Under an explicit source context it is not wired yet, so it is skipped, not attempted.
        try:
            languages = list(dict.fromkeys(t["language"] for t in resolve_public_subtitles(url)["tracks"]))
        except (OutboundError, ControlledHttpError):
            raise
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
    return restrict_format_options(choices, format_id, max_height)


def restrict_format_options(choices: list[dict], format_id: str, max_height: int) -> str:
    """Pure entitlement binding, reusing the broker's single metadata response."""
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
    # Before the server-download early return: a ctx must not trigger (None, {}) fallback.
    _unwired_under_context()
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
    _unwired_under_context()
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
    except (OutboundError, ControlledHttpError):
        raise
    except ASRError:
        raise
    except (SessionError, _BilibiliSourceError) as error:
        raise ASRError(classify_error(error), public_error_message(error)) from None
    except Exception:
        raise ASRError('transcription_fetch_failed', '音频获取失败，请检查视频来源或稍后重试') from None


def download(url: str, format_id: str, outtmpl: str, progress_hook) -> str:
    _unwired_under_context()
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


# Explicit U4 objects only. No application factory constructs these classes.
@dataclass(frozen=True)
class _YtdlpReadLimits:
    max_bytes: int
    phase_seconds: float
    io_timeout: float
    identity_only: bool = False

    def __post_init__(self):
        valid = type(self.max_bytes) is int and self.max_bytes > 0 and type(self.identity_only) is bool
        try:
            valid = valid and all(type(value) in (int, float) and math.isfinite(value) and value > 0
                                  for value in (self.phase_seconds, self.io_timeout))
        except (OverflowError, ValueError):
            valid = False
        if not valid:
            raise ValueError('Invalid controlled yt-dlp limits') from None


class _GuardedRequestError(RequestError):
    """Terminal request sentinel; deliberately not HTTPError/TransportError."""

    def __init__(self, code: str):
        safe_codes = frozenset({
            'invalid_url', 'outbound_blocked', 'outbound_unavailable', 'source_timeout',
            'source_too_large', 'subtitle_too_large', 'source_budget_exhausted',
            'source_http_error', 'source_busy',
        })
        self.code = code if code in safe_codes else 'outbound_unavailable'
        super().__init__('Controlled source request stopped: ' + self.code)


class _YtdlpGuardState:
    """Only a fixed descriptor survives; never keep an upstream exception."""

    def __init__(self, network: SourceNetworkContext):
        if type(network) is not SourceNetworkContext:
            raise OutboundUnavailableError() from None
        self.network = network
        self._failure = None

    def remember_terminal(self, error: OutboundError | ControlledHttpError) -> None:
        if self._failure is not None:
            return
        descriptor = ('outbound', 'outbound_unavailable', 'unavailable')
        if isinstance(error, OutboundError):
            try:
                approved = OutboundError(error.code, error.reason)
                descriptor = ('outbound', approved.code, approved.reason)
            except (ValueError, AttributeError, TypeError):
                pass
        elif type(error) is ControlledHttpStatusError:
            if type(error.source_status) is int and 400 <= error.source_status <= 999:
                descriptor = ('status', error.source_status)
        elif type(error) is ControlledHttpBusyError:
            descriptor = ('busy',)
        self._failure = descriptor

    def _error(self):
        kind, *data = self._failure
        if kind == 'status':
            return ControlledHttpStatusError(data[0])
        if kind == 'busy':
            return ControlledHttpBusyError()
        return OutboundError(*data)

    def check(self, *, request_error: bool = False) -> None:
        if self._failure is None:
            try:
                self.network.check_owner()
                self.network.budget.remaining_seconds()
            except (OutboundError, ControlledHttpError) as error:
                self.remember_terminal(error)
            except Exception:
                self.remember_terminal(OutboundUnavailableError())
        if self._failure is not None:
            error = self._error()
            if request_error:
                error = _GuardedRequestError(error.code)
            # May be called by a consumer inside its own except(raw) suite.
            try:
                raise error from None
            except (OutboundError, ControlledHttpError, _GuardedRequestError):
                error.__context__ = error.__cause__ = None
                raise

    def call(self, action, *, request_error=True):
        self.check(request_error=request_error)
        ordinary_http = None
        result = None
        try:
            result = action()
        except HTTPError as error:
            ordinary_http = error
        except _GuardedRequestError:
            if self._failure is None:
                self.remember_terminal(OutboundUnavailableError())
        except (OutboundError, ControlledHttpError) as error:
            self.remember_terminal(error)
        except Exception:
            self.remember_terminal(OutboundUnavailableError())
        self.check(request_error=request_error)
        if ordinary_http is not None:
            raise ordinary_http from None
        return result


class _ControlledYtdlpResponse(Response):
    """Decoded, bounded file-like view owning one live context exchange."""

    _BUFFER_LIMIT = 64 * 1024

    def __init__(self, response: ControlledResponse, exchange, state: _YtdlpGuardState):
        self._response, self._exchange, self._state = response, exchange, state
        self._iterator, self._buffer = None, b''
        self._eof = self._released = False
        self._on_close = None
        super().__init__(io.BytesIO(), response.effective_url, {}, status=response.status_code)
        encoded = response.headers.get('content-encoding', 'identity').strip().lower() != 'identity'
        for name, value in response.header_items():
            if encoded and name.lower() in ('content-encoding', 'content-length'):
                continue
            self.headers.add_header(name, value)

    def _check(self):
        self._state.check(request_error=True)
        self._state.call(self._response.check_deadline)

    def _release(self):
        if self._released:
            return
        self._released = True
        if self._iterator is not None:
            try:
                self._iterator.close()
            except Exception:
                pass
        exchange, self._exchange = self._exchange, None
        try:
            exchange.__exit__(None, None, None)
        except Exception:
            pass

    def readable(self):
        return not self.closed

    def read(self, amt=None):
        def action():
            self._check()
            if amt is not None and (type(amt) is not int or amt < -1):
                raise OutboundUnavailableError() from None
            if self.closed:
                raise OutboundUnavailableError() from None
            if amt == 0:
                return b''
            wanted = None if amt is None or amt == -1 else amt
            parts, size = [], 0
            while wanted is None or size < wanted:
                self._check()
                if self._buffer:
                    count = len(self._buffer) if wanted is None else min(len(self._buffer), wanted - size)
                    parts.append(self._buffer[:count])
                    self._buffer = self._buffer[count:]
                    size += count
                    continue
                if self._eof:
                    break
                if self._iterator is None:
                    self._iterator = iter(self._response.iter_bytes())
                chunk = self._state.call(lambda: next(self._iterator, None))
                self._check()
                if chunk is None:
                    self._eof = True
                    self._release()
                    break
                if type(chunk) is not bytes or len(chunk) > self._BUFFER_LIMIT:
                    raise OutboundUnavailableError() from None
                self._buffer = chunk
            self._check()
            return b''.join(parts)
        try:
            return self._state.call(action)
        except _GuardedRequestError:
            self.close()
            raise

    def close(self):
        if self.closed:
            return
        self._buffer = b''
        self._release()
        callback, self._on_close = self._on_close, None
        if callback is not None:
            callback(self)
        super().close()


class _ControlledSourceRH(RequestHandler):
    _SUPPORTED_URL_SCHEMES = ('http', 'https')
    _SUPPORTED_PROXY_SCHEMES = ()
    _SUPPORTED_FEATURES = ()

    def __init__(self, *, network: SourceNetworkContext, state: _YtdlpGuardState,
                 purpose: OutboundPurpose, limits: _YtdlpReadLimits):
        super().__init__(logger=_PrivateBilibiliLogger(), headers={}, proxies={})
        self._network, self._state = network, state
        self._purpose, self._limits = purpose, limits
        self._responses = set()
        self._closed = False

    def _validate(self, request):
        def validate():
            if (self._closed or not isinstance(request, Request)
                    or request.method not in ('GET', 'HEAD') or request.data is not None or request.proxies):
                raise OutboundUnavailableError() from None
            validate_url(request.url, self._purpose, self._network.policy, initial=False)
            if set(request.extensions) - {'timeout'}:
                raise OutboundUnavailableError() from None
            if 'timeout' in request.extensions:
                value = request.extensions['timeout']
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise OutboundUnavailableError() from None
        self._state.call(validate)

    def _send(self, request):
        self._validate(request)
        opened = None
        def open_response():
            nonlocal opened
            timeout = min(self._limits.io_timeout, request.extensions.get('timeout', self._limits.io_timeout))
            exchange = self._network.exchange(request.method, request.url, purpose=self._purpose,
                headers=source_headers(dict(request.headers)), max_bytes=self._limits.max_bytes,
                phase_seconds=self._limits.phase_seconds, io_timeout=timeout,
                identity_only=self._limits.identity_only)
            response = exchange.__enter__()
            try:
                bridge = _ControlledYtdlpResponse(response, exchange, self._state)
            except Exception:
                exchange.__exit__(None, None, None)
                raise
            bridge._on_close = self._responses.discard
            self._responses.add(bridge)
            opened = bridge
            bridge._check()
            return bridge
        try:
            result = self._state.call(open_response)
        except _GuardedRequestError:
            # Ownership was established before the successful-result checks.
            # The caller never received this stream, so release it immediately.
            if opened is not None:
                opened.close()
            raise
        if result.status >= 400:
            raise HTTPError(result)
        return result

    def close(self):
        if self._closed:
            return
        self._closed = True
        for response in tuple(self._responses):
            response.close()


def _validate_derived_info(info: dict, state: _YtdlpGuardState) -> dict:
    """Pure, bounded copy of a deliberately narrow single-file fixture graph."""
    def validate():
        seen, nodes, text_bytes = set(), 0, 0

        def scan(value, depth=1):
            nonlocal nodes, text_bytes
            nodes += 1
            if depth > 8 or nodes > 256:
                raise OutboundUnavailableError() from None
            if type(value) is str:
                if len(value) > 8192:
                    raise OutboundUnavailableError() from None
                size = len(value.encode('utf-8'))
                text_bytes += size
                if size > 8192 or text_bytes > 65536:
                    raise OutboundUnavailableError() from None
                return
            if type(value) not in (dict, list) or id(value) in seen:
                raise OutboundUnavailableError() from None
            seen.add(id(value))
            if type(value) is dict:
                for key, item in value.items():
                    if type(key) is not str:
                        raise OutboundUnavailableError() from None
                    scan(key, depth + 1)
                    scan(item, depth + 1)
            else:
                for item in value:
                    scan(item, depth + 1)

        scan(info)
        if type(info) is not dict:
            raise OutboundUnavailableError() from None
        policy = state.network.policy

        def headers(value):
            if type(value) is not dict or len(value) > 32:
                raise OutboundUnavailableError() from None
            names, size, clean = set(), 0, {}
            for name, text in value.items():
                if type(name) is not str or type(text) is not str:
                    raise OutboundUnavailableError() from None
                lower = name.lower()
                size += len(name.encode('utf-8')) + len(text.encode('utf-8'))
                if (not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name)
                        or lower in names or size > 16384
                        or any(ord(char) < 32 or ord(char) == 127 for char in text)):
                    raise OutboundUnavailableError() from None
                names.add(lower)
                if lower in ('cookie', 'authorization', 'proxy-authorization'):
                    continue
                if not source_headers({name: text}):
                    raise OutboundUnavailableError() from None
                if lower == 'referer':
                    validate_url(text, OutboundPurpose.METADATA, policy, initial=False)
                clean[name] = text
            return clean

        scalars = {'id', 'title', 'ext', 'format_id'}
        extras = {'original_url', 'webpage_url', 'webpage_url_basename', 'webpage_url_domain',
                  'extractor', 'extractor_key'}

        def leaf(value, purpose, *, root=False, subtitle=False):
            allowed = {'url', 'protocol', 'http_headers'} | scalars
            if root:
                allowed |= extras | {'formats', 'subtitles', 'automatic_captions'}
            if subtitle:
                allowed.add('name')
            if type(value) is not dict or set(value) - allowed or 'url' not in value:
                raise OutboundUnavailableError() from None
            target = validate_url(value['url'], purpose, policy, initial=False)
            if ((root and 'protocol' not in value) or ('protocol' in value and (
                    value['protocol'] not in ('http', 'https') or value['protocol'] != target.scheme
                    or not value['url'].startswith(value['protocol'] + '://')))):
                raise OutboundUnavailableError() from None
            clean = {'url': value['url']}
            if 'protocol' in value:
                clean['protocol'] = value['protocol']
            for key in scalars | ({'name'} if subtitle else set()):
                if key in value:
                    if type(value[key]) is not str:
                        raise OutboundUnavailableError() from None
                    clean[key] = value[key]
            if 'http_headers' in value:
                clean['http_headers'] = headers(value['http_headers'])
            if root:
                for key in extras & value.keys():
                    if type(value[key]) is not str:
                        raise OutboundUnavailableError() from None
                    if key in ('original_url', 'webpage_url'):
                        validate_url(value[key], OutboundPurpose.METADATA, policy, initial=False)
            return clean

        clean = leaf(info, OutboundPurpose.MEDIA, root=True)
        if 'formats' in info:
            if type(info['formats']) is not list:
                raise OutboundUnavailableError() from None
            for value in info['formats']:
                leaf(value, OutboundPurpose.MEDIA)
        for key in ('subtitles', 'automatic_captions'):
            if key not in info:
                continue
            if type(info[key]) is not dict:
                raise OutboundUnavailableError() from None
            for values in info[key].values():
                if type(values) is not list:
                    raise OutboundUnavailableError() from None
                for value in values:
                    leaf(value, OutboundPurpose.SUBTITLE, subtitle=True)
        return clean
    return state.call(validate, request_error=False)


class _GuardedYoutubeDL(yt_dlp.YoutubeDL):
    """Explicit metadata-only fixture seam, not the production source factory.

    The official plugin opt-out must be set before the process's first import.
    This check cannot undo earlier plugin execution or isolate hostile Python.
    """

    def __init__(self, network: SourceNetworkContext, *, purpose: OutboundPurpose,
                 limits: _YtdlpReadLimits):
        self._u4_closed = False
        polluted = any(name == root or name.startswith(root + '.')
                       for name in sys.modules for root in ('yt_dlp_plugins', 'ytdlp_plugins'))
        if (os.environ.get('YTDLP_NO_PLUGINS') != '1' or polluted
                or _ytdlp_globals.plugin_ies.value or _ytdlp_globals.plugin_pps.value
                or _ytdlp_globals.plugin_ies_overrides.value
                or not isinstance(purpose, OutboundPurpose) or purpose is OutboundPurpose.PROVIDER
                or type(limits) is not _YtdlpReadLimits):
            raise OutboundUnavailableError() from None
        self._u4_state = _YtdlpGuardState(network)
        self._u4_state.check()
        self._u4_purpose = purpose
        self._u5_limits = limits
        self._u5_attempted = self._u5_downloading = False
        self._u5_http_status = None
        self._u5b_metadata_status = None  # U5b: last HTTP status seen while extracting (I4)
        params = dict(quiet=True, no_warnings=True, noprogress=True, logger=_PrivateBilibiliLogger(),
            cachedir=False, cookiefile=None, cookiesfrombrowser=None, js_runtimes={}, remote_components=[],
            retries=0, extractor_retries=0, fragment_retries=0, skip_download=True, noplaylist=True,
            geo_bypass=False, color='never')
        self._u4_state.call(lambda: super(_GuardedYoutubeDL, self).__init__(params, auto_init=False),
                            request_error=False)
        director = RequestDirector(logger=_PrivateBilibiliLogger())
        director.add_handler(_ControlledSourceRH(network=network, state=self._u4_state,
            purpose=purpose, limits=limits))
        self._request_director = director

    def urlopen(self, req):
        opened = None
        def open_request():
            nonlocal opened
            if self._u4_closed:
                raise OutboundUnavailableError() from None
            if isinstance(req, str):
                url = req
            elif isinstance(req, Request):
                url = req.url
            elif hasattr(req, 'get_full_url') and type(req).__module__ == 'urllib.request':
                url = req.get_full_url()
            else:
                raise OutboundUnavailableError() from None
            validate_url(url, self._u4_purpose, self._u4_state.network.policy, initial=False)
            ordinary_http = None
            try:
                opened = super(_GuardedYoutubeDL, self).urlopen(req)
            except HTTPError as error:
                opened, ordinary_http = error.response, error
                if self._u5_downloading:
                    # HttpFD handles 416 with one further GET; a recovered 416
                    # must not reclassify a subsequent unknown file failure.
                    self._u5_http_status = error.status if error.status != 416 else None
                else:
                    self._u5b_metadata_status = error.status
            # The scope is tighter than the operation and can also expire in
            # the outer window, after the director returned or raised HTTPError.
            opened._check()
            if ordinary_http is not None:
                raise ordinary_http from None
            return opened
        try:
            return self._u4_state.call(open_request)
        except _GuardedRequestError:
            if opened is not None:
                opened.close()
            self._stop_owned_responses()
            raise

    def _u5b_enter_download(self, limits: '_YtdlpReadLimits') -> None:
        """U5b: extraction is over. Close its leftover responses (a Generic direct-media probe is
        left unread) and apply the download's own limits for the HttpFD phase only."""
        if (self._u5_attempted or self._u5_downloading or self._u4_closed
                or type(limits) is not _YtdlpReadLimits or limits.identity_only is not True):
            raise OutboundUnavailableError() from None
        for handler in self._request_director.handlers.values():
            for response in tuple(handler._responses):
                response.close()
            handler._limits = limits
        self._u5_limits = limits

    def _stop_owned_responses(self):
        director = self.__dict__.get('_request_director')
        if director is not None:
            for handler in director.handlers.values():
                handler.close()

    def extract_info(self, url, download=False, ie_key=None, extra_info=None,
                     process=False, force_generic_extractor=False):
        def extract():
            if download is not False or process is not False or self._u4_closed:
                raise OutboundUnavailableError() from None
            validate_url(url, self._u4_purpose, self._u4_state.network.policy)
            return super(_GuardedYoutubeDL, self).extract_info(url, download=False, ie_key=ie_key,
                extra_info=extra_info, process=False, force_generic_extractor=force_generic_extractor)
        try:
            return self._u4_state.call(extract, request_error=False)
        except (OutboundError, ControlledHttpError):
            self._stop_owned_responses()
            raise

    def process_info(self, info_dict):
        self._u4_state.remember_terminal(OutboundUnavailableError())
        self._stop_owned_responses()
        self._u4_state.check()

    @contextmanager
    def _download_http_file(self, info: dict, *, target_dir: Path) -> Iterator[Path]:
        """One native HttpFD attempt in a trusted caller-owned empty directory.

        Instance-local observers record actual opened handles and inode identity.
        They cannot establish ownership when an upstream open fails before return;
        such unknown files are preserved. This is not hostile-writer isolation.
        """
        state = self._u4_state
        files, streams, ancestors = {}, [], []
        final = partial = None

        def identity(path, *, directory=False):
            saved = path.lstat()
            if (stat.S_ISLNK(saved.st_mode) or getattr(saved, 'st_file_attributes', 0) & 1024
                    or not (stat.S_ISDIR(saved.st_mode) if directory else stat.S_ISREG(saved.st_mode))
                    or not saved.st_ino):
                raise OutboundUnavailableError() from None
            return saved.st_dev, saved.st_ino

        def check_directory():
            for path, expected in ancestors:
                if identity(path, directory=True) != expected:
                    raise OutboundUnavailableError() from None

        def stop_responses():
            failed = False
            director = self.__dict__.get('_request_director')
            if director is not None:
                for handler in director.handlers.values():
                    # One failed close must not skip other responses (e.g. the
                    # 416 bridge followed by HttpFD's second GET response).
                    for response in tuple(handler._responses):
                        try:
                            response.close()
                        except Exception:
                            failed = True
                    try:
                        handler.close()
                    except Exception:
                        failed = True
            return failed

        def download():
            nonlocal final, partial
            attempted, self._u5_attempted = self._u5_attempted, True
            if attempted or self._u4_closed or self._u5_limits.identity_only is not True:
                raise OutboundUnavailableError() from None
            clean = _validate_derived_info(info, state)
            if (not isinstance(target_dir, Path) or not target_dir.is_absolute()
                    or target_dir != target_dir.resolve(strict=True)):
                raise OutboundUnavailableError() from None
            for path in (target_dir, *target_dir.parents):
                ancestors.append((path, identity(path, directory=True)))
            if any(target_dir.iterdir()):
                raise OutboundUnavailableError() from None
            final, partial = target_dir / 'media.bin', target_dir / 'media.bin.part'
            params = dict(quiet=True, no_warnings=True, noprogress=True,
                retries=0, fragment_retries=0, file_access_retries=0, continuedl=False,
                nopart=False, overwrites=False, http_chunk_size=0, buffersize=65536,
                noresizebuffer=True, test=False, updatetime=False, xattr_set_filesize=False,
                external_downloader='native', concurrent_fragment_downloads=1)
            if get_suitable_downloader(dict(clean), params) is not HttpFD:
                raise OutboundUnavailableError() from None
            fd = HttpFD(self, params)
            real_open, real_rename = fd.sanitize_open, fd.try_rename

            def observe_open(filename, mode):
                check_directory()
                if filename != str(partial) or mode != 'wb' or partial.exists() or final.exists():
                    raise OutboundUnavailableError() from None
                stream, name = real_open(filename, mode)
                # Keep the handle before any recognition that itself may fail.
                streams.append(stream)
                opened = os.fstat(stream.fileno())
                if (name != str(partial) or not stat.S_ISREG(opened.st_mode)
                        or identity(partial) != (opened.st_dev, opened.st_ino)):
                    raise OutboundUnavailableError() from None
                files[partial] = (opened.st_dev, opened.st_ino)
                return stream, name

            def observe_rename(old, new):
                check_directory()
                if (old != str(partial) or new != str(final) or final.exists()
                        or partial not in files or identity(partial) != files[partial]):
                    raise OutboundUnavailableError() from None
                # Record the same inode at both possible names before rename.
                # If an upstream wrapper renames and then raises, cleanup still
                # verifies identity instead of guessing from a filename.
                files[final] = files[partial]
                result = real_rename(old, new)
                if identity(final) != files[final]:
                    raise OutboundUnavailableError() from None
                return result

            fd.sanitize_open, fd.try_rename = observe_open, observe_rename
            self._u5_downloading = True
            ordinary_status = None
            result = None
            try:
                result = fd.download(str(final), clean, subtitle=False)
            except HTTPError as error:
                ordinary_status = error.status
            except (OutboundError, ControlledHttpError, _GuardedRequestError):
                raise
            except Exception:
                ordinary_status = self._u5_http_status
                if ordinary_status is None:
                    state.remember_terminal(OutboundUnavailableError())
            finally:
                self._u5_downloading = False
            # Rebuild only after leaving the upstream except suite.
            state.check(request_error=False)
            if ordinary_status is not None:
                raise ControlledHttpStatusError(ordinary_status) from None
            if not (type(result) is tuple and len(result) == 2
                    and result[0] is True and result[1] is True):
                if self._u5_http_status is not None:
                    raise ControlledHttpStatusError(self._u5_http_status) from None
                raise OutboundUnavailableError() from None
            # HttpFD may stop exactly at Content-Length without reading EOF.
            # The original response phase must still be healthy at acceptance.
            for handler in self._request_director.handlers.values():
                for response in tuple(handler._responses):
                    response._check()
            check_directory()
            if (final not in files or identity(final) != files[final]
                    or not 0 < final.lstat().st_size <= self._u5_limits.max_bytes):
                raise OutboundUnavailableError() from None
            return final

        try:
            try:
                path = state.call(download, request_error=False)
            finally:
                pending = sys.exc_info()[0] is not None
                if stop_responses() and not pending:
                    state.remember_terminal(OutboundUnavailableError())
                    state.check(request_error=False)
            # Caller exceptions are outside the source error conversion boundary.
            yield path
        finally:
            pending = sys.exc_info()[0] is not None
            failed = False
            for stream in streams:
                try:
                    stream.close()
                except Exception:
                    failed = True
            if stop_responses():
                failed = True
            for path, expected in files.items():
                try:
                    check_directory()
                    try:
                        actual = identity(path)
                    except FileNotFoundError:
                        continue
                    if actual != expected:
                        failed = True
                        continue
                    path.unlink()
                except Exception:
                    failed = True
            if failed and not pending:
                state.remember_terminal(OutboundUnavailableError())
                state.check(request_error=False)

    def dl(self, name, info, subtitle=False, test=False):
        self._u4_state.remember_terminal(OutboundUnavailableError())
        self._stop_owned_responses()
        self._u4_state.check()

    def close(self):
        if getattr(self, '_u4_closed', True):
            return
        self._u4_closed = True
        if '_request_director' in self.__dict__:
            self._request_director.close()
            del self._request_director


# B5 W1: explicit-ctx metadata limits (only tighten the context's own budget/group).
# Only extractors proven on the guarded anonymous-GET path may join the instance;
# others can start PhantomJS outside the director or add request handlers.
_METADATA_EXTRACTORS = frozenset({'Generic'})
_MANIFEST_SUFFIXES = ('.m3u8', '.m3u', '.f4m', '.mpd', '.ism', '.ism/manifest', '.isml/manifest')
_METADATA_LIMITS = _YtdlpReadLimits(max_bytes=1024 * 1024, phase_seconds=16, io_timeout=8, identity_only=True)
_SOURCE_TEXT_KEYS = ('id', 'title', 'description', 'uploader', 'channel', 'extractor', 'extractor_key',
                     'upload_date', 'ext', 'format_id', 'vcodec', 'acodec')
_SOURCE_NUMBER_KEYS = ('duration', 'view_count', 'timestamp', 'height', 'width', 'filesize', 'filesize_approx')
_FORMAT_TEXT_KEYS = ('format_id', 'ext', 'vcodec', 'acodec', 'format_note')
_FORMAT_NUMBER_KEYS = ('height', 'width', 'filesize', 'filesize_approx')
_SUBTITLE_TEXT_KEYS = ('ext', 'name')
_SOURCE_ROOT_KEYS = frozenset((*_SOURCE_TEXT_KEYS, *_SOURCE_NUMBER_KEYS, 'url', 'protocol', 'http_headers',
    'formats', 'subtitles', 'automatic_captions', 'thumbnail', 'original_url', 'webpage_url',
    'webpage_url_basename', 'webpage_url_domain', 'direct', 'hls_aes', '_type', 'is_live', 'live_status'))


def _validate_source_metadata(info: dict, state: _YtdlpGuardState) -> dict:
    """Bounded, pure projection of extractor metadata into a new independent dict.

    Separate from U5a's single-file validator. Every derived URL is checked
    against the context policy for its purpose; nothing here sends a request.
    Unknown keys, playlists, live, manifests/fragments and execution controls
    are refused rather than dropped.
    """
    def unavailable():
        raise OutboundUnavailableError() from None

    def validate():
        seen, nodes, text_bytes = set(), 0, 0

        def scan(value, depth=1):
            nonlocal nodes, text_bytes
            nodes += 1
            if depth > 8 or nodes > 256:
                unavailable()
            kind = type(value)
            if kind is str:
                if len(value) > 8192:
                    unavailable()
                size = len(value.encode('utf-8'))
                text_bytes += size
                if size > 8192 or text_bytes > 65536:
                    unavailable()
            elif kind is float:
                if not math.isfinite(value):
                    unavailable()
            elif kind in (int, bool) or value is None:
                return
            elif kind in (dict, list):
                if id(value) in seen:
                    unavailable()
                seen.add(id(value))
                if kind is dict:
                    for key, item in value.items():
                        if type(key) is not str:
                            unavailable()
                        scan(key, depth + 1)
                        scan(item, depth + 1)
                else:
                    for item in value:
                        scan(item, depth + 1)
            else:
                unavailable()

        scan(info)
        if type(info) is not dict or set(info) - _SOURCE_ROOT_KEYS:
            unavailable()
        policy = state.network.policy

        def text(value):
            if value is not None and type(value) is not str:
                unavailable()
            return value

        def number(value):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                unavailable()
            return value

        def headers(value):
            if type(value) is not dict or len(value) > 32:
                unavailable()
            names, size, clean = set(), 0, {}
            for name, item in value.items():
                if type(name) is not str or type(item) is not str:
                    unavailable()
                lower = name.lower()
                size += len(name.encode('utf-8')) + len(item.encode('utf-8'))
                if (not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or lower in names or size > 16384
                        or any(ord(char) < 32 or ord(char) == 127 for char in item)):
                    unavailable()
                names.add(lower)
                if lower in ('cookie', 'authorization', 'proxy-authorization'):
                    continue
                if not source_headers({name: item}):
                    unavailable()
                if lower == 'referer':
                    validate_url(item, OutboundPurpose.METADATA, policy, initial=False)
                clean[name] = item
            return clean

        def url_leaf(value, purpose, text_keys=(), number_keys=()):
            allowed = {'url', 'protocol', 'http_headers', *text_keys, *number_keys}
            if type(value) is not dict or set(value) - allowed or type(value.get('url')) is not str:
                unavailable()
            target = validate_url(value['url'], purpose, policy, initial=False)
            # Derive like yt-dlp would, so an unlabeled manifest is never treated as a plain file.
            derived = determine_protocol({'url': value['url']})
            protocol = value.get('protocol', derived)
            if (target.scheme not in ('http', 'https') or protocol != target.scheme or derived != target.scheme
                    or not value['url'].startswith(protocol + '://')
                    or urlparse(value['url']).path.lower().endswith(_MANIFEST_SUFFIXES)):
                unavailable()
            clean = {'url': value['url'], 'protocol': protocol}
            for key in text_keys:
                if key in value:
                    clean[key] = text(value[key])
            for key in number_keys:
                if key in value:
                    clean[key] = number(value[key])
            if value.get('http_headers') is not None:
                clean['http_headers'] = headers(value['http_headers'])
            return clean

        # Locked yt-dlp conventions that may be present; validated, then dropped.
        if info.get('_type', 'video') != 'video' or info.get('is_live', False) is not False:
            unavailable()
        if info.get('live_status') not in (None, 'not_live'):
            unavailable()
        if ('direct' in info and type(info['direct']) is not bool) or info.get('hls_aes') is not None:
            unavailable()
        for key in ('webpage_url_basename', 'webpage_url_domain'):
            text(info.get(key))
        clean = {}
        for key in _SOURCE_TEXT_KEYS:
            if key in info:
                clean[key] = text(info[key])
        for key in _SOURCE_NUMBER_KEYS:
            if key in info:
                clean[key] = number(info[key])
        for key in ('thumbnail', 'original_url', 'webpage_url'):
            if key in info:
                if info[key] is not None:
                    if type(info[key]) is not str:
                        unavailable()
                    validate_url(info[key], OutboundPurpose.METADATA, policy, initial=False)
                clean[key] = info[key]
        if 'url' in info:
            clean.update(url_leaf({key: info[key] for key in ('url', 'protocol', 'http_headers') if key in info},
                                  OutboundPurpose.MEDIA))
        elif 'protocol' in info:
            unavailable()
        elif info.get('http_headers') is not None:
            clean['http_headers'] = headers(info['http_headers'])
        if 'formats' in info:
            if info['formats'] is not None and type(info['formats']) is not list:
                unavailable()
            for item in info['formats'] or []:
                # Unprocessed results never get yt-dlp's filled-in format_id; consumers index it.
                if type(item) is not dict or type(item.get('format_id')) is not str or not item['format_id']:
                    unavailable()
            clean['formats'] = None if info['formats'] is None else [
                url_leaf(item, OutboundPurpose.MEDIA, _FORMAT_TEXT_KEYS, _FORMAT_NUMBER_KEYS)
                for item in info['formats']]
        for key in ('subtitles', 'automatic_captions'):
            if key not in info:
                continue
            tracks = info[key]
            if tracks is None:
                clean[key] = None
                continue
            if type(tracks) is not dict:
                unavailable()
            clean[key] = {}
            for language, items in tracks.items():
                if type(items) is not list:
                    unavailable()
                clean[key][language] = [url_leaf(item, OutboundPurpose.SUBTITLE, _SUBTITLE_TEXT_KEYS)
                                        for item in items]
        return clean
    return state.call(validate, request_error=False)


def _restrict_extractors(ydl) -> None:
    for key in [key for key in ydl._ies if key not in _METADATA_EXTRACTORS]:
        del ydl._ies[key]
        ydl._ies_instances.pop(key, None)
    if set(ydl._ies) != set(_METADATA_EXTRACTORS):
        raise OutboundUnavailableError() from None


class _GuardedMetadataYoutubeDL(_GuardedYoutubeDL):
    """Explicit-ctx metadata instance: extract_info returns only the bounded projection."""

    def get_info_extractor(self, ie_key):
        # Extractors may look up other IEs by key; never instantiate one outside the allowlist.
        if ie_key not in _METADATA_EXTRACTORS:
            raise OutboundUnavailableError() from None
        return super().get_info_extractor(ie_key)

    def extract_info(self, url, download=False, ie_key=None, extra_info=None,
                     process=False, force_generic_extractor=False):
        result = super().extract_info(url, download=download, ie_key=ie_key, extra_info=extra_info,
                                      process=process, force_generic_extractor=force_generic_extractor)
        try:
            return _validate_source_metadata(result, self._u4_state)
        except (OutboundError, ControlledHttpError):
            self._stop_owned_responses()
            raise


# U5b: one controlled single-file download for the C3 worker's 'ytdlp' executor.
# Media containers a download may produce (seal_candidate's ext); anything else is unavailable.
DOWNLOAD_EXTS = frozenset({'mp4', 'webm', 'mkv', 'mov', 'flv', 'm4a', 'mp3', 'ogg', 'opus', 'aac', 'wav'})
_DOWNLOAD_PHASE_SECONDS = 1800.0  # never beyond the absolute 30-minute run window
# The three format-id shapes the product stores (get_direct_url/download routes, restrict_format).
_PLAIN_FORMAT = re.compile(r'[A-Za-z0-9_.-]{1,64}\Z')
_ID_HEIGHT_FORMAT = re.compile(r'([A-Za-z0-9_.-]{1,64})\[height<=([0-9]{1,5})\]\Z')
_BEST_HEIGHT_FORMAT = re.compile(r'bestvideo\[height<=([0-9]{1,5})\]\+bestaudio/best\[height<=([0-9]{1,5})\]\Z')
_DOWNLOAD_HEADERS = frozenset({'user-agent', 'referer', 'accept', 'accept-language'})


class DownloadFormatUnsupported(Exception):
    """No single file matches the stored format id here (fixed, no text): never guess another."""


def _parse_download_format(format_id) -> tuple[str | None, int | None]:
    """(exact leaf id or None for the default choice, max height or None); unsupported raises."""
    if type(format_id) is not str:
        raise DownloadFormatUnsupported()
    if format_id in ('', 'best'):
        return None, None
    match = _BEST_HEIGHT_FORMAT.match(format_id)
    if match and match.group(1) == match.group(2):
        return None, int(match.group(1))  # the merge half is never available here: best single file
    match = _ID_HEIGHT_FORMAT.match(format_id)
    if match:
        return (None if match.group(1) == 'best' else match.group(1)), int(match.group(2))
    if _PLAIN_FORMAT.match(format_id) and format_id != 'best':
        return format_id, None
    raise DownloadFormatUnsupported()


@dataclass(frozen=True, slots=True)
class DownloadedFile:
    path: Path = field(repr=False)
    ext: str


def _select_download(projection: dict, format_id: str) -> dict:
    """Pick one single-file leaf of the bounded projection; returns a new minimal U5a info dict.

    Unprocessed formats are in extractor order (yt-dlp sorts only when processing), so no order
    is assumed. An exact id must match one leaf; otherwise a lone leaf (direct media, also
    audio- or video-only) is taken, else the best-ranked complete leaf by height, then size.
    A height limit excludes leaves of unknown height (membership limits fail closed). Merges,
    unknown containers and ambiguous ids raise DownloadFormatUnsupported; a Bilibili target is
    OutboundUnavailableError (safety). Nothing is sent here.
    """
    exact, max_height = _parse_download_format(format_id)
    leaves = list(projection.get('formats') or ([projection] if 'url' in projection else []))
    if max_height is not None:
        leaves = [item for item in leaves if type(item.get('height')) is int and item['height'] <= max_height]
    if exact is not None:
        matches = [item for item in leaves if item.get('format_id') == exact]
        chosen = matches[0] if len(matches) == 1 else None
    elif len(leaves) == 1:
        chosen = leaves[0]
    else:
        complete = [(index, item) for index, item in enumerate(leaves)
                    if item.get('vcodec') != 'none' and item.get('acodec') != 'none']

        def rank(entry):
            index, item = entry
            size = item.get('filesize') or item.get('filesize_approx') or -1
            return (item.get('height') if type(item.get('height')) is int else -1, size, index)
        chosen = max(complete, key=rank)[1] if complete else None
    # Safety first: a Bilibili target is refused whatever its container (never "no direct link").
    if chosen is not None and (_bilibili_family(chosen['url']) or is_bilibili_url(chosen['url'])):
        raise OutboundUnavailableError() from None
    ext = None if chosen is None else (chosen.get('ext') or projection.get('ext'))
    if chosen is None or type(ext) is not str or ext not in DOWNLOAD_EXTS:
        raise DownloadFormatUnsupported()  # no matching single file: a business outcome, not a safety one
    minimal = {'url': chosen['url'], 'protocol': chosen['protocol'], 'ext': ext}
    if chosen.get('format_id') is not None:
        minimal['format_id'] = chosen['format_id']
    # Only plain request headers reach HttpFD (never Range/If-* that could yield partial content).
    merged = {}
    for source in (projection.get('http_headers') or {}, chosen.get('http_headers') or {}):
        for name, value in source.items():
            if name.lower() in _DOWNLOAD_HEADERS:
                merged[name.lower()] = (name, value)  # one value per header name; the leaf wins
    headers = dict(merged.values())
    if headers:
        minimal['http_headers'] = headers
    for key in ('id', 'title'):
        if type(projection.get(key)) is str:
            minimal[key] = projection[key]
    return minimal


def _extract_projection(ydl, url: str) -> dict:
    """Guarded extraction; an HTTP failure keeps its status class (a transient 503 stays retryable)."""
    status = None
    try:
        return ydl.extract_info(url, download=False)
    except OutboundError as error:
        status = ydl._u5b_metadata_status
        if error.code != 'outbound_unavailable' or status is None or not 400 <= status <= 999:
            raise
    # Raised outside the except suite so the safe error carries no context.
    raise ControlledHttpStatusError(status) from None


def resolve_direct(url: str, format_id: str, *, network: SourceNetworkContext) -> tuple[str, dict] | None:
    """U6: the selected single file's URL and plain headers for a browser download, or None.

    Metadata only (one guarded extraction, Generic extractor); the media itself is never
    requested. None means no single file matches the stored format id (the caller may fall
    back to a server download); every safety, policy, budget or HTTP failure is raised.
    """
    try:
        _parse_download_format(format_id)
    except DownloadFormatUnsupported:
        return None
    with _guarded_metadata_source(url, network) as ydl:
        try:
            selected = _select_download(_extract_projection(ydl, url), format_id)
        except DownloadFormatUnsupported:
            return None
    return selected['url'], dict(selected.get('http_headers') or {})


@contextmanager
def download_attempt(url: str, format_id: str, *, scratch_dir: Path, max_bytes: int, deadline_seconds: float,
                     network: SourceNetworkContext | None = None, progress_hook=None) -> Iterator[DownloadedFile]:
    """Controlled Bilibili API/DASH, or guarded Generic metadata -> native HttpFD.

    The file is scratch_dir/media.bin inside the with block; the caller links it elsewhere before
    leaving (the U5a seam removes its own files on exit). Only yt-dlp's Generic extractor is
    allowed: direct media and pages embedding it; a redirecting source page is unavailable
    (Generic returns a url result). An unsupported stored format id raises
    DownloadFormatUnsupported before any I/O. Without an explicit network the current scope
    is used, else the runtime factory, which stays closed (OutboundUnavailableError) until the
    environmental gate is verified. Errors are the fixed U4/U5a safe types; no fallback or retry.
    Bilibili instead uses two fixed official API GETs, two bounded HTTPS CDN
    files and a local-only ffmpeg merger; its stored selector still binds height.
    """
    _parse_download_format(format_id)  # an unsupported stored id fails before any I/O
    if type(deadline_seconds) not in (int, float) or not math.isfinite(deadline_seconds) or deadline_seconds <= 0:
        raise ValueError('Invalid download deadline') from None
    limits = _YtdlpReadLimits(max_bytes=max_bytes, phase_seconds=min(deadline_seconds, _DOWNLOAD_PHASE_SECONDS),
                              io_timeout=_METADATA_LIMITS.io_timeout, identity_only=True)
    if network is None:
        network = current_source_network() or make_runtime_source_network()
    if _bilibili_family(url):
        with _download_bilibili_attempt(url, format_id, scratch_dir=scratch_dir,
                max_bytes=max_bytes, deadline_seconds=deadline_seconds, network=network,
                progress_hook=progress_hook) as downloaded:
            yield downloaded
        return
    # Extraction keeps the tight metadata limits; only the HttpFD phase gets the attempt's limits.
    with _guarded_metadata_source(url, network) as ydl:
        selected = _select_download(_extract_projection(ydl, url), format_id)
        ydl._u5b_enter_download(limits)
        with ydl._download_http_file(selected, target_dir=scratch_dir) as path:
            yield DownloadedFile(path, selected['ext'])


def _controlled_bilibili_projection(url: str, *, deadline=None) -> dict:
    """Only the fixed official API adapter; no YoutubeDL/extractor construction or fallback."""
    try:
        info = extract_api_video(url, deadline=deadline)
    except BilibiliApiError as error:
        raise _BilibiliSourceError(error.category) from None
    play = info.pop('play_info', None)
    if not isinstance(play, dict) or not isinstance(play.get('dash'), dict):
        # Progressive advertising does not establish a verified stream height.
        # The controlled adapter accepts DASH only and never guesses entitlement.
        raise _BilibiliSourceError(ERROR_UNSUPPORTED) from None
    formats = []
    for kind in ('video', 'audio'):
        # The ordinary AAC track is sufficient for the local MP4 merger. Optional
        # Dolby/FLAC tracks do not trigger probes or any alternate network path.
        for stream in play['dash'][kind]:
            codec = stream.get('codecs', '')
            formats.append({'format_id': str(stream.get('id', '')), 'url': stream['baseUrl'],
                'protocol': 'https', 'ext': 'mp4' if kind == 'video' else 'm4a',
                'height': stream.get('height') if kind == 'video' else None,
                'width': stream.get('width') if kind == 'video' else None,
                'vcodec': codec if kind == 'video' else 'none',
                'acodec': codec if kind == 'audio' else 'none',
                'tbr': stream.get('bandwidth') if type(stream.get('bandwidth')) is int else 0})
    info.update(formats=formats, extractor='BiliBili', extractor_key='BiliBili')
    return info


def _merge_bilibili_files(video: Path, audio: Path, output: Path, *, max_bytes: int, deadline: float):
    """Fixed local files, demuxers and protocols only; no provider data enters ffmpeg argv."""
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        raise OutboundUnavailableError() from None
    command = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-n']
    for path in (video, audio):
        command += ['-protocol_whitelist', 'file', '-format_whitelist', 'mov',
                    '-f', 'mov', '-enable_drefs', '0', '-use_absolute_path', '0', '-i', str(path.resolve())]
    command += ['-map', '0:v:0', '-map', '1:a:0', '-c', 'copy', '-f', 'mp4',
                '-fs', str(max_bytes + 1), str(output.resolve())]
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        while child.poll() is None:
            if time.monotonic() >= deadline:
                raise OutboundError('source_timeout', 'deadline') from None
            if output.exists() and output.stat().st_size > max_bytes:
                raise OutboundError('source_too_large', 'response_raw_bytes') from None
            time.sleep(min(.05, max(.001, deadline - time.monotonic())))
        if child.returncode != 0 or not output.is_file():
            raise OutboundUnavailableError() from None
        if output.stat().st_size > max_bytes:
            raise OutboundError('source_too_large', 'response_raw_bytes') from None
        if time.monotonic() >= deadline:
            raise OutboundError('source_timeout', 'deadline') from None
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


@contextmanager
def _download_bilibili_attempt(url, format_id, *, scratch_dir, max_bytes, deadline_seconds, network,
                               progress_hook):
    deadline = time.monotonic() + deadline_seconds
    try:
        directory = scratch_dir.lstat()
    except OSError:
        raise OutboundUnavailableError() from None
    if not stat.S_ISDIR(directory.st_mode) or scratch_dir.is_symlink():
        raise OutboundUnavailableError() from None
    exact, height = _parse_download_format(format_id)
    video, audio, output = (scratch_dir / name for name in ('video.bin', 'audio.bin', 'media.bin'))
    owned = []
    total = 0
    try:
        with source_network_scope(network):
            try:
                info = _controlled_bilibili_projection(url, deadline=deadline)
            except _BilibiliSourceError:
                raise OutboundUnavailableError() from None
        videos = [f for f in info['formats'] if f['vcodec'] != 'none'
                  and (height is None or type(f['height']) is int and f['height'] <= height)
                  and (exact is None or f['format_id'] == exact)]
        audios = [f for f in info['formats'] if f['acodec'].lower().startswith('mp4a')]
        if not videos or not audios:
            raise DownloadFormatUnsupported()
        streams = (max(videos, key=lambda f: (f['height'], f['vcodec'].startswith('avc'), f['tbr'])),
                   max(audios, key=lambda f: f['tbr']))
        for stream, path in zip(streams, (video, audio)):
            target = stream['url']
            if safe_media_url(target) != target:
                raise OutboundUnavailableError() from None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OutboundError('source_timeout', 'deadline') from None
            if total >= max_bytes:
                raise OutboundError('source_too_large', 'raw_bytes') from None
            with path.open('xb') as handle:
                owned.append(path)
                with network.stream(target, purpose=OutboundPurpose.MEDIA,
                        headers={'Referer': info['http_headers']['Referer'], 'User-Agent': 'Mozilla/5.0'},
                        follow_redirects=False, max_bytes=max_bytes-total,
                        phase_seconds=remaining, io_timeout=min(8, remaining), identity_only=True) as response:
                    response.raise_for_status()
                    if response.status_code != 200 or response.headers.get('Content-Encoding', '').lower().strip() not in {'', 'identity'}:
                        raise OutboundUnavailableError() from None
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if progress_hook is not None:
                            progress_hook(total)  # before disk write/cleanup, including failed attempts
                        if total > max_bytes:
                            raise OutboundError('source_too_large', 'raw_bytes') from None
                        handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        if output.exists() or output.is_symlink():
            raise OutboundUnavailableError() from None
        owned.append(output)
        _merge_bilibili_files(video, audio, output, max_bytes=max_bytes, deadline=deadline)
        if not output.is_file() or output.stat().st_size > max_bytes:
            raise OutboundError('source_too_large', 'raw_bytes') from None
        yield DownloadedFile(output, 'mp4')
    finally:
        if progress_hook is not None:
            progress_hook(total)
        for path in reversed(owned):
            path.unlink(missing_ok=True)
