import json
from types import SimpleNamespace

import pytest
pytestmark = pytest.mark.usefixtures("vip_entitlements")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import subtitle as routes
from app.services import subtitle_service as service
from app.services.subtitle_service import SubtitleDocument, SubtitleServiceError


def fetch_inline(monkeypatch, raw, ext):
    monkeypatch.setattr(service.ytdlp_service, 'extract_subtitle_tracks', lambda url: {
        'title': 'video', 'tracks': [{'language': 'en', 'is_auto': False,
            'formats': [{'ext': ext, 'data': raw}]}]})
    return service.fetch_subtitle_document('https://example.com/video')


@pytest.mark.parametrize('ext,raw', [
    ('srt', '1\n00:00:01,250 --> 00:00:02,500\n<b>Hello</b>\n\n2\n00:00:02,500 --> 00:00:03,000\nHello'),
    ('vtt', 'WEBVTT\n\ncue-a\n00:00:01.250 --> 00:00:02.500\n<b>Hello</b>\n\ncue-b\n00:00:02.500 --> 00:00:03.000\nHello'),
    ('ttml', '<tt xmlns="http://www.w3.org/ns/ttml"><body><div><p begin="1.25s" end="2.5s">Hello</p><p begin="2.5s" dur="0.5s">Hello</p></div></body></tt>'),
    ('srv3', '<timedtext><body><p t="1250" d="1250"><s>Hello</s></p><p t="2500" d="500">Hello</p></body></timedtext>'),
    ('json3', json.dumps({'events': [{'tStartMs': 1250, 'dDurationMs': 1250, 'segs': [{'utf8': 'Hello'}]}, {'tStartMs': 2500, 'dDurationMs': 500, 'segs': [{'utf8': 'Hello'}]}]})),
    ('bilibili_json', json.dumps({'body': [{'from': 1.25, 'to': 2.5, 'content': 'Hello'}, {'from': 2.5, 'to': 3, 'content': 'Hello'}]})),
])
def test_timeline_preserves_repeated_cues_without_changing_deduped_body(monkeypatch, ext, raw):
    doc = fetch_inline(monkeypatch, raw, ext)
    assert doc.text == 'Hello'
    assert [(cue.start, cue.end, cue.text) for cue in doc.segments] == [(1.25, 2.5, 'Hello'), (2.5, 3, 'Hello')]


@pytest.mark.parametrize('ext,raw', [
    ('ttml', '<tt><body><p>Hello</p></body></tt>'),
    ('srv3', '<timedtext><body><p>Hello</p></body></timedtext>'),
    ('json3', '{"events":[{"segs":[{"utf8":"Hello"}]}]}'),
    ('json3', '{"events":[{"tStartMs":0,"dDurationMs":1000,"segs":[{"utf8":"Hello"}]},{"segs":[{"utf8":"World"}]}]}'),
])
def test_missing_times_never_fabricate_or_export_partial_timeline(monkeypatch, ext, raw):
    doc = fetch_inline(monkeypatch, raw, ext)
    assert doc.text.startswith('Hello')
    assert doc.segments == []


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), True, '1000'])
def test_invalid_json3_times_reject_safely(monkeypatch, value):
    raw = json.dumps({'events': [{'tStartMs': value, 'dDurationMs': 1000, 'segs': [{'utf8': 'Hello'}]}]})
    with pytest.raises(SubtitleServiceError) as error:
        fetch_inline(monkeypatch, raw, 'json3')
    assert error.value.error_type == 'subtitle_invalid'


def test_timeline_cue_limit_rejects_before_export(monkeypatch):
    monkeypatch.setattr(service.settings, 'subtitle_max_cues', 1, raising=False)
    raw = '1\n00:00:00,000 --> 00:00:01,000\nOne\n\n2\n00:00:01,000 --> 00:00:02,000\nTwo'
    with pytest.raises(SubtitleServiceError) as error:
        fetch_inline(monkeypatch, raw, 'srt')
    assert error.value.error_type == 'subtitle_too_large'


@pytest.fixture
def api(monkeypatch):
    from app.services import request_cache
    monkeypatch.setattr(request_cache, '_stores', {})
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_current_user] = lambda: SimpleNamespace(id='timeline-user')
    return TestClient(app)


