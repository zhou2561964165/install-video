"""Function-only B5 terminal contracts. Run with the reviewed offline harness.

No ASGI, real engine/session, worker, subprocess, source request or model.
"""
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.routes import download, insight_common, parse, transcribe
from app.schemas import DownloadRequest, DownloadResponse, ParseRequest
from app.models import JobStatus
from app.services import asr_service, jobs
from app.services.asr_errors import ASRError
from app.services.bilibili_session import SessionError
from app.services.outbound_budget import BudgetReason, OutboundBudgetError
from app.services.outbound_httpx import ControlledHttpBusyError, ControlledHttpError, ControlledHttpStatusError
from app.services.outbound_policy import OutboundError, OutboundPolicyError, OutboundPurpose, OutboundUnavailableError
from app.services.subtitle_service import SubtitleServiceError

CANARIES = ('B5_TERMINAL_QUERY_CANARY', 'B5_TERMINAL_HEADER_CANARY', 'B5_TERMINAL_BODY_CANARY')
URL = 'https://www.youtube.com/watch?v=offline1234&synthetic=' + CANARIES[0]
USER = SimpleNamespace(id='b5-synthetic-user')
CASES = ['invalid', 'blocked', 'unavailable', 'busy'] + [f'http-{n}' for n in (401, 403, 412, 502, 503)]
CASES += ['budget-' + reason.value for reason in BudgetReason]
CASES += ['subtitle-' + reason.value for reason in (BudgetReason.RAW_BYTES, BudgetReason.DECODED_BYTES,
                                                   BudgetReason.RESPONSE_RAW_BYTES, BudgetReason.RESPONSE_DECODED_BYTES)]


@pytest.fixture(params=CASES)
def terminal_case(request):
    case = request.param
    if case == 'invalid':
        return OutboundPolicyError(invalid=True)
    if case == 'blocked':
        return OutboundPolicyError()
    if case == 'unavailable':
        return OutboundUnavailableError()
    if case == 'busy':
        return ControlledHttpBusyError()
    kind, value = case.split('-', 1)
    if kind == 'http':
        return ControlledHttpStatusError(int(value))
    return OutboundBudgetError(BudgetReason(value), OutboundPurpose.SUBTITLE if kind == 'subtitle' else OutboundPurpose.METADATA)


def assert_safe(value, caplog):
    """Inspect all visible causes/contexts/args, not just suppressed display."""
    seen, pieces = set(), []
    def visit(item):
        if id(item) in seen:
            return
        seen.add(id(item))
        if isinstance(item, BaseException):
            assert isinstance(item, (HTTPException, OutboundError, ControlledHttpError))
            visit(item.args)
            visit(getattr(item, 'detail', None))
            visit(vars(item))
            visit(item.__cause__)
            visit(item.__context__)
        elif isinstance(item, dict):
            for key, content in item.items():
                visit(key)
                visit(content)
        elif isinstance(item, (tuple, list)):
            for content in item:
                visit(content)
        else:
            pieces.append(str(item))
    visit(value)
    pieces.append(caplog.text)
    text = '\n'.join(pieces)
    assert not any(canary in text for canary in CANARIES)


def assert_http(caught, source, caplog):
    error = caught.value
    assert error.status_code == source.status_code
    assert error.detail == source.public_detail()
    assert error.__context__ is source
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    assert_safe(error, caplog)


def safe_legacy_spies(monkeypatch, module):
    classifier, message = Mock(return_value='legacy'), Mock(return_value='legacy message')
    monkeypatch.setattr(module, 'classify_error', classifier)
    monkeypatch.setattr(module, 'public_error_message', message)
    return classifier, message


def test_parse_terminal_priority(monkeypatch, terminal_case, caplog):
    source = Mock(side_effect=terminal_case)
    monkeypatch.setattr(parse, 'parse_video', source)
    classifier, message = safe_legacy_spies(monkeypatch, parse)
    with pytest.raises(HTTPException) as caught:
        parse.parse(ParseRequest(url=URL), USER)
    assert_http(caught, terminal_case, caplog)
    source.assert_called_once_with(URL)
    classifier.assert_not_called()
    message.assert_not_called()


class FakeSession:
    def __init__(self, dialect='sqlite', job=None):
        self.dialect, self.job = dialect, job
        self.calls = Counter()
        self.added = []
    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name=self.dialect))
    def add(self, value):
        self.added.append(value)
    def commit(self):
        self.calls['commit'] += 1
    def rollback(self):
        self.calls['rollback'] += 1
    def refresh(self, value):
        self.calls['refresh'] += 1
    def get(self, model, key):
        self.calls['get'] += 1
        return self.job
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


