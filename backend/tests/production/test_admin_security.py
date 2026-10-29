"""Admin M1 Task 2: admin settings validation and security primitives (offline)."""
import dataclasses

import pytest

from app.admin import security
from app.admin.config import AdminSettings

SECRET = b's' * 32


def settings(**changes):
    base = AdminSettings(cookie_path='/api/admin/v1', allowed_origins=('https://admin.example',), csrf_secret=SECRET)
    return dataclasses.replace(base, **changes)


def test_csrf_is_deterministic_and_bound():
    token = security.csrf_token(SECRET, 'sid', 'a' * 64)
    assert token == security.csrf_token(SECRET, 'sid', 'a' * 64)
    assert len(token) == 64
    assert token != security.csrf_token(SECRET, 'other', 'a' * 64)
    assert token != security.csrf_token(SECRET, 'sid', 'b' * 64)
    assert token != security.csrf_token(b't' * 32, 'sid', 'a' * 64)


def test_csrf_valid_rejects_none_and_wrong():
    token = security.csrf_token(SECRET, 'sid', 'a' * 64)
    assert security.csrf_valid(SECRET, 'sid', 'a' * 64, token)
    assert not security.csrf_valid(SECRET, 'sid', 'a' * 64, None)
    assert not security.csrf_valid(SECRET, 'sid', 'a' * 64, '')
    assert not security.csrf_valid(SECRET, 'sid', 'a' * 64, token[:-1] + ('0' if token[-1] != '0' else '1'))


def test_origin_exact_match_and_empty_list_denies():
    allowed = ('https://admin.example', 'http://127.0.0.1:4174')
    assert security.origin_allowed('https://admin.example', allowed)
    assert not security.origin_allowed('https://admin.example/', allowed)
    assert not security.origin_allowed('https://evil.example', allowed)
    assert not security.origin_allowed(None, allowed)
    assert not security.origin_allowed('https://admin.example', ())


def test_session_token_and_hash():
    token, digest = security.new_session_token()
    assert len(token) >= 40 and digest == security.token_hash(token)
    assert len(digest) == 64 and all(c in '0123456789abcdef' for c in digest)
    assert security.new_session_token()[0] != token


def test_settings_unavailable_reasons():
    assert settings().unavailable_reason() is None
    assert settings(cookie_path=None).unavailable_reason() is not None
    assert settings(cookie_path='/other').unavailable_reason() is not None
    assert settings(csrf_secret=None).unavailable_reason() is not None
    assert settings(csrf_secret=b's' * 31).unavailable_reason() is not None


@pytest.mark.parametrize('name,value', [
    ('ADMIN_SESSION_TTL_SECONDS', '299'), ('ADMIN_SESSION_TTL_SECONDS', '3601'),
    ('ADMIN_PAGE_SIZE_MAX', '1001'), ('ADMIN_PAGE_SIZE_DEFAULT', '200'), ('ADMIN_REFRESH_INTERVAL_SECONDS', '10'),
    ('ADMIN_REFRESH_INTERVAL_SECONDS', '301'), ('ADMIN_COOKIE_SECURE', 'maybe'),
])
def test_settings_range_validation(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        AdminSettings.from_env()


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv('ADMIN_COOKIE_PATH', '/api/admin/v1')
    monkeypatch.setenv('ADMIN_ALLOWED_ORIGINS', 'http://localhost:4174, http://127.0.0.1:4174')
    monkeypatch.setenv('ADMIN_CSRF_SECRET', 'x' * 40)
    monkeypatch.setenv('ADMIN_COOKIE_SECURE', 'false')
    loaded = AdminSettings.from_env()
    assert loaded.allowed_origins == ('http://localhost:4174', 'http://127.0.0.1:4174')
    assert loaded.csrf_secret == b'x' * 40 and loaded.cookie_secure is False
    assert (loaded.session_ttl_seconds, loaded.default_page_size, loaded.max_page_size) == (900, 20, 100)
    assert loaded.unavailable_reason() is None


def test_throttle_key_hides_inputs():
    key = security.throttle_key(SECRET, '203.0.113.9', ' Admin@Example.COM ')
    assert key == security.throttle_key(SECRET, '203.0.113.9', 'admin@example.com')
    assert len(key) == 64 and 'admin' not in key and '203' not in key
    assert key != security.throttle_key(SECRET, '203.0.113.10', 'admin@example.com')


def test_dummy_hash_verifies_nothing():
    from app.services.auth import verify_password
    assert not verify_password('anything', security.DUMMY_PASSWORD_HASH)


def test_non_ascii_csrf_header_is_rejected_not_an_error():
    assert not security.csrf_valid(SECRET, 'sid', 'a' * 64, 'caf\u00e9' * 16)


@pytest.mark.parametrize('origins', ['https://a.example/', 'null', 'https://a.example/path', 'ftp://a.example', '*'])
def test_origin_entries_must_be_exact_origins(monkeypatch, origins):
    monkeypatch.setenv('ADMIN_ALLOWED_ORIGINS', origins)
    with pytest.raises(ValueError):
        AdminSettings.from_env()


def test_insecure_cookie_only_for_loopback_origins(monkeypatch):
    monkeypatch.setenv('ADMIN_COOKIE_SECURE', 'false')
    monkeypatch.setenv('ADMIN_ALLOWED_ORIGINS', 'https://admin.example')
    with pytest.raises(ValueError):
        AdminSettings.from_env()
    monkeypatch.setenv('ADMIN_ALLOWED_ORIGINS', 'http://127.0.0.1:4174,http://localhost:4174')
    assert AdminSettings.from_env().cookie_secure is False
