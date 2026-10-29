"""Bounded UNIX metadata RPC. The API never opens a source network context.

Only the broker reads the operator cookie file. Its isolated child receives a
bounded in-memory snapshot on private stdin; neither RPC nor argv carries it.
"""
from __future__ import annotations

import errno
from functools import partial
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import stat
import struct
import subprocess
import sys
import time

from . import child_isolation
from .outbound_policy import OutboundError, OutboundPurpose, validate_url

MAX_REQUEST = 64 * 1024
MAX_RESPONSE = 512 * 1024
MAX_SUBTITLE_RESPONSE = 8 * 1024 * 1024
CHILD_SECONDS = 45
RPC_SECONDS = 55
_BACKEND = Path(__file__).resolve().parents[2]
_ERRORS = {
    'outbound_unavailable': (503, '安全访问通道暂不可用'),
    'format_unverified': (422, '无法确认视频清晰度，请重新解析'),
    'membership_required': (403, '此功能需要 VIP 会员'),
    'invalid_url': (400, '链接格式无效'),
    'outbound_blocked': (422, '来源地址不符合安全策略'),
    'source_timeout': (504, '来源处理超时'),
    'source_too_large': (422, '来源内容超过大小限制'),
    'subtitle_too_large': (422, '字幕内容超过大小限制'),
    'source_budget_exhausted': (422, '来源处理预算已耗尽'),
    'source_http_error': (502, '来源返回失败状态'),
    'source_busy': (503, '来源处理繁忙'),
    'subtitle_unavailable': (422, '该视频没有可用字幕或请求的字幕语言'),
    'subtitle_invalid': (422, '字幕内容格式无效'),
    'verification_required': (422, '来源需要安全验证，请管理员更新会话'),
    'unsupported_site': (422, '暂不支持该站点视频'),
    'age_restricted': (422, '视频存在年龄限制'),
    'geo_blocked': (422, '视频存在地区限制'),
    'drm': (422, '视频受版权保护'),
    'login_required': (422, '来源需要登录'),
    'ffmpeg_missing': (422, '服务器音视频合并工具不可用'),
    'network': (422, '来源网络访问失败'),
    'quota': (422, '来源文件超过大小限制'),
}


class SourceBrokerError(OutboundError):
    """Fixed public error contract; never retain a child exception or payload."""

    def __init__(self, code='outbound_unavailable'):
        if code not in _ERRORS:
            code = 'outbound_unavailable'
        self.code = code
        self.reason = 'unavailable'
        self.status_code, self.message = _ERRORS[code]
        Exception.__init__(self, self.message)
        self.__suppress_context__ = True

    def public_detail(self):
        return {'error_type': self.code, 'error': self.message}


def error_response(code='outbound_unavailable'):
    error = SourceBrokerError(code)
    return {'version': 1, 'ok': False, 'code': error.code, 'status': error.status_code}