@pytest.fixture
def download_env(monkeypatch):
    session = FakeSession()
    recorder = SimpleNamespace(cleanup_expired=Mock(), submit_download=Mock())
    monkeypatch.setattr(download, 'job_manager', recorder)
    monkeypatch.setattr(download, 'max_height', Mock(return_value=None))
    monkeypatch.setattr(download, 'check_and_reserve', Mock())
    monkeypatch.setattr(download.ytdlp_service, 'restrict_format', Mock(return_value='bounded'))
    monkeypatch.setattr(download.ytdlp_service, 'requires_server_download', Mock(return_value=False))
    monkeypatch.setattr(download.ytdlp_service, 'get_direct_url', Mock(return_value=('https://media.example/public', {})))
    monkeypatch.setattr(download.ytdlp_service, 'parse_video', Mock(side_effect=AssertionError('extra parse forbidden')))
    return session, recorder


def request_download(session, key=None, force_server=False):
    return download.download(DownloadRequest(url=URL, format_id='chosen', force_server=force_server), session, USER, key)


def test_download_height_terminal_before_receipt(monkeypatch, download_env, terminal_case, caplog):
    session, recorder = download_env
    monkeypatch.setattr(download, 'max_height', Mock(return_value=720))
    download.ytdlp_service.restrict_format.side_effect = terminal_case
    reserve = Mock()
    monkeypatch.setattr(download.download_idempotency, 'reserve', reserve)
    with pytest.raises(HTTPException) as caught:
        request_download(session, 'synthetic-key')
    assert_http(caught, terminal_case, caplog)
    reserve.assert_not_called()
    download.ytdlp_service.restrict_format.assert_called_once_with(URL, 'chosen', 720)
    download.ytdlp_service.get_direct_url.assert_not_called()
    download.ytdlp_service.parse_video.assert_not_called()
    download.check_and_reserve.assert_not_called()
    recorder.cleanup_expired.assert_not_called()
    recorder.submit_download.assert_not_called()
    assert not session.added


def test_download_direct_terminal_finishes_receipt(monkeypatch, download_env, terminal_case, caplog):
    session, recorder = download_env
    download.ytdlp_service.get_direct_url.side_effect = terminal_case
    reserve, fail, complete = Mock(return_value=SimpleNamespace(response=None, record_id='receipt')), Mock(return_value=True), Mock()
    monkeypatch.setattr(download.download_idempotency, 'reserve', reserve)
    monkeypatch.setattr(download.download_idempotency, 'fail', fail)
    monkeypatch.setattr(download.download_idempotency, 'complete', complete)
    with pytest.raises(HTTPException) as caught:
        request_download(session, 'synthetic-key')
    assert_http(caught, terminal_case, caplog)
    assert caught.value.headers == {'Idempotency-Status': 'complete'}
    fail.assert_called_once_with(session, 'receipt', caught.value)
    assert_safe(fail.call_args.args[2], caplog)
    complete.assert_not_called()
    recorder.submit_download.assert_not_called()
    download.ytdlp_service.get_direct_url.assert_called_once_with(URL, 'chosen')
    download.ytdlp_service.parse_video.assert_not_called()
    recorder.cleanup_expired.assert_called_once()
    download.check_and_reserve.assert_called_once_with(session, USER.id)
    assert not session.added
    assert session.calls['rollback'] == 0


def test_download_direct_terminal_without_receipt(monkeypatch, download_env, terminal_case, caplog):
    session, recorder = download_env
    download.ytdlp_service.get_direct_url.side_effect = terminal_case
    fail, reserve = Mock(), Mock()
    monkeypatch.setattr(download.download_idempotency, 'fail', fail)
    monkeypatch.setattr(download.download_idempotency, 'reserve', reserve)
    with pytest.raises(HTTPException) as caught:
        request_download(session)
    assert_http(caught, terminal_case, caplog)
    assert caught.value.headers is None
    fail.assert_not_called()
    reserve.assert_not_called()
    recorder.submit_download.assert_not_called()
    download.ytdlp_service.parse_video.assert_not_called()
    download.ytdlp_service.get_direct_url.assert_called_once()
    assert not session.added


def test_subtitle_terminal_stops_consumer(monkeypatch, terminal_case, caplog):
    source = Mock(side_effect=terminal_case)
    monkeypatch.setattr(insight_common, 'fetch_subtitle_document', source)
    downstream_asr, downstream_model = Mock(), Mock()
    with pytest.raises(HTTPException) as caught:
        document = insight_common.load_subtitle(URL, 'en')
        downstream_asr(document)
        downstream_model(document)
    assert_http(caught, terminal_case, caplog)
    source.assert_called_once_with(URL, 'en')
    downstream_asr.assert_not_called()
    downstream_model.assert_not_called()


