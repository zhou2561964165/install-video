from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
pytestmark = pytest.mark.usefixtures("vip_entitlements")
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.main import app
from app.services.llm_service import LLMSummaryResult, LLMTextResult, LLMServiceError
from app.services.subtitle_service import SubtitleDocument


@pytest.fixture
def fixture(monkeypatch):
    monkeypatch.setattr('app.main._window', defaultdict(list))
    client = TestClient(app)
    calls = defaultdict(int)
    doc = SubtitleDocument('title', 'en', False, ['en'], 'source text')
    def source(url, language):
        calls['source'] += 1
        return doc
    def summary(*args, **kwargs):
        calls['summary'] += 1
        return LLMSummaryResult('overview', ['detail'], 'mock', 'model')
    def translation(*args, **kwargs):
        calls['translation'] += 1
        return LLMTextResult('translated', 'mock', 'model')
    monkeypatch.setattr('app.routes.insight_common.fetch_subtitle_document', source)
    monkeypatch.setattr('app.routes.summary.summarize_text', summary)
    monkeypatch.setattr('app.routes.subtitle.translate_text', translation)
    def account():
        response = client.post('/api/auth/register', json={'email': f'{uuid4()}@example.com', 'password': 'password123'})
        assert response.status_code == 200
        return {'Authorization': f"Bearer {response.json()['token']}"}
    return client, calls, doc, account


def test_read_translate_and_summary_share_one_subtitle_fetch(fixture):
    client, calls, _, account = fixture
    headers = account()
    for path in ['/api/subtitle', '/api/subtitle/translate', '/api/summary', '/api/summary']:
        result = client.post(path, json={'url': 'https://example.com/v'}, headers=headers)
        assert result.status_code == 200
    assert calls == {'source': 1, 'translation': 1, 'summary': 1}


@pytest.mark.parametrize('path,field', [('/api/summary', 'summary'), ('/api/subtitle/translate', 'translation')])
def test_result_reuse_isolated_by_account_and_language(fixture, path, field):
    client, calls, _, account = fixture
    headers = account()
    body = {'url': 'https://example.com/v'}
    one = client.post(path, json=body, headers=headers)
    two = client.post(path, json=body, headers=headers)
    assert one.json() == two.json()
    assert calls[field] == 1
    foreign = account()
    assert client.post(path, json=body, headers=foreign).status_code == 200
    language = 'output_language' if field == 'summary' else 'target_language'
    assert client.post(path, json={**body, language: 'en'}, headers=headers).status_code == 200
    assert calls[field] == 3


def test_changed_model_settings_cannot_replay_old_result(fixture, monkeypatch):
    client, calls, _, account = fixture
    headers = account()
    body = {'url': 'https://example.com/v'}
    assert client.post('/api/summary', json=body, headers=headers).status_code == 200
    monkeypatch.setattr(settings, 'llm_model', 'changed-model')
    assert client.post('/api/summary', json=body, headers=headers).status_code == 200
    assert calls['summary'] == 2


def test_invalid_cached_source_still_obeys_current_public_length_limit(fixture, monkeypatch):
    client, calls, _, account = fixture
    headers = account()
    body = {'url': 'https://example.com/v'}
    assert client.post('/api/summary', json=body, headers=headers).status_code == 200
    monkeypatch.setattr(settings, 'summary_max_source_chars', 1)
    result = client.post('/api/summary', json=body, headers=headers)
    assert result.status_code == 422
    assert calls['summary'] == 1


def test_unauthenticated_request_cannot_use_authenticated_result(fixture):
    client, calls, _, account = fixture
    assert client.post('/api/summary', json={'url': 'https://example.com/v'}, headers=account()).status_code == 200
    assert client.post('/api/summary', json={'url': 'https://example.com/v'}).status_code == 401
    assert calls['summary'] == 1


def test_cache_configuration_has_finite_validated_defaults():
    config = Settings()
    assert config.insight_cache_max_entries == 128
    assert config.insight_cache_max_bytes == 16 * 1024 * 1024
    assert config.subtitle_cache_ttl_seconds == 900
    assert config.insight_result_cache_ttl_seconds == 3600


@pytest.mark.parametrize('name,value', [
    ('insight_cache_max_entries', 0), ('insight_cache_max_bytes', -1),
    ('insight_cache_max_inflight', 0), ('insight_cache_max_waiters', 0),
    ('insight_cache_wait_seconds', 0), ('subtitle_cache_ttl_seconds', -1),
    ('insight_result_cache_ttl_seconds', -1), ('download_idempotency_ttl_seconds', 0),
])
def test_cache_configuration_rejects_invalid_limits(name, value):
    with pytest.raises(ValueError):
        Settings(**{name: value})