def validate_request(value):
    if type(value) is not dict or type(value.get('version')) is not int or value['version'] != 1:
        raise SourceBrokerError()
    op = value.get('op')
    fields = {'ping': {'version', 'op'}, 'parse': {'version', 'op', 'url'},
              'subtitle': {'version', 'op', 'url', 'language'},
              'verify': {'version', 'op', 'url', 'format_id', 'max_height'}}
    if type(op) is not str or op not in fields or set(value) != fields[op]:
        raise SourceBrokerError()
    result = dict(value)
    if op != 'ping':
        try:
            result['url'] = validate_url(value['url'], OutboundPurpose.METADATA).url
        except OutboundError as error:
            raise SourceBrokerError(error.code) from None
    if op == 'verify':
        choice, height = value['format_id'], value['max_height']
        if (type(choice) is not str or not choice or len(choice.encode('utf8')) > 1024
                or any(ord(c) < 32 or ord(c) == 127 for c in choice)
                or (height is not None and (type(height) is not int or not 1 <= height <= 16384))):
            raise SourceBrokerError('format_unverified')
    if op == 'subtitle':
        language = value['language']
        if language is not None and (type(language) is not str or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', language)):
            raise SourceBrokerError()
    return result


def canonical_format(options, format_id, max_height):
    """Prove an exact option and bind its selector against future height changes."""
    valid = [item for item in options if type(item) is dict
             and type(item.get('height')) is int and 0 < item['height'] <= 16384
             and type(item.get('format_id')) is str]
    if format_id == 'best':
        legal = [item for item in valid if max_height is None or item['height'] <= max_height]
        choice = max(legal, key=lambda item: item['height']) if legal else None
    else:
        choice = next((item for item in valid if item['format_id'] == format_id), None)
    if choice is None:
        raise SourceBrokerError('format_unverified')
    height = choice['height']
    if max_height is not None and height > max_height:
        raise SourceBrokerError('membership_required')
    selector = choice['format_id']
    expected = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'
    if selector == expected:
        return selector
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', selector) or selector == 'best':
        raise SourceBrokerError('format_unverified')
    return f'{selector}[height<={max_height if max_height is not None else height}]'


def _decode(raw):
    try:
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise SourceBrokerError() from None


def _encode(value, maximum):
    try:
        raw = json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    except (ValueError, TypeError, RecursionError):
        raise SourceBrokerError() from None
    if not raw or len(raw) > maximum:
        raise SourceBrokerError()
    return raw


def read_frame(conn, maximum, *, timeout=RPC_SECONDS):
    deadline = time.monotonic() + timeout
    def exact(count):
        chunks = bytearray()
        while len(chunks) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceBrokerError()
            conn.settimeout(remaining)
            chunk = conn.recv(count - len(chunks))
            if not chunk:
                raise SourceBrokerError()
            chunks.extend(chunk)
        return chunks
    length = struct.unpack('!I', exact(4))[0]
    if not 0 < length <= maximum:
        raise SourceBrokerError()
    return _decode(exact(length))


def write_frame(conn, value, maximum, *, timeout=RPC_SECONDS):
    raw = _encode(value, maximum)
    conn.settimeout(timeout)
    conn.sendall(struct.pack('!I', len(raw)) + raw)


def _request(socket_path, payload, *, timeout=RPC_SECONDS):
    try:
        if not hasattr(socket, 'AF_UNIX'):
            raise SourceBrokerError()
        path = os.fspath(socket_path)
        if not path or ('\x00' in path if isinstance(path, str) else b'\x00' in path):
            raise SourceBrokerError()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout)
            conn.connect(path)
            write_frame(conn, payload, MAX_REQUEST, timeout=timeout)
            result = read_frame(conn, MAX_SUBTITLE_RESPONSE if payload.get('op') == 'subtitle' else MAX_RESPONSE,
                                timeout=timeout)
        if type(result) is not dict or type(result.get('version')) is not int or result['version'] != 1:
            raise SourceBrokerError()
        if result.get('ok') is False:
            if (set(result) != {'version', 'ok', 'code', 'status'}
                    or type(result.get('code')) is not str or result['code'] not in _ERRORS
                    or type(result.get('status')) is not int or result['status'] != _ERRORS[result['code']][0]):
                raise SourceBrokerError()
            raise SourceBrokerError(result['code'])
        if result.get('ok') is not True:
            raise SourceBrokerError()
        return result
    except SourceBrokerError:
        raise
    except (OSError, ValueError, TypeError, OverflowError):
        raise SourceBrokerError() from None


def ping(socket_path, timeout=2):
    try:
        value = _request(socket_path, {'version': 1, 'op': 'ping'}, timeout=timeout)
        return (type(value) is dict and set(value) == {'version', 'ok', 'pong', 'ready'}
                and type(value['version']) is int and value['version'] == 1
                and all(value[key] is True for key in ('ok', 'pong', 'ready')))
    except SourceBrokerError:
        return False


def parse_video(socket_path, url):
    result = _request(socket_path, {'version': 1, 'op': 'parse', 'url': url})
    if (set(result) != {'version', 'ok', 'meta', 'options'} or type(result['meta']) is not dict
            or type(result['options']) is not list or any(type(item) is not dict for item in result['options'])):
        raise SourceBrokerError()
    return result['meta'], result['options']


def verify_format(socket_path, url, format_id, max_height=None):
    result = _request(socket_path, {'version': 1, 'op': 'verify', 'url': url,
                                  'format_id': format_id, 'max_height': max_height})
    if (set(result) != {'version', 'ok', 'format_id'} or type(result['format_id']) is not str
            or not result['format_id'] or len(result['format_id']) > 1024):
        raise SourceBrokerError()
    return result['format_id']