def test_transcribe_route_terminal(monkeypatch, terminal_case, caplog):
    source = Mock(side_effect=terminal_case)
    monkeypatch.setattr(transcribe.asr_service, 'transcribe_video', source)
    reuse = Mock(side_effect=lambda namespace, uid, parameters, producer: producer())
    monkeypatch.setattr(transcribe, 'reuse', reuse)
    with pytest.raises(HTTPException) as caught:
        transcribe.transcribe(transcribe.TranscribeRequest(url=URL, language='en'), USER)
    assert_http(caught, terminal_case, caplog)
    source.assert_called_once_with(URL, 'en')
    reuse.assert_called_once()


@pytest.fixture
def asr_env(monkeypatch, tmp_path):
    monkeypatch.setattr(asr_service, 'capabilities', Mock(return_value={'available': True}))
    monkeypatch.setattr(asr_service.settings, 'temp_dir', tmp_path / 'audio')
    monkeypatch.setattr(asr_service, '_active', 0)
    decode, model = Mock(), Mock()
    monkeypatch.setattr(asr_service, '_check_audio_duration', decode)
    monkeypatch.setattr(asr_service, '_get_model', model)
    return decode, model, asr_service.settings.temp_dir


def test_asr_service_terminal_releases_and_cleans(monkeypatch, asr_env, terminal_case, caplog):
    decode, model, root = asr_env
    source = Mock(side_effect=terminal_case)
    monkeypatch.setattr(asr_service.ytdlp_service, 'fetch_transcription_audio', source)
    with pytest.raises((OutboundError, ControlledHttpError)) as caught:
        asr_service.transcribe_video(URL, 'en')
    assert caught.value is terminal_case
    assert_safe(caught.value, caplog)
    source.assert_called_once()
    decode.assert_not_called()
    model.assert_not_called()
    assert asr_service._active == 0
    assert list(root.iterdir()) == []


def test_lower_source_through_real_acquisition_asr_and_route(monkeypatch, asr_env, terminal_case, caplog):
    """T0 composition: replace only the lower extractor context manager."""
    decode, model, root = asr_env
    calls = Counter()
    class Extractor:
        def __enter__(self):
            calls['enter'] += 1
            return self
        def __exit__(self, *args):
            calls['exit'] += 1
        def extract_info(self, url, download):
            calls['extract'] += 1
            assert url == URL and download is False
            raise terminal_case
        def process_info(self, info):
            calls['process'] += 1
            raise AssertionError('terminal source reached media work')
    factory = Mock(return_value=Extractor())
    monkeypatch.setattr(asr_service.ytdlp_service, '_source_youtube_dl', factory)
    monkeypatch.setattr(transcribe, 'reuse', lambda namespace, uid, parameters, producer: producer())
    with pytest.raises(HTTPException) as caught:
        transcribe.transcribe(transcribe.TranscribeRequest(url=URL, language='en'), USER)
    assert_http(caught, terminal_case, caplog)
    factory.assert_called_once()
    assert calls == {'enter': 1, 'extract': 1, 'exit': 1}
    decode.assert_not_called()
    model.assert_not_called()
    assert asr_service._active == 0 and not list(root.iterdir())


def test_legacy_job_safe_run_terminal(monkeypatch, terminal_case, caplog):
    job = SimpleNamespace(status=JobStatus.queued, error_type=None, error=None)
    session = FakeSession(job=job)
    manager = object.__new__(jobs.JobManager)
    manager._lock = nullcontext()
    manager._executor = SimpleNamespace(submit=Mock())
    monkeypatch.setattr(jobs, 'Session', lambda engine: session)
    order = []
    def fail_run(*args):
        order.append('run')
        raise terminal_case
    run, cleanup = Mock(side_effect=fail_run), Mock(side_effect=lambda *args: order.append('cleanup'))
    original_mark = manager._mark_error
    def mark_error(*args):
        order.append('mark')
        original_mark(*args)
    manager._mark_error = mark_error
    original_commit = session.commit
    def commit():
        order.append('commit')
        original_commit()
    session.commit = commit
    monkeypatch.setattr(jobs, '_run_download', run)
    monkeypatch.setattr(jobs, '_cleanup_failed_download', cleanup)
    classifier, message = safe_legacy_spies(monkeypatch, jobs)
    manager._safe_run('job', URL, 'chosen')
    run.assert_called_once_with('job', URL, 'chosen')
    cleanup.assert_called_once_with('job')
    assert job.status is JobStatus.error
    assert job.error_type == terminal_case.code
    assert job.error == terminal_case.message
    assert set(vars(job)) == {'status', 'error_type', 'error', 'updated_at'}
    assert session.calls['commit'] == 1
    assert session.calls['get'] == 1
    assert session.added == [job]
    assert order == ['run', 'cleanup', 'mark', 'commit']
    classifier.assert_not_called()
    message.assert_not_called()
    manager._executor.submit.assert_not_called()
    assert_safe([job.error_type, job.error, terminal_case], caplog)


