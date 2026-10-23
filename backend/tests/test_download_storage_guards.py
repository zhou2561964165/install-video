from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings, settings
from app.models import Job, JobStatus
from app.services import jobs, ytdlp_service


@pytest.fixture
def storage(monkeypatch, tmp_path):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(jobs, 'engine', engine)
    monkeypatch.setattr(settings, 'temp_dir', tmp_path / 'media')
    monkeypatch.setattr(settings, 'max_file_size', 100)
    monkeypatch.setattr(settings, 'download_min_free_bytes', 0)
    with Session(engine) as session:
        job = Job(url='https://example.test/video', format_id='best')
        session.add(job)
        session.commit()
        session.refresh(job)
    return engine, job


def run_job(job):
    manager = jobs.JobManager(max_workers=1)
    try:
        manager._safe_run(job.id, job.url, job.format_id)
    finally:
        manager._executor.shutdown()


def test_low_disk_refuses_before_download(monkeypatch, storage):
    engine, job = storage
    monkeypatch.setattr(settings, 'download_min_free_bytes', 1024)
    monkeypatch.setattr(jobs.shutil, 'disk_usage', lambda _: SimpleNamespace(free=1023))
    monkeypatch.setattr(jobs, '_ytdlp_download', lambda *args: pytest.fail('download must not start'))
    run_job(job)
    with Session(engine) as session:
        result = session.get(Job, job.id)
        assert result.status == JobStatus.error
        assert result.error_type == 'quota'
    assert not (settings.temp_dir / job.id).exists()


def test_failure_removes_only_job_artifacts(monkeypatch, storage):
    engine, job = storage
    neighbor = settings.temp_dir / 'other-job'
    neighbor.mkdir(parents=True)
    protected = neighbor / 'keep.mp4'
    protected.write_bytes(b'keep')

    def failed(url, format_id, outtmpl, hook):
        directory = Path(outtmpl).parent
        (directory / 'video.f137.mp4.part').write_bytes(b'x' * 30)
        (directory / 'video.f140.m4a').write_bytes(b'y' * 20)
        raise RuntimeError('connection interrupted')

    monkeypatch.setattr(jobs, '_ytdlp_download', failed)
    run_job(job)
    assert not (settings.temp_dir / job.id).exists()
    assert protected.read_bytes() == b'keep'
    with Session(engine) as session:
        assert session.get(Job, job.id).error_type == 'network'


def test_final_oversize_removes_all_split_artifacts(monkeypatch, storage):
    engine, job = storage

    def oversized(url, format_id, outtmpl, hook):
        directory = Path(outtmpl).parent
        (directory / 'video.f140.m4a').write_bytes(b'x' * 20)
        output = directory / 'video.mp4'
        output.write_bytes(b'y' * 101)
        return str(output)

    monkeypatch.setattr(jobs, '_ytdlp_download', oversized)
    run_job(job)
    assert not (settings.temp_dir / job.id).exists()
    with Session(engine) as session:
        assert session.get(Job, job.id).error_type == 'quota'


def test_disk_reserve_is_rechecked_during_download(monkeypatch, storage):
    engine, job = storage
    monkeypatch.setattr(settings, 'download_min_free_bytes', 1024)
    free_space = iter((2048, 512))
    monkeypatch.setattr(jobs.shutil, 'disk_usage', lambda _: SimpleNamespace(free=next(free_space)))

    def running(url, format_id, outtmpl, hook):
        (Path(outtmpl).parent / 'partial.mp4.part').write_bytes(b'x')
        hook({'status': 'downloading', 'downloaded_bytes': 1})
        pytest.fail('download must abort at reserve threshold')

    monkeypatch.setattr(jobs, '_ytdlp_download', running)
    run_job(job)
    assert not (settings.temp_dir / job.id).exists()
    with Session(engine) as session:
        assert session.get(Job, job.id).error_type == 'quota'


def test_successful_job_retains_file_and_expiration(monkeypatch, storage):
    engine, job = storage

    def successful(url, format_id, outtmpl, hook):
        output = Path(outtmpl).parent / 'video.mp4'
        output.write_bytes(b'x' * 90)
        hook({'status': 'finished'})
        return str(output)

    monkeypatch.setattr(jobs, '_ytdlp_download', successful)
    run_job(job)
    with Session(engine) as session:
        result = session.get(Job, job.id)
        assert result.status == JobStatus.done
        assert result.progress == 100
        assert result.file_size == 90
        assert result.expires_at is not None
        assert Path(result.file_path).read_bytes() == b'x' * 90