def _subtitle_document(value):
    from .subtitle_service import SubtitleDocument
    from .subtitle_timing import SubtitleSegment
    fields = {'title', 'language', 'is_auto', 'available_languages', 'text', 'segments'}
    if (type(value) is not dict or set(value) != fields
            or any(type(value[key]) is not str for key in ('title', 'language', 'text'))
            or type(value['is_auto']) is not bool or type(value['available_languages']) is not list
            or any(type(item) is not str for item in value['available_languages'])
            or type(value['segments']) is not list):
        raise SourceBrokerError()
    segments = []
    for item in value['segments']:
        if (type(item) is not dict or set(item) != {'start', 'end', 'text'}
                or type(item['text']) is not str
                or any(type(item[key]) not in (int, float) or not math.isfinite(item[key]) for key in ('start', 'end'))
                or not 0 <= item['start'] <= item['end']):
            raise SourceBrokerError()
        segments.append(SubtitleSegment(**item))
    return SubtitleDocument(**{**value, 'segments': segments})


def fetch_subtitle_document(socket_path, url, language=None):
    result = _request(socket_path, {'version': 1, 'op': 'subtitle', 'url': url, 'language': language})
    if set(result) != {'version', 'ok', 'document'}:
        raise SourceBrokerError()
    return _subtitle_document(result['document'])


def _child_limits(maximum=MAX_RESPONSE):
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE, (maximum, maximum))
    # setpriv may clear this when changing UID; source_child re-arms and checks parent PID.
    _prctl(1, signal.SIGKILL)


def _prctl(option, value):
    import ctypes
    if ctypes.CDLL(None, use_errno=True).prctl(option, value, 0, 0, 0) != 0:
        raise SourceBrokerError()


def run_source_child(config, url, snapshot, *, op='parse', language=None):
    if os.name != 'posix' or not hasattr(os, 'memfd_create'):
        raise SourceBrokerError()
    if snapshot is not None and (type(snapshot) is not str or len(snapshot.encode('utf8')) > 16 * 1024):
        raise SourceBrokerError()
    request = {'version': 1, 'op': op, 'url': url, 'bili_cookie_snapshot': snapshot}
    if op == 'subtitle':
        request['language'] = language
    maximum = MAX_SUBTITLE_RESPONSE if op == 'subtitle' else MAX_RESPONSE
    payload = _encode(request, MAX_REQUEST - 1) + b'\n'
    process = None
    # Anonymous RAM file: no metadata or credentials are persisted on disk.
    with os.fdopen(os.memfd_create('source-result', os.MFD_CLOEXEC), 'w+b') as output:
        try:
            env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(_BACKEND), 'PYTHONDONTWRITEBYTECODE': '1',
                   'SOURCE_BROKER_PARENT_PID': str(os.getpid()), **config.child_env()}
            process = subprocess.Popen(config.command_prefix() + [sys.executable, '-B', '-m', 'app.source_child'],
                stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL, env=env,
                cwd=str(_BACKEND), start_new_session=True, preexec_fn=partial(_child_limits, maximum))
            # Keep stdin open as the parent-liveness channel. Payload is <=64KiB;
            # use a nonblocking write with the same absolute child deadline.
            import select
            os.set_blocking(process.stdin.fileno(), False)
            deadline = time.monotonic() + CHILD_SECONDS
            offset = 0
            while offset < len(payload):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([], [process.stdin], [], remaining)[1]:
                    raise SourceBrokerError()
                try:
                    offset += os.write(process.stdin.fileno(), payload[offset:])
                except BlockingIOError:
                    continue
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
            if process.returncode != 0:
                raise SourceBrokerError()
        except (OSError, subprocess.SubprocessError):
            raise SourceBrokerError() from None
        finally:
            try:
                if process is not None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    finally:
                        if process.stdin is not None:
                            process.stdin.close()
                        process.wait(timeout=5)
            finally:
                try:
                    # Fences helpers that escaped the group; sweep failure poisons this broker.
                    child_isolation.sweep(config)
                finally:
                    _reap_children()
        output.seek(0)
        raw = output.read(maximum + 1)
    if len(raw) > maximum:
        raise SourceBrokerError()
    result = _decode(raw)
    if type(result) is not dict or type(result.get('version')) is not int or result['version'] != 1:
        raise SourceBrokerError()
    if result.get('ok') is False:
        if (set(result) != {'version', 'ok', 'code', 'status'}
                or type(result.get('code')) is not str or result['code'] not in _ERRORS
                or type(result.get('status')) is not int or result['status'] != _ERRORS[result['code']][0]):
            raise SourceBrokerError()
        raise SourceBrokerError(result['code'])
    if op == 'subtitle':
        if set(result) != {'version', 'ok', 'document'} or result.get('ok') is not True:
            raise SourceBrokerError()
        _subtitle_document(result['document'])
        return result['document']
    if (set(result) != {'version', 'ok', 'meta', 'options'} or result.get('ok') is not True
            or type(result['meta']) is not dict or type(result['options']) is not list
            or any(type(item) is not dict for item in result['options'])):
        raise SourceBrokerError()
    return result['meta'], result['options']


