"""Bounded Bilibili API metadata; no webpage extraction or yt-dlp dependency.

Only two fixed official GET endpoints are used. Media addresses are returned to
the downloader only after normalization to the official HTTPS CDN boundary.
"""
import copy
import json
import math
import re
import time
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx

from .bilibili_session import cookie_jar_for_url
from .bilibili_subtitle_source import apply_session_cookies

_MAX_BYTES = 1024 * 1024
_SOCKET_SECONDS = 8
_PHASE_SECONDS = 16
_BVID = re.compile(r'BV[A-Za-z0-9]{10}')


class BilibiliApiError(RuntimeError):
    """Only safe categories cross the source boundary, never provider material."""

    def __init__(self, category='unsupported_site'):
        self.category = category
        super().__init__('B站API来源不可用：' + category)


def video_identity(url):
    try:
        if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in url) or '\\' in url:
            raise BilibiliApiError('invalid_url')
        parsed = urlsplit(url)
        if (parsed.scheme not in {'http', 'https'} or parsed.hostname not in {'www.bilibili.com', 'bilibili.com'}
                or parsed.port not in {None, 80, 443} or parsed.username is not None
                or parsed.password is not None or parsed.fragment):
            raise BilibiliApiError('invalid_url')
        match = re.fullmatch(r'/video/(BV[A-Za-z0-9]{10}|av[1-9][0-9]{0,17})/?', parsed.path)
        parts = parse_qs(parsed.query, keep_blank_values=True).get('p', ['1'])
        if not match or len(parts) != 1 or not re.fullmatch(r'[1-9][0-9]{0,5}', parts[0]):
            raise BilibiliApiError('invalid_url')
        return match[1], int(parts[0])
    except (ValueError, TypeError):
        raise BilibiliApiError('invalid_url') from None


def safe_media_url(value):
    if not isinstance(value, str) or not value or '\\' in value or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ''
        if (parsed.scheme not in {'http', 'https'} or not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.bilivideo\.com', host)
                or parsed.port not in {None, 443} or parsed.username is not None
                or parsed.password is not None or parsed.fragment or not parsed.path.startswith('/')):
            return None
        return urlunsplit(('https', host.lower(), parsed.path, parsed.query, ''))
    except ValueError:
        return None


def _get(client, path, params):
    # A socket wait is <=8s. The 16s phase guard is checked after every streamed
    # chunk, so even a stalled last read remains bounded by one socket interval.
    deadline = time.monotonic() + _PHASE_SECONDS
    try:
        with client.stream('GET', 'https://api.bilibili.com' + path, params=params) as response:
            if response.status_code != 200:
                raise BilibiliApiError('verification_required' if response.status_code == 412 else 'network')
            if response.headers.get('Content-Encoding', '').strip().lower() not in {'', 'identity'}:
                raise BilibiliApiError('network')
            body = bytearray()
            # Do not coalesce small transport chunks: that would postpone the
            # phase guard indefinitely on a peer trickling a short response.
            for chunk in response.iter_bytes():
                if time.monotonic() > deadline or len(body) + len(chunk) > _MAX_BYTES:
                    raise BilibiliApiError('network')
                body.extend(chunk)
        payload = json.loads(body)
        if not isinstance(payload, dict) or type(payload.get('code')) is not int:
            raise BilibiliApiError()
        code = payload['code']
        if code != 0:
            category = ('verification_required' if code in {-352, -412, 401, 352, -799}
                        else 'login_required' if code in {-101, -104, -403, -2001, -600} else 'unsupported_site')
            raise BilibiliApiError(category)
        data = payload.get('data')
        if not isinstance(data, dict):
            raise BilibiliApiError()
        if data.get('v_voucher') or payload.get('v_voucher'):
            raise BilibiliApiError('verification_required')
        return data
    except BilibiliApiError:
        raise
    except (httpx.HTTPError, ValueError, TypeError, UnicodeError):
        raise BilibiliApiError('network') from None


def _positive(value):
    return type(value) is int and value > 0


def _duration(value):
    return type(value) in {int, float} and math.isfinite(value) and value > 0


def _restricted(data):
    if any(data.get(key) for key in ('is_preview', 'isPreview', 'preview', 'is_drm', 'drm_tech_type', 'drm', 'drmType')):
        raise BilibiliApiError('drm' if any(data.get(k) for k in ('is_drm', 'drm_tech_type', 'drm', 'drmType')) else 'login_required')


def _clean_stream(stream, video=False):
    if not isinstance(stream, dict):
        raise BilibiliApiError()
    _restricted(stream)
    candidates = [stream.get('baseUrl'), stream.get('base_url'), stream.get('url')]
    for key in ('backupUrl', 'backup_url'):
        backups = stream.get(key) or []
        if not isinstance(backups, list):
            raise BilibiliApiError()
        candidates.extend(backups)
    safe = next((normalized for item in candidates if (normalized := safe_media_url(item))), None)
    if not safe:
        raise BilibiliApiError()
    if not isinstance(stream.get('codecs'), str) or not stream['codecs']:
        raise BilibiliApiError()
    if video and (not _positive(stream.get('height')) or not _positive(stream.get('width'))):
        raise BilibiliApiError()
    cleaned = copy.deepcopy(stream)
    for key in ('baseUrl', 'base_url', 'url', 'backupUrl', 'backup_url'):
        cleaned.pop(key, None)
    cleaned['baseUrl'] = safe
    return cleaned


