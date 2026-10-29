"""U4 explicit objects only; no application factory is switched."""
import os
import sys
import types
import subprocess
from urllib.request import Request as UrllibRequest

import pytest
import yt_dlp
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.networking import Request
from yt_dlp.networking.common import RequestDirector, Response, _REQUEST_HANDLERS
from yt_dlp.networking.exceptions import HTTPError, RequestError, TransportError
from yt_dlp import globals as yt_globals

from app.services import ytdlp_service as service
from app.services.outbound_budget import BudgetLimits, OutboundBudget
from app.services.outbound_httpx import ProxyChannel
from app.services.outbound_policy import OutboundError, OutboundPurpose, OutboundUnavailableError
from app.services.source_network import SourceNetworkContext
from test_outbound_httpx import transport_network


def reply(body=b'ok', status=b'200 OK', headers=b''):
    return (b'HTTP/1.1 ' + status + b'\r\nConnection: close\r\nContent-Length: '
            + str(len(body)).encode() + b'\r\n' + headers + b'\r\n' + body)


def context(clock=None):
    args = {} if clock is None else {'clock': clock}
    return SourceNetworkContext(
        ProxyChannel('http://127.0.0.1:4750', readiness_confirmed=True),
        OutboundBudget(BudgetLimits(seconds=100, requests=32), **args))


def guarded(network=None, **limits):
    return service._GuardedYoutubeDL(network or context(), purpose=OutboundPurpose.METADATA,
        limits=service._YtdlpReadLimits(**({'max_bytes': 4096, 'phase_seconds': 5,
                                         'io_timeout': 2} | limits)))


def safe(error):
    assert 'synthetic-secret' not in str(error) + repr(error) + repr(error.args)
    assert error.__context__ is None and error.__cause__ is None


def test_explicit_director_fixed_options_and_no_registry_or_environment_mutation(transport_network):
    before_env = dict(os.environ)
    before_registry = _REQUEST_HANDLERS.copy()
    before_plugins = (dict(yt_globals.plugin_ies.value), dict(yt_globals.plugin_pps.value))
    with guarded() as ydl:
        assert isinstance(ydl._request_director, RequestDirector)
        assert list(ydl._request_director.handlers) == [service._ControlledSourceRH.RH_KEY]
        assert ydl._ies == {} and ydl.params['js_runtimes'] == {}
        assert ydl.params['remote_components'] == set() and ydl.params['cachedir'] is False
        assert not ydl.params.get('cookiefile') and not ydl.params.get('cookiesfrombrowser')
        assert not ydl.params.get('postprocessors') and not ydl.params.get('post_hooks')
        assert 'proxies' not in ydl.__dict__
    assert _REQUEST_HANDLERS == before_registry
    assert before_plugins == (yt_globals.plugin_ies.value, yt_globals.plugin_pps.value)
    assert dict(os.environ) == before_env and not transport_network.connections


def test_real_super_uses_official_plugin_opt_out_without_scanning(monkeypatch):
    import importlib
    ydl_module = importlib.import_module('yt_dlp.YoutubeDL')
    plugins = importlib.import_module('yt_dlp.plugins')
    calls = []
    real_loader = ydl_module.load_all_plugins
    def loader():
        calls.append('real_loader')
        return real_loader()
    def scan(*args, **kwargs):
        pytest.fail('official plugin opt-out performed a scan')
    monkeypatch.setattr(ydl_module, 'load_all_plugins', loader)
    monkeypatch.setattr(plugins, 'iter_modules', scan)
    monkeypatch.setattr(yt_globals.all_plugins_loaded, 'value', False)
    with guarded():
        pass
    assert calls == ['real_loader']