def test_legacy_document_position_constructor_and_response_default(api, monkeypatch):
    doc = SubtitleDocument('title', 'en', False, ['en'], 'body')
    monkeypatch.setattr(routes, 'load_cached_subtitle', lambda *args: doc)
    result = api.post('/api/subtitle', json={'url': 'https://example.com/v'})
    assert result.status_code == 200
    assert result.json()['segments'] == []


@pytest.mark.parametrize('format_', ['srt', 'vtt'])
def test_export_reuses_read_cache_and_returns_plain_safe_file(api, monkeypatch, format_):
    calls = []
    doc = fetch_inline(monkeypatch, '1\n00:00:01,250 --> 00:00:02,500\n<b>Hello</b> &amp; world', 'srt')
    from dataclasses import replace
    doc = replace(doc, title='../bad:<title>\r\n/a')
    monkeypatch.setattr('app.routes.insight_common.fetch_subtitle_document', lambda *args: calls.append(args) or doc)
    body = {'url': 'https://example.com/v'}
    read = api.post('/api/subtitle', json=body)
    assert read.status_code == 200
    assert read.json()['segments'] == [{'start': 1.25, 'end': 2.5, 'text': 'Hello & world'}]
    result = api.post('/api/subtitle/export', json={**body, 'format': format_})
    assert result.status_code == 200
    payload = result.json()
    assert payload['format'] == format_
    assert payload['filename'].endswith('.' + format_)
    assert not any(char in payload['filename'] for char in '/\\<>:\r\n')
    assert 'Hello & world' in payload['content']
    assert '<b>' not in payload['content']
    assert ('00:00:01,250 --> 00:00:02,500' if format_ == 'srt' else '00:00:01.250 --> 00:00:02.500') in payload['content']
    assert len(calls) == 1