def test_parse_legacy_failure_and_success(monkeypatch):
    classifier, message = safe_legacy_spies(monkeypatch, parse)
    ordinary = RuntimeError('ordinary failure')
    source = Mock(side_effect=ordinary)
    monkeypatch.setattr(parse, 'parse_video', source)
    with pytest.raises(HTTPException) as caught:
        parse.parse(ParseRequest(url=URL), USER)
    assert caught.value.status_code == 422
    assert caught.value.detail == {'error_type': 'legacy', 'error': 'legacy message'}
    classifier.assert_called_once_with(ordinary)
    message.assert_called_once_with(ordinary)
    source.side_effect = None
    source.return_value = ({'title': 'synthetic title', 'thumbnail': None, 'duration': 1}, [{'format_id': 'ok', 'label': 'ok'}])
    assert parse.parse(ParseRequest(url=URL), USER).formats[0].format_id == 'ok'


@pytest.mark.parametrize('case,code,status', [('value', 'membership_required', 403), ('session', 'verification_required', 422), ('generic', 'format_unverified', 422)])
def test_download_legacy_height_failures(monkeypatch, download_env, case, code, status):
    session, recorder = download_env
    monkeypatch.setattr(download, 'max_height', Mock(return_value=720))
    errors = {'value': ValueError(), 'session': SessionError('unavailable'), 'generic': RuntimeError()}
    download.ytdlp_service.restrict_format.side_effect = errors[case]
    with pytest.raises(HTTPException) as caught:
        request_download(session)
    assert caught.value.status_code == status
    assert caught.value.detail['error_type'] == code
    recorder.submit_download.assert_not_called()


def test_download_legacy_direct_fallback_and_success(download_env):
    session, recorder = download_env
    assert request_download(session).mode == 'direct'
    assert not session.added
    download.ytdlp_service.get_direct_url.side_effect = RuntimeError('ordinary direct failure')
    assert request_download(session).mode == 'server'
    recorder.submit_download.assert_called_once()
    assert len(session.added) == 2
    assert session.calls['commit'] == 2


def test_download_replay_after_canonical_height_check(monkeypatch, download_env):
    session, recorder = download_env
    monkeypatch.setattr(download, 'max_height', Mock(return_value=720))
    cached = DownloadResponse(mode='server', job_id='existing')
    def reserve(s, uid, key, request):
        assert download.ytdlp_service.restrict_format.call_count == 1
        assert request.format_id == 'bounded'
        return SimpleNamespace(response=cached, record_id='existing-receipt')
    monkeypatch.setattr(download.download_idempotency, 'reserve', reserve)
    assert request_download(session, 'synthetic-key') is cached
    download.check_and_reserve.assert_not_called()
    download.ytdlp_service.get_direct_url.assert_not_called()
    recorder.submit_download.assert_not_called()
    assert not session.added


def test_download_success_receipt_completes(monkeypatch, download_env):
    session, _ = download_env
    complete, fail = Mock(), Mock()
    monkeypatch.setattr(download.download_idempotency, 'reserve', Mock(return_value=SimpleNamespace(response=None, record_id='receipt')))
    monkeypatch.setattr(download.download_idempotency, 'complete', complete)
    monkeypatch.setattr(download.download_idempotency, 'fail', fail)
    response = request_download(session, 'synthetic-key')
    complete.assert_called_once_with(session, 'receipt', response)
    fail.assert_not_called()


def test_queue_acceptance_remains_uncertain(monkeypatch, download_env):
    session, recorder = download_env
    recorder.submit_download.side_effect = OutboundUnavailableError()
    fail = Mock()
    monkeypatch.setattr(download.download_idempotency, 'reserve', Mock(return_value=SimpleNamespace(response=None, record_id='receipt')))
    monkeypatch.setattr(download.download_idempotency, 'fail', fail)
    with pytest.raises(HTTPException) as caught:
        request_download(session, 'synthetic-key', force_server=True)
    assert caught.value.detail['error_type'] == 'idempotency_uncertain'
    assert session.calls['rollback'] == 1
    recorder.submit_download.assert_called_once()
    fail.assert_called_once_with(session, 'receipt', caught.value)