def test_super_constructor_unexpected_failure_is_safe(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError('synthetic-secret')
    monkeypatch.setattr(yt_dlp.YoutubeDL, '__init__', broken)
    with pytest.raises(OutboundError) as error:
        guarded()
    assert error.value.code == 'outbound_unavailable'
    safe(error.value)


@pytest.mark.parametrize('flag', [None, '', 'true', '0'])
def test_plugin_flag_is_required_before_super(flag, monkeypatch):
    if flag is None:
        monkeypatch.delenv('YTDLP_NO_PLUGINS', raising=False)
    else:
        monkeypatch.setenv('YTDLP_NO_PLUGINS', flag)
    called = []
    monkeypatch.setattr(yt_dlp.YoutubeDL, '__init__', lambda *a, **kw: called.append(True))
    with pytest.raises(OutboundUnavailableError) as error:
        guarded()
    safe(error.value)
    assert called == []


@pytest.mark.parametrize('kind', ['extractor', 'postprocessor', 'override', 'new_namespace', 'old_namespace'])
def test_plugin_pollution_is_rejected_without_clearing_global_state(kind, monkeypatch):
    if kind in ('new_namespace', 'old_namespace'):
        name = ('yt_dlp_plugins' if kind == 'new_namespace' else 'ytdlp_plugins') + '.synthetic'
        marker = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, marker)
        read_marker = lambda: sys.modules[name]
    else:
        mapping = {'extractor': yt_globals.plugin_ies, 'postprocessor': yt_globals.plugin_pps,
                   'override': yt_globals.plugin_ies_overrides}[kind].value
        marker = object()
        monkeypatch.setitem(mapping, 'synthetic', marker)
        read_marker = lambda: mapping['synthetic']
    with pytest.raises(OutboundUnavailableError):
        guarded()
    assert read_marker() is marker


@pytest.mark.parametrize('source_request', [
    'http://127.0.0.1/private?sig=synthetic-secret',
    'https://u:synthetic-secret@public.example/page',
    Request('https://public.example/page', method='POST'),
    Request('https://public.example/page', data=b'synthetic-secret'),
    Request('https://public.example/page', proxies={'all': None}),
    Request('https://public.example/page', extensions={'cookiejar': None}),
    Request('https://public.example/page', extensions={'impersonate': 'chrome'}),
    Request('https://public.example/page', extensions={'timeout': True}),
    Request('https://public.example/page', extensions={'timeout': float('inf')}),
    Request('ftp://public.example/file'),
    object(),
])
def test_unsupported_request_is_terminal_before_io(source_request, transport_network):
    with guarded() as ydl:
        with pytest.raises(RequestError) as error:
            ydl.urlopen(source_request)
        safe(error.value)
        assert not isinstance(error.value, (HTTPError, TransportError))
        with pytest.raises(RequestError):
            ydl.urlopen('https://public.example/second')
    assert not transport_network.connections


@pytest.mark.parametrize('form', ['str', 'request', 'urllib', 'head'])
def test_real_director_get_head_and_safe_headers(form, transport_network):
    transport_network.replies = [reply()]
    network = context()
    url = 'http://public.example/path?sig=synthetic-secret'
    if form == 'str':
        request = url
    elif form == 'urllib':
        request = UrllibRequest(url)
    else:
        request = Request(url, method='HEAD' if form == 'head' else 'GET',
            headers={'Cookie': 'synthetic-secret', 'Authorization': 'synthetic-secret',
                     'User-Agent': 'fixture', 'Referer': 'https://public.example/'})
    with guarded(network) as ydl:
        response = ydl.urlopen(request)
        assert isinstance(response, Response) and response.status == 200
        assert response.read() == (b'' if form == 'head' else b'ok')
    sent = b''.join(transport_network.writes).lower()
    assert b'cookie:' not in sent and b'authorization:' not in sent
    assert network.budget.snapshot().requests == 1


class SwallowGuardIE(InfoExtractor):
    _VALID_URL = r'https://public\.example/(?P<id>[a-z]+)'
    attempts = []

    def _real_extract(self, url):
        for target in ('http://127.0.0.1/private?sig=synthetic-secret', 'https://public.example/second'):
            try:
                self._request_webpage(target, 'fixture', fatal=False)
            except Exception:
                self.attempts.append(target)
        return {'id': 'fixture', 'title': 'fake success', 'url': 'https://public.example/media'}


def test_true_extractor_swallowing_guard_cannot_send_again_or_return_success(transport_network):
    ie = SwallowGuardIE()
    ie.attempts = []
    with guarded() as ydl:
        ydl.add_info_extractor(ie)
        with pytest.raises(OutboundError) as error:
            ydl.extract_info('https://public.example/page', download=False, process=False)
        safe(error.value)
    assert len(ie.attempts) == 2 and not transport_network.connections


class ExpectedHttpIE(InfoExtractor):
    _VALID_URL = r'http://public\.example/(?P<id>[a-z]+)'
    def _real_extract(self, url):
        response = self._request_webpage(url, 'fixture', expected_status=404, fatal=False)
        return {'id': 'fixture', 'title': response.read().decode()}


def test_real_http_error_expected_status_remains_compatible(transport_network):
    transport_network.replies = [reply(b'not found', status=b'404 Not Found')]
    with guarded() as ydl:
        ydl.add_info_extractor(ExpectedHttpIE())
        result = ydl.extract_info('http://public.example/page', download=False, process=False)
        assert result['title'] == 'not found'