def _clean_play(play):
    _restricted(play)
    dash = play.get('dash')
    if not isinstance(dash, dict):
        raise BilibiliApiError()
    _restricted(dash)
    cleaned = {'video': [], 'audio': []}
    for kind in ('video', 'audio'):
        streams = dash.get(kind) or []
        if not isinstance(streams, list):
            raise BilibiliApiError()
        cleaned[kind] = [_clean_stream(stream, kind == 'video') for stream in streams]
    dolby, flac = dash.get('dolby') or {}, dash.get('flac') or {}
    if not isinstance(dolby, dict) or not isinstance(flac, dict):
        raise BilibiliApiError()
    _restricted(dolby)
    _restricted(flac)
    dolby_audio = dolby.get('audio') or []
    if not isinstance(dolby_audio, list):
        raise BilibiliApiError()
    cleaned['dolby'] = {'audio': [_clean_stream(stream) for stream in dolby_audio]}
    if flac.get('audio'):
        cleaned['flac'] = {'audio': _clean_stream(flac['audio'])}
    if not cleaned['video'] or not (cleaned['audio'] or cleaned['dolby']['audio'] or cleaned.get('flac')):
        raise BilibiliApiError()
    # Deliberately omit durl and advertised qualities. The converter sees only
    # actual DASH streams and cannot turn entitlement advertising into formats.
    return {'dash': cleaned, 'timelength': play.get('timelength')}


def extract_api_video(url):
    identity, part = video_identity(url)
    cookies = cookie_jar_for_url(url)
    with httpx.Client(timeout=httpx.Timeout(_SOCKET_SECONDS), trust_env=False,
                      follow_redirects=False, headers={'User-Agent': 'Mozilla/5.0',
                          'Accept-Encoding': 'identity',
                          'Referer': 'https://www.bilibili.com/'},
                      event_hooks={'request': [lambda request: apply_session_cookies(request, cookies)]}) as client:
        view = _get(client, '/x/web-interface/view',
                    {'bvid': identity} if identity.startswith('BV') else {'aid': int(identity[2:])})
        bvid, aid = view.get('bvid'), view.get('aid')
        if (not isinstance(bvid, str) or not _BVID.fullmatch(bvid) or not _positive(aid)
                or (identity.startswith('BV') and identity != bvid)
                or (identity.startswith('av') and int(identity[2:]) != aid)
                or not isinstance(view.get('title'), str) or not view['title'].strip()):
            raise BilibiliApiError()
        _restricted(view)
        if view.get('is_upower_exclusive'):
            raise BilibiliApiError('login_required')
        rights = view.get('rights') or {}
        if not isinstance(rights, dict) or any(rights.get(k) for k in ('is_pay', 'pay', 'ugc_pay', 'ugc_pay_preview')):
            raise BilibiliApiError('login_required')
        pages = view.get('pages')
        if (not isinstance(pages, list) or not pages or any(not isinstance(p, dict)
                or not _positive(p.get('page')) or not _positive(p.get('cid')) for p in pages)
                or len({p['page'] for p in pages}) != len(pages)
                or len({p['cid'] for p in pages}) != len(pages)):
            raise BilibiliApiError()
        page = next((p for p in pages if p['page'] == part), None)
        if page is None or not _duration(page.get('duration')):
            raise BilibiliApiError()
        play = _get(client, '/x/player/playurl', {'bvid': bvid, 'avid': aid, 'cid': page['cid'],
            'qn': 80, 'fnver': 0, 'fnval': 16, 'fourk': 0, 'otype': 'json'})
    for key, expected in (('bvid', bvid), ('aid', aid), ('cid', page['cid'])):
        if key in play and (type(play[key]) is not type(expected) or play[key] != expected):
            raise BilibiliApiError()
    duration = page['duration']
    if (not _duration(play.get('timelength')) or abs(play['timelength'] / 1000 - duration) > max(2, duration * .02)):
        raise BilibiliApiError()
    owner = view.get('owner') if isinstance(view.get('owner'), dict) else {}
    return {'id': bvid if part == 1 else f'{bvid}_p{part}',
        'title': view['title'] + (f" - {page['part']}" if len(pages) > 1 and part > 1 and page.get('part') else ''),
        'duration': duration, 'description': view.get('desc') if isinstance(view.get('desc'), str) else '',
        'uploader': owner.get('name'), 'uploader_id': str(owner['mid']) if _positive(owner.get('mid')) else None,
        'timestamp': view.get('pubdate') if _positive(view.get('pubdate')) else None,
        'thumbnail': view.get('pic'), 'view_count': (view.get('stat') or {}).get('view'),
        'http_headers': {'Referer': f'https://www.bilibili.com/video/{bvid}'},
        'webpage_url': f'https://www.bilibili.com/video/{bvid}?p={part}',
        '_bilibili_api': True, 'play_info': _clean_play(play)}
