import re
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import GeoRestrictedError, UnsupportedError

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