def test_export_requires_login_and_no_timing_is_explicit_422(api, monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    unauthenticated = TestClient(app)
    body = {'url': 'https://example.com/v', 'format': 'srt'}
    assert unauthenticated.post('/api/subtitle/export', json=body).status_code == 401
    monkeypatch.setattr(routes, 'load_cached_subtitle', lambda *args: SubtitleDocument('t', 'en', False, ['en'], 'plain'))
    response = api.post('/api/subtitle/export', json=body)
    assert response.status_code == 422
    assert response.json()['detail']['error_type'] == 'subtitle_timing_unavailable'


def test_export_rejects_unknown_format_before_loading(api, monkeypatch):
    monkeypatch.setattr(routes, 'load_cached_subtitle', lambda *args: pytest.fail('must not load'))
    assert api.post('/api/subtitle/export', json={'url': 'https://example.com/v', 'format': 'html'}).status_code == 422


@pytest.mark.parametrize('raw', [
    '1\n-00:00:01,000 --> 00:00:02,000\nHello',
    '1\n00:61:01,000 --> 00:62:02,000\nHello',
    '1\n00:00:02,000 --> 00:00:01,000\nHello',
    '1\n00:00:02,000 --> 00:00:03,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nWorld',
])
def test_invalid_srt_timestamps_are_not_silently_normalized(monkeypatch, raw):
    with pytest.raises(SubtitleServiceError) as error:
        fetch_inline(monkeypatch, raw, 'srt')
    assert error.value.error_type == 'subtitle_invalid'


def test_missing_timestamps_still_obey_cue_limit(monkeypatch):
    monkeypatch.setattr(service.settings, 'subtitle_max_cues', 1)
    raw = json.dumps({'events': [{'segs': [{'utf8': 'One'}]}, {'segs': [{'utf8': 'Two'}]}]})
    with pytest.raises(SubtitleServiceError) as error:
        fetch_inline(monkeypatch, raw, 'json3')
    assert error.value.error_type == 'subtitle_too_large'


def test_vtt_metadata_and_short_fractions_keep_only_speech(monkeypatch):
    raw = 'WEBVTT\n\nNOTE note\nnot spoken\n\nfirst\n00:00:01.2 --> 00:00:02.34 align:start\nHello\n\nlast\n00:00:02.340 --> 00:00:03.000\nWorld'
    doc = fetch_inline(monkeypatch, raw, 'vtt')
    assert [(cue.start, cue.end, cue.text) for cue in doc.segments] == [(1.2, 2.34, 'Hello'), (2.34, 3, 'World')]


def test_export_helpers_are_available_to_asr_and_refuse_clamped_times():
    from app.services.subtitle_timing import SubtitleSegment, TimingError, export_segments, safe_export_filename
    content = export_segments([SubtitleSegment(0, 1, 'Hello')], 'srt')
    assert '00:00:00,000 --> 00:00:01,000' in content
    assert safe_export_filename('CON', 'srt') == 'subtitle.srt'
    with pytest.raises(TimingError) as error:
        export_segments([SubtitleSegment(0, 1_000_000, 'Hello')], 'srt')
    assert error.value.error_type == 'subtitle_invalid'


@pytest.mark.parametrize('format_', ['srt', 'vtt'])
def test_plain_export_preserves_code_braces_and_literal_backslashes(format_):
    from app.services.subtitle_timing import SubtitleSegment, export_segments
    text = r'print({name}) and literal \N \h \n stay in one cue'
    content = export_segments([SubtitleSegment(0, 1, text)], format_)
    assert text in content
    assert content.count('-->') == 1


@pytest.mark.parametrize('ext', ['srt', 'vtt'])
def test_source_code_and_encoded_angles_survive_parse_then_export(monkeypatch, ext):
    from app.services.subtitle_timing import export_segments
    stamp = '00:00:00,000 --> 00:00:01,000' if ext == 'srt' else '00:00:00.000 --> 00:00:01.000'
    header = '1' if ext == 'srt' else 'WEBVTT\n\nfirst'
    payload = r"<b>print('\n')</b> vector&lt;int&gt; \N \h {name} {\b}"
    expected = r"print('\n') vector<int> \N \h {name} {\b}"
    doc = fetch_inline(monkeypatch, f'{header}\n{stamp}\n{payload}', ext)
    assert doc.segments[0].text == expected
    assert expected in export_segments(doc.segments, ext)


@pytest.mark.parametrize('text', ['a < b > c', '<div>', 'vector<int>', r'{\b} &lt;literal&gt; \n'])
@pytest.mark.parametrize('format_', ['srt', 'vtt'])
def test_asr_plain_segments_export_without_markup_or_entity_reinterpretation(text, format_):
    from app.services.subtitle_timing import SubtitleSegment, export_segments
    content = export_segments([SubtitleSegment(0, 1, text)], format_)
    assert text in content


@pytest.mark.parametrize('ext,raw', [
    ('ttml', r'<tt xmlns="http://www.w3.org/ns/ttml"><body><div><p begin="0s" end="1s">vector&lt;int&gt; \n</p></div></body></tt>'),
    ('srv3', r'<timedtext><body><p t="0" d="1000">vector&lt;int&gt; \n</p></body></timedtext>'),
])
def test_xml_payload_is_not_stripped_again_after_xml_decode(monkeypatch, ext, raw):
    from app.services.subtitle_timing import export_segments
    doc = fetch_inline(monkeypatch, raw, ext)
    assert doc.segments[0].text == r'vector<int> \n'
    assert r'vector<int> \n' in export_segments(doc.segments, 'srt')


@pytest.mark.parametrize('ext,text', [
    ('json3', 'vector<int>'),
    ('bilibili_json', 'a < b > c'),
    ('json3', 'literal &lt;tag&gt;'),
    ('bilibili_json', 'literal &amp;lt;tag&amp;gt;'),
])
@pytest.mark.parametrize('format_', ['srt', 'vtt'])
def test_plain_json_payloads_keep_angles_and_entities_through_export(monkeypatch, ext, text, format_):
    from app.services.subtitle_timing import export_segments
    payload = ({'events': [{'tStartMs': 0, 'dDurationMs': 1000, 'segs': [{'utf8': text}]}]}
               if ext == 'json3' else {'body': [{'from': 0, 'to': 1, 'content': text}]})
    doc = fetch_inline(monkeypatch, json.dumps(payload), ext)
    assert doc.segments[0].text == text
    assert text in export_segments(doc.segments, format_)