@pytest.mark.parametrize('operation', ['download', 'process', 'process_info', 'dl'])
def test_no_download_path_is_enabled(operation, transport_network):
    with guarded() as ydl:
        with pytest.raises(OutboundError) as error:
            if operation == 'process_info':
                ydl.process_info({'url': 'https://public.example/a.m3u8'})
            elif operation == 'dl':
                ydl.dl('-', {'url': 'https://public.example/a.m3u8'})
            else:
                ydl.extract_info('https://public.example/page',
                    download=operation == 'download', process=operation == 'process')
        assert error.value.code == 'outbound_unavailable'
    assert transport_network.connections == []


@pytest.mark.parametrize('field,value', [('max_bytes', True), ('max_bytes', 0),
    ('phase_seconds', False), ('phase_seconds', float('nan')), ('io_timeout', -1), ('identity_only', 1)])
def test_invalid_read_limits_rejected(field, value):
    with pytest.raises((ValueError, OutboundUnavailableError)):
        guarded(**{field: value})


def test_unknown_backend_error_is_sanitized_and_first_terminal_remains(transport_network, caplog):
    transport_network.connect_error = RuntimeError('synthetic-secret')
    with guarded() as ydl:
        with pytest.raises(RequestError) as error:
            ydl.urlopen('https://public.example/?sig=synthetic-secret')
        safe(error.value)
        with pytest.raises(RequestError) as again:
            ydl.urlopen('http://127.0.0.1/other')
        assert str(error.value) == str(again.value)
    assert len(transport_network.connections) == 1 and 'synthetic-secret' not in caplog.text


def test_fresh_process_first_import_uses_official_opt_out_without_plugin_scan():
    code = r'''
import os, sys, socket
assert not any(n == 'yt_dlp' or n.startswith('yt_dlp.') for n in sys.modules)
os.environ['YTDLP_NO_PLUGINS'] = '1'
def no_network(*args, **kwargs):
    raise AssertionError('offline child denied')
socket.getaddrinfo = socket.socket.connect = socket.socket.connect_ex = no_network
for action in (lambda: socket.getaddrinfo('offline.invalid', 80),
               lambda: socket.socket().connect(('192.0.2.1', 80)),
               lambda: socket.socket().connect_ex(('192.0.2.1', 80))):
    try: action()
    except AssertionError: pass
    else: raise AssertionError('child socket guard missing')
events = {'scanner': 0, 'loader': 0, 'exec': 0}
def watch(frame, event, arg):
    if event == 'call' and frame.f_code.co_filename.replace('\\', '/').endswith('/yt_dlp/plugins.py'):
        if frame.f_code.co_name == 'iter_modules':
            events['scanner'] += 1
            raise AssertionError('unexpected plugin scanner')
        if frame.f_code.co_name == 'load_all_plugins': events['loader'] += 1
    return watch
def audit(event, args):
    if event == 'exec':
        filename = getattr(args[0], 'co_filename', '').replace('\\', '/')
        if '/yt_dlp_plugins/' in filename or '/ytdlp_plugins/' in filename:
            events['exec'] += 1
            raise AssertionError('unexpected plugin exec')
sys.setprofile(watch)
sys.addaudithook(audit)
from app.services.ytdlp_service import _GuardedYoutubeDL, _YtdlpReadLimits
from app.services.source_network import SourceNetworkContext
from app.services.outbound_httpx import ProxyChannel
from app.services.outbound_budget import OutboundBudget, BudgetLimits
from app.services.outbound_policy import OutboundPurpose
network = SourceNetworkContext(ProxyChannel('http://127.0.0.1:4750', readiness_confirmed=True), OutboundBudget(BudgetLimits()))
with _GuardedYoutubeDL(network, purpose=OutboundPurpose.METADATA,
        limits=_YtdlpReadLimits(max_bytes=100, phase_seconds=1, io_timeout=1)):
    pass
sys.setprofile(None)
assert events == {'scanner': 0, 'loader': 1, 'exec': 0}, events
assert not any(n == 'yt_dlp_plugins' or n.startswith('yt_dlp_plugins.') or n == 'ytdlp_plugins' or n.startswith('ytdlp_plugins.') for n in sys.modules)
print('fresh plugin import checked')
'''
    child_env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR') if key in os.environ}
    child_env.update(PYTHONPATH=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                     DB_URL='sqlite:///:memory:', BILIBILI_COOKIE_FILE='')
    result = subprocess.run([sys.executable, '-B', '-c', code], env=child_env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'fresh plugin import checked'