def _reap_children():
    while True:
        try:
            if os.waitpid(-1, os.WNOHANG)[0] == 0:
                return
        except ChildProcessError:
            return


def peer_uid(conn):
    if not hasattr(socket, 'SO_PEERCRED'):
        raise SourceBrokerError()
    return struct.unpack('3i', conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]


class Broker:
    def __init__(self, config, *, api_uid, api_gid, child_runner=run_source_child, snapshot_reader=None):
        if type(api_uid) is not int or api_uid <= 0 or type(api_gid) is not int or api_gid <= 0:
            raise SourceBrokerError()
        if snapshot_reader is None:
            from .bilibili_session import cookie_snapshot_for_url
            snapshot_reader = cookie_snapshot_for_url
        self.config, self.api_uid, self.api_gid = config, api_uid, api_gid
        self.child_runner, self.snapshot_reader = child_runner, snapshot_reader
        self.ready = False
        self.broken = False

    def dispatch(self, payload):
        try:
            if self.broken:
                raise SourceBrokerError()
            request = validate_request(payload)
            if request['op'] == 'ping':
                if not self.ready:
                    raise SourceBrokerError()
                return {'version': 1, 'ok': True, 'pong': True, 'ready': True}
            snapshot = self.snapshot_reader(request['url'])
            if request['op'] == 'subtitle':
                document = self.child_runner(self.config, request['url'], snapshot,
                                             op='subtitle', language=request['language'])
                return {'version': 1, 'ok': True, 'document': document}
            meta, options = self.child_runner(self.config, request['url'], snapshot)
            if request['op'] == 'verify':
                return {'version': 1, 'ok': True, 'format_id': canonical_format(
                    options, request['format_id'], request['max_height'])}
            return {'version': 1, 'ok': True, 'meta': meta, 'options': options}
        except SourceBrokerError as error:
            return error_response(error.code)
        except child_isolation.IsolationError:
            self.ready = False
            self.broken = True
            return error_response()
        except Exception:
            return error_response()

    def handle_connection(self, conn, *, peer_uid=peer_uid):
        try:
            if peer_uid(conn) != self.api_uid:
                raise SourceBrokerError()
            payload = read_frame(conn, MAX_REQUEST, timeout=5)
            result = self.dispatch(payload)
            maximum = MAX_SUBTITLE_RESPONSE if type(payload) is dict and payload.get('op') == 'subtitle' else MAX_RESPONSE
            write_frame(conn, result, maximum, timeout=5)
        except Exception:
            try:
                write_frame(conn, error_response(), MAX_RESPONSE, timeout=2)
            except Exception:
                pass

    def serve(self, socket_path):
        """systemd owns the runtime directory; no mkdir or unsafe path removal."""
        if os.name != 'posix' or not hasattr(socket, 'SO_PEERCRED') or not hasattr(os, 'memfd_create'):
            raise SourceBrokerError()
        _prctl(36, 1)  # PR_SET_CHILD_SUBREAPER: reap escaped descendants after sweep.
        child_isolation.preflight(self.config)
        child_isolation.sweep(self.config)
        path = Path(socket_path)
        parent = path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
            raise SourceBrokerError()
        try:
            previous = path.lstat()
        except FileNotFoundError:
            previous = None
        if previous is not None:
            if not stat.S_ISSOCK(previous.st_mode) or previous.st_uid != os.geteuid():
                raise SourceBrokerError()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(1)
                try:
                    probe.connect(os.fspath(path))
                except OSError as error:
                    if error.errno != errno.ECONNREFUSED:
                        raise SourceBrokerError() from None
                else:
                    raise SourceBrokerError()
            current = path.lstat()
            if (current.st_dev, current.st_ino) != (previous.st_dev, previous.st_ino):
                raise SourceBrokerError()
            path.unlink()
        identity = None
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            try:
                listener.bind(os.fspath(path))
                identity = path.lstat()
                os.chown(path, -1, self.api_gid)
                os.chmod(path, 0o660)
                listener.listen(8)
                self.ready = True
                while True:
                    conn, _ = listener.accept()
                    with conn:
                        self.handle_connection(conn)
            finally:
                self.ready = False
                if identity is not None:
                    try:
                        current = path.lstat()
                        if (stat.S_ISSOCK(current.st_mode) and current.st_uid == os.geteuid()
                                and (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino)):
                            path.unlink()
                    except FileNotFoundError:
                        pass