def test_changed_source_body_invalidates_summary_even_at_same_url(fixture, monkeypatch):
    client, calls, doc, account = fixture
    monkeypatch.setattr(settings, 'subtitle_cache_ttl_seconds', 0)
    headers = account()
    body = {'url': 'https://example.com/v'}
    assert client.post('/api/summary', json=body, headers=headers).status_code == 200
    from dataclasses import replace
    monkeypatch.setattr('app.routes.insight_common.fetch_subtitle_document',
                        lambda *args: replace(doc, text='updated source text'))
    assert client.post('/api/summary', json=body, headers=headers).status_code == 200
    assert calls['summary'] == 2


@pytest.mark.parametrize('field', ['subtitle_cache_ttl_seconds', 'insight_result_cache_ttl_seconds',
                                 'insight_cache_max_entries', 'insight_cache_max_bytes',
                                 'insight_cache_max_inflight', 'insight_cache_max_waiters',
                                 'insight_cache_wait_seconds', 'download_idempotency_ttl_seconds',
                                 'download_idempotency_direct_ttl_seconds', 'download_idempotency_max_entries'])
def test_settings_read_cache_and_idempotency_limits_from_env(monkeypatch, field):
    monkeypatch.setenv(field.upper(), '42')
    assert getattr(Settings.from_env(), field) == 42


@pytest.mark.parametrize('path', ['/api/summary', '/api/subtitle/translate'])
def test_failed_generation_is_not_saved_as_a_success(fixture, monkeypatch, path):
    client, calls, _, account = fixture
    headers = account()
    name = 'summary.summarize_text' if path == '/api/summary' else 'subtitle.translate_text'
    def fail(*args, **kwargs):
        calls['failure'] += 1
        raise LLMServiceError('llm_incomplete_response', 'incomplete')
    monkeypatch.setattr(f'app.routes.{name}', fail)
    for _ in range(2):
        response = client.post(path, json={'url': 'https://example.com/v'}, headers=headers)
        assert response.status_code == 502
        assert response.json()['detail']['error_type'] == 'llm_incomplete_response'
    assert calls['failure'] == 2  # Two explicit requests, no automatic retry.
    assert calls['source'] == 1


def test_subtitle_error_is_not_cached(fixture, monkeypatch):
    from app.services.subtitle_service import SubtitleServiceError
    client, calls, _, account = fixture
    headers = account()
    def fail(*args, **kwargs):
        calls['failure'] += 1
        raise SubtitleServiceError('no_subtitles', 'no subtitles')
    monkeypatch.setattr('app.routes.insight_common.fetch_subtitle_document', fail)
    for _ in range(2):
        assert client.post('/api/subtitle', json={'url': 'https://example.com/v'}, headers=headers).status_code == 422
    assert calls['failure'] == 2


@pytest.mark.parametrize('fail', [False, True])
def test_concurrent_summary_joins_one_provider_call_and_shares_failure(fixture, monkeypatch, fail):
    from app.services import request_cache
    client, calls, _, account = fixture
    headers = account()
    entered, joined, release = Event(), Event(), Event()
    class ObservedFuture(Future):
        def result(self, timeout=None):
            joined.set()
            return super().result(timeout)
    monkeypatch.setattr(request_cache, 'Future', ObservedFuture)
    def generate(*args, **kwargs):
        calls['provider'] += 1
        entered.set()
        assert release.wait(3)
        if fail:
            raise LLMServiceError('llm_error', 'provider unavailable')
        return LLMSummaryResult('result', ['one'], 'mock', 'model')
    monkeypatch.setattr('app.routes.summary.summarize_text', generate)
    def post():
        return client.post('/api/summary', json={'url': 'https://example.com/v'}, headers=headers)
    # Prime source so the observed Future join belongs to result generation.
    assert client.post('/api/subtitle', json={'url': 'https://example.com/v'}, headers=headers).status_code == 200
    with ThreadPoolExecutor(2) as pool:
        owner = pool.submit(post)
        assert entered.wait(1)
        waiter = pool.submit(post)
        try:
            assert joined.wait(1)
        finally:
            release.set()
        first, second = owner.result(3), waiter.result(3)
    assert first.status_code == second.status_code == (502 if fail else 200)
    assert first.json() == second.json()
    assert calls['provider'] == 1


def test_saturated_content_cache_returns_503_without_second_provider(fixture, monkeypatch):
    client, calls, _, account = fixture
    monkeypatch.setattr(settings, 'insight_cache_max_inflight', 1)
    headers = account()
    entered, release = Event(), Event()
    def generate(*args, **kwargs):
        calls['provider'] += 1
        entered.set()
        assert release.wait(3)
        return LLMSummaryResult('result', ['one'], 'mock', 'model')
    monkeypatch.setattr('app.routes.summary.summarize_text', generate)
    with ThreadPoolExecutor(1) as pool:
        owner = pool.submit(client.post, '/api/summary', json={'url': 'https://example.com/v'}, headers=headers)
        assert entered.wait(1)
        try:
            busy = client.post('/api/summary', json={'url': 'https://example.com/v', 'output_language': 'en'}, headers=headers)
            assert busy.status_code == 503
            assert busy.json()['detail']['error_type'] == 'request_busy'
        finally:
            release.set()
        assert owner.result(3).status_code == 200
    assert calls['provider'] == 1
