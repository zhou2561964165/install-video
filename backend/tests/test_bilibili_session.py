"""Only synthetic credentials; this suite never sends network requests."""
import importlib
import os
import stat
from urllib.request import Request
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings, settings


VIDEO = 'https://www.bilibili.com/video/BVtest'
SECRET = 'synthetic-secret-never-log'


def session():
    return importlib.import_module('app.services.bilibili_session')


def cookie_file(tmp_path, monkeypatch, rows=None):
    path = tmp_path / 'synthetic.jar'
    path.write_text('# Netscape HTTP Cookie File\n' + (rows if rows is not None else
        f'.bilibili.com\tTRUE\t/\tTRUE\t4102444800\tX-BILI-SEC-TOKEN\t{SECRET}\n'), encoding='utf-8')
    path.chmod(0o600)
    monkeypatch.setattr(settings, 'bilibili_cookie_file', str(path), raising=False)
    return path


def test_config_opt_in_from_environment(monkeypatch):
    monkeypatch.delenv('BILIBILI_COOKIE_FILE', raising=False)
    assert Settings.from_env().bilibili_cookie_file == ''
    monkeypatch.setenv('BILIBILI_COOKIE_FILE', 'fixture.jar')
    assert Settings.from_env().bilibili_cookie_file == 'fixture.jar'


@pytest.mark.parametrize(('url', 'allowed'), [
    (VIDEO, True), ('https://api.bilibili.com/x', True), ('http://b23.tv/a', True),
    ('https://bilibili.com.evil.test/x', False), ('https://evilbilibili.com', False),
    ('https://bilibili.com@evil.test', False), ('https://user@bilibili.com/x', False),
    ('file://bilibili.com/x', False), ('https://bilibili.com:broken/x', False),
    ('https://bilivideo.com/v', False), ('https://bilibili.com\\@evil.test', False),
])
def test_official_url_boundary(url, allowed):
    assert session().is_bilibili_url(url) is allowed


def test_cookie_scope_reloads_and_no_writeback(tmp_path, monkeypatch):
    path = cookie_file(tmp_path, monkeypatch,
        f'.bilibili.com\tTRUE\t/private\tTRUE\t4102444800\tX-BILI-SEC-TOKEN\t{SECRET}\n'
        '.evil.test\tTRUE\t/\tFALSE\t4102444800\tforeign\tignore\n'
        '.bilibili.com\tTRUE\t/\tTRUE\t1\tbili_ticket\told\n')
    original = path.read_bytes()
    jar = session().cookie_jar_for_url(VIDEO)
    assert [c.name for c in jar] == ['X-BILI-SEC-TOKEN']
    with httpx.Client(cookies=jar, transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        assert SECRET in client.build_request('GET', 'https://api.bilibili.com/private/x').headers['cookie']
        for url in ['https://api.bilibili.com/public', 'http://api.bilibili.com/private',
                    'https://cdn.bilivideo.com/private', 'https://bilibili.com.evil.test/private']:
            assert 'cookie' not in client.build_request('GET', url).headers
    assert path.read_bytes() == original
    replacement = tmp_path / 'replacement.jar'
    replacement.write_bytes(original.replace(SECRET.encode(), b'replacement-secret'))
    replacement.chmod(0o600)
    replacement.replace(path)
    assert next(iter(session().cookie_jar_for_url(VIDEO))).value == 'replacement-secret'


def test_no_config_and_non_bili_never_open_file(monkeypatch):
    monkeypatch.setattr(settings, 'bilibili_cookie_file', 'must-not-open', raising=False)
    monkeypatch.setattr('os.open', lambda *a, **kw: pytest.fail('unexpected credential read'))
    assert list(session().cookie_jar_for_url('https://youtube.com/watch?v=x')) == []
    assert not session().session_enabled('https://youtube.com/watch?v=x')
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    assert list(session().cookie_jar_for_url(VIDEO)) == []


@pytest.mark.parametrize('rows', [
    f'.bilibili.com\tTRUE\t/\tTRUE\t1\tX-BILI-SEC-TOKEN\t{SECRET}\n',
    f'.bilibili.com\tFALSE\t/\tTRUE\t4102444800\tname\t{SECRET}\n',
    f'.bilibili.com\tTRUE\t/\tTRUE\tbad\tname\t{SECRET}\n',
    f'broken {SECRET}\n',
    f'.bilibili.com\tTRUE\t/\tTRUE\t4102444800\tname\t{SECRET}\textra\n',
])
def test_bad_or_expired_credentials_are_safe(tmp_path, monkeypatch, capsys, rows):
    path = cookie_file(tmp_path, monkeypatch, rows)
    with pytest.raises(session().SessionError) as error:
        session().cookie_jar_for_url(VIDEO)
    assert SECRET not in str(error.value)
    assert str(path) not in str(error.value)
    assert capsys.readouterr() == ('', '')


def test_missing_large_nonregular_and_symlink_rejected(tmp_path, monkeypatch):
    path = cookie_file(tmp_path, monkeypatch)
    path.write_bytes(b'x' * (1024 * 1024 + 1))
    with pytest.raises(session().SessionError):
        session().cookie_jar_for_url(VIDEO)
    path.unlink()
    with pytest.raises(session().SessionError):
        session().cookie_jar_for_url(VIDEO)
    monkeypatch.setattr(settings, 'bilibili_cookie_file', str(tmp_path))
    with pytest.raises(session().SessionError):
        session().cookie_jar_for_url(VIDEO)


def test_symlink_metadata_is_rejected_before_open(tmp_path, monkeypatch):
    cookie_file(tmp_path, monkeypatch)
    link = SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_size=12, st_uid=0)
    monkeypatch.setattr(os, 'lstat', lambda _: link)
    monkeypatch.setattr(os, 'open', lambda *a, **kw: pytest.fail('symlink opened'))
    with pytest.raises(session().SessionError):
        session().cookie_jar_for_url(VIDEO)


def test_host_only_cookie_never_expands_to_other_subdomain(tmp_path, monkeypatch):
    cookie_file(tmp_path, monkeypatch,
        f'www.bilibili.com\tFALSE\t/\tTRUE\t0\tX-BILI-SEC-TOKEN\t{SECRET}\n')
    jar = session().cookie_jar_for_url(VIDEO)
    exact = Request(VIDEO)
    child = Request('https://api.www.bilibili.com/v')
    jar.add_cookie_header(exact)
    jar.add_cookie_header(child)
    assert SECRET in exact.get_header('Cookie')
    assert child.get_header('Cookie') is None


@pytest.mark.parametrize(('mode', 'uid', 'allowed'), [
    (0o640, 0, True), (0o600, 123, True), (0o660, 0, False),
    (0o604, 0, False), (0o640, 999, False),
])
def test_linux_trust_allows_root_group_read_only(mode, uid, allowed):
    metadata = SimpleNamespace(st_mode=stat.S_IFREG | mode, st_uid=uid, st_size=42)
    if allowed:
        session()._validate_metadata(metadata, posix=True, current_uid=123)
    else:
        with pytest.raises(session().SessionError):
            session()._validate_metadata(metadata, posix=True, current_uid=123)
