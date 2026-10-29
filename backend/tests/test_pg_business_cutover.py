"""Offline F-gate boundary checks. No production env, database or source requests."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import db
from app.config import Settings, settings
from app.models import User
from app.schemas import DownloadRequest, DownloadResponse
from app.services.download_submission import AccessSnapshot


def test_pg_startup_requires_explicit_enable_and_ready_source(monkeypatch, tmp_path):
    engine = SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
    monkeypatch.setattr(db, 'engine', engine)
    checked = []
    monkeypatch.setattr(db, 'assert_schema_current', lambda e: checked.append(e))
    monkeypatch.setattr(db, 'assert_source_ready', lambda: checked.append('source'), raising=False)
    cfg = Settings(pg_business_enabled=True, source_broker_socket=str(tmp_path / 'broker.sock'),
                   media_root=tmp_path, billing_inbox_mode='durable',
                   stripe_provider_account_scope='operator-sandbox', stripe_livemode=False)
    monkeypatch.setattr(db, 'settings', cfg)
    db.init_db()
    assert checked == [engine, 'source']


def test_pg_startup_rejects_partial_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(db, 'engine', SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))
    monkeypatch.setattr(db, 'assert_schema_current', lambda _: None)
    monkeypatch.setattr(db, 'assert_source_ready', lambda: None, raising=False)
    for changes in ({'source_broker_socket': ''}, {'media_root': None},
                    {'billing_inbox_mode': 'legacy_sync'}, {'stripe_livemode': None},
                    {'stripe_provider_account_scope': ''}):
        values = dict(pg_business_enabled=True, source_broker_socket=str(tmp_path/'broker.sock'),
                      media_root=tmp_path, billing_inbox_mode='durable',
                      stripe_provider_account_scope='operator-sandbox', stripe_livemode=False)
        values.update(changes)
        monkeypatch.setattr(db, 'settings', Settings(**values))
        with pytest.raises(db.DatabaseConfigurationError):
            db.init_db()


@pytest.mark.parametrize('key', ['PG_BUSINESS_ENABLED', 'PG_CUTOVER_READ_ONLY'])
def test_cutover_flags_refuse_ambiguous_boolean(monkeypatch, key):
    monkeypatch.setenv(key, 'yes')
    with pytest.raises(ValueError, match=key):
        Settings.from_env()


def test_pg_download_releases_request_session_and_uses_verified_format(monkeypatch):
    from app.routes import download as route
    calls = []
    class Session:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
        def close(self):
            calls.append('closed')
    session = Session()
    monkeypatch.setattr(settings, 'source_broker_socket', '/run/source.sock', raising=False)
    monkeypatch.setattr(settings, 'pg_cutover_read_only', False, raising=False)
    snapshot = AccessSnapshot(720, 3, '')
    monkeypatch.setattr(route.download_submission, 'read_access_snapshot', lambda *_: snapshot)
    def verify(path, url, format_id, height):
        assert calls == ['closed']
        assert height == 720
        calls.append('verified')
        return 'bestvideo[height<=360]+bestaudio/best[height<=360]'
    monkeypatch.setattr(route, '_verify_source_format', verify)
    def submit(engine, uid, request, key, access, **kwargs):
        assert uid == 'existing-user'
        assert access == replace(snapshot, canonical_format_id=request.format_id)
        assert request.format_id.endswith('height<=360]')
        assert kwargs['server_required'] is True
        assert key == 'stable-client-key'
        return DownloadResponse(mode='server', job_id='durable-job')
    monkeypatch.setattr(route.download_submission, 'submit_download', submit)
    result = route.download(DownloadRequest(url='https://www.bilibili.com/video/BV1DdnM6bEL4',
        format_id='choice'), session=session, user=User(id='existing-user', email='operator@example.invalid',
        password_hash='synthetic'), idempotency_key='stable-client-key')
    assert result.job_id == 'durable-job'
    assert calls == ['closed', 'verified']


def test_readonly_cutover_blocks_login_webhook_and_download(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(settings, 'pg_cutover_read_only', True, raising=False)
    with TestClient(app) as client:
        for path in ('/api/auth/login', '/api/billing/webhook', '/api/download', '/api/membership'):
            response = client.post(path, json={}) if path != '/api/membership' else client.get(path)
            assert response.status_code == 503
            assert response.headers['retry-after'] == '60'
        assert client.get('/api/health').status_code == 200
        assert client.get('/api/membership/plans').status_code == 200


def test_production_parse_uses_broker_and_never_legacy_source(monkeypatch):
    from app.routes import parse as route
    from app.services import source_broker
    from app.schemas import ParseRequest
    monkeypatch.setattr(settings, 'pg_business_enabled', True)
    monkeypatch.setattr(settings, 'source_broker_socket', '/run/source.sock')
    monkeypatch.setattr(route, 'parse_video', lambda *_: pytest.fail('unguarded source'))
    calls = []
    def isolated(path, url):
        calls.append((path, url))
        return {'title': 'isolated', 'thumbnail': None, 'duration': 20}, []
    monkeypatch.setattr(source_broker, 'parse_video', isolated)
    result = route.parse(ParseRequest(url='https://public.example/video'), _user=None)
    assert result.title == 'isolated' and calls == [('/run/source.sock', 'https://public.example/video')]


def test_production_subtitle_uses_broker(monkeypatch):
    from app.routes import insight_common
    from app.services import source_broker
    from app.services.subtitle_service import SubtitleDocument
    monkeypatch.setattr(settings, 'pg_business_enabled', True)
    monkeypatch.setattr(settings, 'source_broker_socket', '/run/source.sock')
    monkeypatch.setattr(insight_common, 'fetch_subtitle_document', lambda *_: pytest.fail('unguarded subtitle'))
    doc = SubtitleDocument('isolated', 'zh', False, ['zh'], 'safe text')
    monkeypatch.setattr(source_broker, 'fetch_subtitle_document', lambda *args: doc)
    assert insight_common.load_subtitle('https://public.example/video', 'zh') is doc


def test_admin_readiness_requires_live_broker_and_no_maintenance(monkeypatch):
    from app.admin.routes_read import _download_readiness
    from app.services import source_broker
    monkeypatch.setattr(settings, 'pg_business_enabled', True)
    monkeypatch.setattr(settings, 'pg_cutover_read_only', True)
    monkeypatch.setattr(source_broker, 'ping', lambda *_: True)
    assert _download_readiness().ready is False
    monkeypatch.setattr(settings, 'pg_cutover_read_only', False)
    assert _download_readiness().ready is True
    monkeypatch.setattr(source_broker, 'ping', lambda *_: False)
    assert _download_readiness().ready is False