def test_postgres_route_stays_closed(download_env):
    session, recorder = download_env
    session.dialect = 'postgresql'
    with pytest.raises(HTTPException) as caught:
        request_download(session)
    assert caught.value.status_code == 503
    download.max_height.assert_not_called()
    download.ytdlp_service.restrict_format.assert_not_called()
    download.ytdlp_service.get_direct_url.assert_not_called()
    recorder.submit_download.assert_not_called()


def test_subtitle_legacy_error_and_success(monkeypatch):
    source = Mock(side_effect=SubtitleServiceError('missing', 'ordinary subtitle failure'))
    monkeypatch.setattr(insight_common, 'fetch_subtitle_document', source)
    with pytest.raises(HTTPException) as caught:
        insight_common.load_subtitle(URL, 'en')
    assert caught.value.status_code == 422
    assert caught.value.detail['error_type'] == 'missing'
    source.side_effect = RuntimeError('ordinary failure')
    monkeypatch.setattr(insight_common.ytdlp_service, 'classify_error', Mock(return_value='legacy'))
    with pytest.raises(HTTPException) as caught:
        insight_common.load_subtitle(URL, 'en')
    assert caught.value.detail['error_type'] == 'legacy'
    source.side_effect, source.return_value = None, object()
    assert insight_common.load_subtitle(URL, 'en') is source.return_value


@pytest.mark.parametrize('code,status', [('transcription_failed', 422), ('transcription_unavailable', 503), ('transcription_busy', 503)])
def test_transcription_legacy_asr_mapping(monkeypatch, code, status):
    monkeypatch.setattr(transcribe, 'reuse', lambda namespace, uid, parameters, producer: producer())
    monkeypatch.setattr(transcribe.asr_service, 'transcribe_video', Mock(side_effect=ASRError(code, 'ordinary ASR failure')))
    with pytest.raises(HTTPException) as caught:
        transcribe.transcribe(transcribe.TranscribeRequest(url=URL), USER)
    assert caught.value.status_code == status
    assert caught.value.detail['error_type'] == code


def test_export_miss_never_acquires_audio(monkeypatch):
    monkeypatch.setattr(transcribe, 'lookup_reused', Mock(return_value=None))
    source = Mock()
    monkeypatch.setattr(transcribe.asr_service, 'transcribe_video', source)
    with pytest.raises(HTTPException) as caught:
        transcribe.export_transcription(transcribe.TranscriptionExportRequest(url=URL, format='srt'), USER)
    assert caught.value.status_code == 422
    source.assert_not_called()


def test_asr_legacy_failure_and_success(monkeypatch, asr_env):
    decode, model, root = asr_env
    source = Mock(side_effect=RuntimeError('ordinary failure'))
    monkeypatch.setattr(asr_service.ytdlp_service, 'fetch_transcription_audio', source)
    with pytest.raises(ASRError) as caught:
        asr_service.transcribe_video(URL)
    assert caught.value.error_type == 'transcription_failed'
    assert asr_service._active == 0 and not list(root.iterdir())
    source.side_effect = None
    source.return_value = (Path('synthetic-audio'), 'synthetic title')
    model.return_value.transcribe.return_value = ([SimpleNamespace(start=0, end=1, text=' hello ')], SimpleNamespace(language='en'))
    result = asr_service.transcribe_video(URL)
    assert result.text == 'hello'
    assert result.segments == [{'start': 0, 'end': 1, 'text': 'hello'}]
    assert asr_service._active == 0 and not list(root.iterdir())


def test_job_legacy_classifier_kept(monkeypatch):
    job = SimpleNamespace(status=JobStatus.queued)
    session = FakeSession(job=job)
    manager = object.__new__(jobs.JobManager)
    manager._lock = nullcontext()
    monkeypatch.setattr(jobs, 'Session', lambda engine: session)
    classifier, message = safe_legacy_spies(monkeypatch, jobs)
    ordinary = RuntimeError('ordinary failure')
    manager._mark_error('job', ordinary)
    classifier.assert_called_once_with(ordinary)
    message.assert_called_once_with(ordinary)
    assert (job.status, job.error_type, job.error) == (JobStatus.error, 'legacy', 'legacy message')
    assert session.calls['commit'] == 1