def test_cleanup_rejects_parent_and_absolute_paths(monkeypatch, tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    monkeypatch.setattr(settings, 'temp_dir', root)
    protected = tmp_path / 'protected'
    protected.mkdir()
    (protected / 'keep').write_bytes(b'x')
    for job_id in ('..', '../protected', str(protected), '.', ''):
        jobs._cleanup_failed_download(job_id)
    assert (protected / 'keep').exists()
    assert root.exists()


def test_cleanup_rejects_symlink_to_neighbor(monkeypatch, tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    protected = root / 'other-job'
    protected.mkdir()
    (protected / 'keep').write_bytes(b'x')
    try:
        (root / 'failed-job').symlink_to(protected, target_is_directory=True)
    except OSError:
        pytest.skip('symlink creation unavailable')
    monkeypatch.setattr(settings, 'temp_dir', root)
    jobs._cleanup_failed_download('failed-job')
    assert (protected / 'keep').exists()


class FakeYDL:
    def __init__(self, opts, tmp_path, events):
        self.opts, self.tmp_path, self.events = opts, tmp_path, events

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download):
        assert self.opts['max_filesize'] == 100
        for event in self.events:
            self.opts['progress_hooks'][0](event)
        output = self.tmp_path / 'video.mp4'
        output.write_bytes(b'x' * 90)
        return {'filepath': str(output)}


@pytest.mark.parametrize('events', [
    [{'status': 'downloading', 'downloaded_bytes': 101}],
    [{'status': 'downloading', 'total_bytes_estimate': 101}],
    [{'status': 'finished', 'filename': 'video.mp4', 'downloaded_bytes': 101}],
    [{'status': 'finished', 'filename': 'video.f137.mp4', 'downloaded_bytes': 70},
     {'status': 'downloading', 'filename': 'video.f140.m4a', 'downloaded_bytes': 31}],
])
def test_progress_rejects_oversize_and_combined_streams(monkeypatch, tmp_path, events):
    monkeypatch.setattr(settings, 'max_file_size', 100)
    monkeypatch.setattr(ytdlp_service, '_youtube_dl', lambda opts: FakeYDL(opts, tmp_path, events))
    with pytest.raises(ytdlp_service.DownloadQuotaError) as failure:
        ytdlp_service.download('https://example.test/v', 'best', str(tmp_path / '%(title)s.%(ext)s'), lambda _: None)
    assert ytdlp_service.classify_error(failure.value) == 'quota'


def test_successful_split_download_preserves_progress(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'max_file_size', 100)
    events = [
        {'status': 'downloading', 'filename': 'video.f137.mp4', 'downloaded_bytes': 40},
        {'status': 'finished', 'filename': 'video.f137.mp4', 'downloaded_bytes': 60},
        {'status': 'finished', 'filename': 'video.f140.m4a', 'downloaded_bytes': 20},
    ]
    monkeypatch.setattr(ytdlp_service, '_youtube_dl', lambda opts: FakeYDL(opts, tmp_path, events))
    observed = []
    output = ytdlp_service.download('https://example.test/v', 'best', str(tmp_path / '%(title)s.%(ext)s'), observed.append)
    assert Path(output).is_file()
    assert observed == events


@pytest.mark.parametrize('metadata', [
    {'filesize': 101},
    {'filesize_approx': 101},
    {'requested_formats': [{'filesize': 80}, {'filesize': 30}]},
])
def test_ytdlp_size_skip_is_a_quota_error(monkeypatch, tmp_path, metadata):
    monkeypatch.setattr(settings, 'max_file_size', 100)

    class SkippedYDL(FakeYDL):
        def extract_info(self, url, download):
            return metadata

    monkeypatch.setattr(ytdlp_service, '_youtube_dl', lambda opts: SkippedYDL(opts, tmp_path, []))
    with pytest.raises(ytdlp_service.DownloadQuotaError):
        ytdlp_service.download('https://example.test/v', 'best', str(tmp_path / '%(title)s.%(ext)s'), lambda _: None)


def test_wrapped_quota_error_retains_classification():
    from yt_dlp.utils import DownloadError
    original = ytdlp_service.DownloadQuotaError('storage exhausted')
    wrapped = DownloadError('download failed', exc_info=(type(original), original, None))
    assert ytdlp_service.classify_error(wrapped) == 'quota'


def test_download_disk_setting_is_opt_in_and_configurable(monkeypatch):
    assert Settings().download_min_free_bytes == 0
    monkeypatch.setenv('DOWNLOAD_MIN_FREE_BYTES', '1073741824')
    assert Settings.from_env().download_min_free_bytes == 1073741824
    for invalid in (-1, True, 1.5):
        with pytest.raises(ValueError, match='download_min_free_bytes'):
            Settings(download_min_free_bytes=invalid)
