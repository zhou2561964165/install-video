"""C2 Task 2: attempt-owned media files (pure filesystem, temporary roots only)."""
import hashlib
import json
import os
from pathlib import Path
import uuid

import pytest

from app.services import artifact_store as store

JOB, ATTEMPT = str(uuid.uuid4()), str(uuid.uuid4())


@pytest.fixture
def root(tmp_path):
    media = tmp_path / 'media'
    media.mkdir()
    store.provision_root(media.resolve())  # operators provision the media root once (C5a review I2)
    return media.resolve()


def write_part(paths, data=b'synthetic-media-bytes'):
    paths.part.write_bytes(data)
    return data


def test_prepare_seal_writes_media_and_manifest(root):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    assert paths.directory == root / JOB / f'1-{ATTEMPT}' and paths.directory.is_dir()
    data = write_part(paths)
    candidate = store.seal_candidate(paths, ext='mp4', max_bytes=1024, media_check='verified')
    final = paths.directory / 'media.mp4'
    assert final.read_bytes() == data and not paths.part.exists()
    assert candidate.sha256 == hashlib.sha256(data).hexdigest() and candidate.byte_size == len(data)
    assert candidate.relative_path == f'{JOB}/1-{ATTEMPT}/media.mp4'
    assert (candidate.job_id, candidate.epoch, candidate.attempt_id) == (JOB, 1, ATTEMPT)
    manifest = json.loads((paths.directory / 'manifest.json').read_text('utf8'))
    assert manifest == dict(job_id=JOB, epoch=1, attempt_id=ATTEMPT, relative_path=candidate.relative_path,
                            byte_size=len(data), sha256=candidate.sha256, media_format='mp4', media_check='verified')
    assert not (paths.directory / 'manifest.part').exists()


def test_prepare_refuses_existing_attempt_directory(root):
    store.prepare_attempt(root, JOB, 1, ATTEMPT)
    with pytest.raises(store.ArtifactError):
        store.prepare_attempt(root, JOB, 1, ATTEMPT)


def test_separate_epochs_get_separate_directories(root):
    first = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    second = store.prepare_attempt(root, JOB, 2, str(uuid.uuid4()))
    assert first.directory != second.directory and first.directory.parent == second.directory.parent


def test_seal_refuses_existing_final(root):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    write_part(paths, b'new')
    (paths.directory / 'media.mp4').write_bytes(b'someone-else')
    with pytest.raises(store.ArtifactError):
        store.seal_candidate(paths, ext='mp4', max_bytes=1024, media_check='verified')
    assert (paths.directory / 'media.mp4').read_bytes() == b'someone-else'
    assert paths.part.read_bytes() == b'new'
    assert not (paths.directory / 'manifest.json').exists()


@pytest.mark.parametrize('size,accepted', [(10, True), (11, False), (0, False)])
def test_size_boundary(root, size, accepted):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    write_part(paths, b'x' * size)
    if accepted:
        assert store.seal_candidate(paths, ext='mp4', max_bytes=10, media_check='verified').byte_size == size
    else:
        with pytest.raises(store.ArtifactError):
            store.seal_candidate(paths, ext='mp4', max_bytes=10, media_check='verified')
        assert not (paths.directory / 'media.mp4').exists()


def test_missing_part_has_no_candidate(root):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    with pytest.raises(store.ArtifactError):
        store.seal_candidate(paths, ext='mp4', max_bytes=10, media_check='verified')


@pytest.mark.parametrize('args', [
    dict(job_id='../escape'), dict(job_id='a/b'), dict(job_id=''), dict(attempt_id='x' * 65),
    dict(epoch=0), dict(epoch=True), dict(epoch='1')], ids=['dotdot', 'slash', 'empty', 'long', 'zero', 'bool', 'str'])
def test_invalid_segments_refused(root, args):
    values = dict(job_id=JOB, epoch=1, attempt_id=ATTEMPT) | args
    with pytest.raises(store.ArtifactError):
        store.prepare_attempt(root, values['job_id'], values['epoch'], values['attempt_id'])


@pytest.mark.parametrize('ext,check', [('MP4', 'verified'), ('m p4', 'verified'), ('mp4/../x', 'verified'),
                                       ('mp4', 'unverified'), ('', 'verified')])
def test_invalid_ext_or_check_refused(root, ext, check):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    write_part(paths)
    with pytest.raises(store.ArtifactError):
        store.seal_candidate(paths, ext=ext, max_bytes=1024, media_check=check)


def test_root_must_be_absolute_existing_directory(tmp_path):
    for value in (Path('relative'), tmp_path / 'missing', str(tmp_path)):
        with pytest.raises(store.ArtifactError):
            store.prepare_attempt(value, JOB, 1, ATTEMPT)


@pytest.mark.skipif(os.name != 'nt', reason='junction test is Windows-specific')
def test_junction_job_directory_refused(root, tmp_path):
    import _winapi
    outside = tmp_path / 'outside'
    outside.mkdir()
    _winapi.CreateJunction(str(outside), str(root / JOB))
    with pytest.raises(store.ArtifactError):
        store.prepare_attempt(root, JOB, 1, ATTEMPT)
    assert list(outside.iterdir()) == []


@pytest.mark.skipif(os.name != 'nt', reason='junction test is Windows-specific')
def test_junction_root_refused(tmp_path):
    import _winapi
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'link'
    _winapi.CreateJunction(str(real), str(link))
    with pytest.raises(store.ArtifactError):
        store.prepare_attempt(link, JOB, 1, ATTEMPT)


# C2 review I4: POSIX symlink escapes (production runs on Linux; run these there).
posix_only = pytest.mark.skipif(os.name == 'nt', reason='POSIX symlink test (Windows uses junction tests)')


@posix_only
def test_symlink_root_refused(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(store.ArtifactError):
        store.prepare_attempt(link, JOB, 1, ATTEMPT)
    assert list(real.iterdir()) == []


@posix_only
def test_symlink_job_directory_refused(root, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / JOB).symlink_to(outside, target_is_directory=True)
    with pytest.raises(store.ArtifactError):
        store.prepare_attempt(root, JOB, 1, ATTEMPT)
    assert list(outside.iterdir()) == []


@posix_only
def test_symlink_part_file_refused(root, tmp_path):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    outside = tmp_path / 'outside.bin'
    outside.write_bytes(b'not-this-attempt')
    paths.part.symlink_to(outside)
    with pytest.raises(store.ArtifactError) as error:
        store.seal_candidate(paths, ext='mp4', max_bytes=1024, media_check='verified')
    assert str(error.value) == 'artifact_path_unsafe'
    assert outside.read_bytes() == b'not-this-attempt' and not (paths.directory / 'media.mp4').exists()


@posix_only
def test_attempt_directory_swapped_for_symlink_refused(root, tmp_path):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'media.part').write_bytes(b'synthetic-media-bytes')
    paths.directory.rmdir()
    paths.directory.symlink_to(outside, target_is_directory=True)
    with pytest.raises(store.ArtifactError):
        store.seal_candidate(paths, ext='mp4', max_bytes=1024, media_check='verified')
    with pytest.raises(store.ArtifactError):
        store.remove_own_attempt(paths)
    assert sorted(entry.name for entry in outside.iterdir()) == ['media.part']


def test_remove_own_attempt_keeps_siblings(root):
    mine = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    sibling = store.prepare_attempt(root, JOB, 2, str(uuid.uuid4()))
    write_part(mine)
    write_part(sibling)
    store.remove_own_attempt(mine)
    assert not mine.directory.exists()
    assert sibling.part.exists() and (root / JOB).is_dir()


def test_remove_own_attempt_refuses_unknown_entries(root):
    mine = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    (mine.directory / 'unexpected.bin').write_bytes(b'x')
    with pytest.raises(store.ArtifactError):
        store.remove_own_attempt(mine)
    assert (mine.directory / 'unexpected.bin').exists()


def test_candidate_repr_has_no_paths_or_hash_secrets(root):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    write_part(paths)
    candidate = store.seal_candidate(paths, ext='mp4', max_bytes=1024, media_check='verified')
    assert str(root) not in repr(paths) and str(root) not in repr(candidate)


# C2 review I3: the bytes that were hashed must be exactly the bytes renamed to media.<ext>.
def test_writer_appending_after_hash_is_refused(root, monkeypatch):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    write_part(paths)
    real_fsync = os.fsync

    def late_writer(descriptor):
        with open(paths.part, 'ab') as other:  # a surviving writer (e.g. a merger child) appends
            other.write(b'late')
        real_fsync(descriptor)

    monkeypatch.setattr(store.os, 'fsync', late_writer)
    with pytest.raises(store.ArtifactError) as error:
        store.seal_candidate(paths, ext='mp4', max_bytes=1024, media_check='verified')
    assert str(error.value) == 'artifact_changed'
    assert not (paths.directory / 'media.mp4').exists() and not (paths.directory / 'manifest.json').exists()


def test_hard_linked_part_is_refused(root, tmp_path):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    write_part(paths)
    os.link(paths.part, tmp_path / 'outside-alias')  # another name could keep changing the bytes
    with pytest.raises(store.ArtifactError) as error:
        store.seal_candidate(paths, ext='mp4', max_bytes=1024, media_check='verified')
    assert str(error.value) == 'artifact_path_unsafe'
    assert not (paths.directory / 'media.mp4').exists()


def test_final_swapped_after_rename_is_refused(root, tmp_path, monkeypatch):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    write_part(paths)
    real_rename = store._rename_no_overwrite

    def swapped(source, target):
        real_rename(source, target)
        if target.name.startswith('media.'):
            # Keep the original inode alive elsewhere so the replacement cannot reuse it (ext4).
            target.rename(tmp_path / 'kept-original')
            target.write_bytes(b'synthetic-media-bytes')  # same size and content, different file
    monkeypatch.setattr(store, '_rename_no_overwrite', swapped)
    with pytest.raises(store.ArtifactError) as error:
        store.seal_candidate(paths, ext='mp4', max_bytes=1024, media_check='verified')
    assert str(error.value) == 'artifact_changed'
    assert not (paths.directory / 'manifest.json').exists()


# C2 review I4: a worker checks once at startup that media_root supports the no-overwrite rename.
def test_probe_root_accepts_supported_root_and_leaves_nothing(root):
    store.probe_root(root)
    assert [entry.name for entry in root.iterdir()] == [store.ROOT_MARKER]  # only the provisioned marker


def test_probe_root_refuses_root_without_no_overwrite_rename(root, monkeypatch):
    def unsupported(source, target):
        raise OSError('operation not supported')  # e.g. a mount without hard links
    monkeypatch.setattr(store, '_rename_no_overwrite', unsupported)
    with pytest.raises(store.ArtifactError) as error:
        store.probe_root(root)
    assert str(error.value) == 'artifact_root_unsupported'
    assert [entry.name for entry in root.iterdir()] == [store.ROOT_MARKER]  # only the provisioned marker


# C2 fix re-review M1: a read-only root fails cleanup too; the error must stay fixed and path-free.
def test_probe_root_on_read_only_root_raises_fixed_path_free_error(root, monkeypatch):
    def read_only_open(*args, **kwargs):
        raise OSError(30, 'Read-only file system', str(root / '.probe-x.part'))

    def read_only_unlink(self, *args, **kwargs):
        raise OSError(30, 'Read-only file system', str(self))
    monkeypatch.setattr(store, 'open', read_only_open, raising=False)
    monkeypatch.setattr(store.Path, 'unlink', read_only_unlink)
    with pytest.raises(store.ArtifactError) as error:
        store.probe_root(root)
    assert str(error.value) == 'artifact_root_unsupported'
    assert error.value.__context__ is None and error.value.__cause__ is None


# C2 fix re-review M2: the probe also proves the rename keeps the file identity seal relies on.
def test_probe_root_refuses_root_where_identity_is_not_preserved(root, tmp_path, monkeypatch):
    real_rename = store._rename_no_overwrite

    def unstable(source, target):
        real_rename(source, target)
        target.rename(tmp_path / 'kept-original')
        target.write_bytes(b'probe')  # e.g. a mount reporting unstable inode/device numbers
    monkeypatch.setattr(store, '_rename_no_overwrite', unstable)
    with pytest.raises(store.ArtifactError) as error:
        store.probe_root(root)
    assert str(error.value) == 'artifact_root_unsupported'
    assert [entry.name for entry in root.iterdir()] == [store.ROOT_MARKER]  # only the provisioned marker


# C3 review M7: an OS error while listing the attempt directory stays a fixed, path-free code.
def test_remove_own_attempt_listing_error_is_fixed_code(root, monkeypatch):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)

    def failing(self):
        raise OSError(13, 'Permission denied', str(self))
    monkeypatch.setattr(store.Path, 'iterdir', failing)
    with pytest.raises(store.ArtifactError) as error:
        store.remove_own_attempt(paths)
    assert str(error.value) == 'artifact_io_failed' and error.value.__context__ is None


# C4: open a published artifact for reading without following links (offline; also runs on Linux).
def sealed(root):
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    data = write_part(paths)
    candidate = store.seal_candidate(paths, ext='mp4', max_bytes=1024, media_check='verified')
    return paths, candidate, data


def test_open_published_reads_exact_bytes(root):
    paths, candidate, data = sealed(root)
    with store.open_published(root, candidate.relative_path, candidate.byte_size) as handle:
        assert handle.read() == data


@pytest.mark.parametrize('relative', ['../escape/1-x/media.mp4', 'job/0-x/media.mp4', 'job/1-x/manifest.json',
                                      'job/1-x/media.mp4/extra', '/abs/1-x/media.mp4'])
def test_open_published_refuses_unexpected_paths(root, relative):
    sealed(root)
    with pytest.raises(store.ArtifactError):
        store.open_published(root, relative, 10)


def test_open_published_refuses_size_mismatch(root):
    paths, candidate, data = sealed(root)
    with pytest.raises(store.ArtifactError) as error:
        store.open_published(root, candidate.relative_path, candidate.byte_size + 1)
    assert str(error.value) == 'artifact_changed'


@posix_only
def test_open_published_refuses_symlinked_final(root, tmp_path):
    paths, candidate, data = sealed(root)
    final = root / candidate.relative_path
    outside = tmp_path / 'outside.mp4'
    outside.write_bytes(data)
    final.unlink()
    final.symlink_to(outside)
    with pytest.raises(store.ArtifactError):
        store.open_published(root, candidate.relative_path, candidate.byte_size)


# C5a: the cleaner deletes one published attempt's controlled objects only (offline; also on Linux).
def test_remove_published_deletes_only_that_attempt(root):
    paths, candidate, data = sealed(root)
    sibling = store.prepare_attempt(root, JOB, 2, str(uuid.uuid4()))
    write_part(sibling)
    store.remove_published(root, candidate.relative_path)
    assert not paths.directory.exists()
    assert sibling.part.exists() and (root / JOB).is_dir()  # the job directory and other attempts stay


def test_remove_published_is_idempotent_when_already_gone(root):
    paths, candidate, data = sealed(root)
    store.remove_published(root, candidate.relative_path)
    store.remove_published(root, candidate.relative_path)  # missing is success
    store.remove_published(root, f'{uuid.uuid4()}/1-{uuid.uuid4()}/media.mp4')  # never existed


def test_remove_published_keeps_everything_on_unknown_entry(root):
    paths, candidate, data = sealed(root)
    (paths.directory / 'unexpected.bin').write_bytes(b'x')
    with pytest.raises(store.ArtifactError) as error:
        store.remove_published(root, candidate.relative_path)
    assert str(error.value) == 'artifact_unknown_entry'
    assert (root / candidate.relative_path).exists() and (paths.directory / 'manifest.json').exists()


def test_remove_published_refuses_unexpected_paths(root):
    for relative in ('../x/1-y/media.mp4', 'job/1-x/manifest.json', 'job/0-x/media.mp4'):
        with pytest.raises(store.ArtifactError):
            store.remove_published(root, relative)


def test_remove_published_root_unavailable(tmp_path):
    with pytest.raises(store.ArtifactError) as error:
        store.remove_published(tmp_path / 'not-mounted', f'{JOB}/1-{ATTEMPT}/media.mp4')
    assert str(error.value) == 'artifact_root_unavailable'


@posix_only
def test_remove_published_refuses_symlinked_attempt_directory(root, tmp_path):
    paths, candidate, data = sealed(root)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'media.mp4').write_bytes(b'keep me')
    for entry in paths.directory.iterdir():
        entry.unlink()
    paths.directory.rmdir()
    paths.directory.symlink_to(outside, target_is_directory=True)
    with pytest.raises(store.ArtifactError):
        store.remove_published(root, candidate.relative_path)
    assert (outside / 'media.mp4').read_bytes() == b'keep me'


@pytest.mark.skipif(os.name != 'nt', reason='junction test is Windows-specific')
def test_remove_published_refuses_junction_job_directory(root, tmp_path):
    import _winapi
    import shutil
    paths, candidate, data = sealed(root)
    outside = tmp_path / 'outside'
    shutil.copytree(root / JOB, outside)
    shutil.rmtree(root / JOB)
    _winapi.CreateJunction(str(outside), str(root / JOB))
    with pytest.raises(store.ArtifactError):
        store.remove_published(root, candidate.relative_path)
    assert (outside / f'1-{ATTEMPT}' / 'media.mp4').exists()


# C5a review I2: an unprovisioned directory (e.g. an empty mount point) is never a media root.
def test_unprovisioned_root_is_unavailable(tmp_path):
    bare = tmp_path / 'empty-mount-point'
    bare.mkdir()
    with pytest.raises(store.ArtifactError) as error:
        store.remove_published(bare.resolve(), f'{JOB}/1-{ATTEMPT}/media.mp4')
    assert str(error.value) == 'artifact_root_unavailable'  # never "already deleted"
    with pytest.raises(store.ArtifactError):
        store.prepare_attempt(bare.resolve(), JOB, 1, ATTEMPT)
    with pytest.raises(store.ArtifactError):
        store.probe_root(bare.resolve())


def test_provision_root_is_idempotent_and_checked(tmp_path):
    media = (tmp_path / 'm')
    media.mkdir()
    store.provision_root(media.resolve())
    store.provision_root(media.resolve())
    store.check_root(media.resolve())
    marker = media / store.ROOT_MARKER
    marker.write_bytes(b'something else')
    with pytest.raises(store.ArtifactError) as error:
        store.check_root(media.resolve())
    assert str(error.value) == 'artifact_root_unavailable'


# C5a review M4: objects vanishing during removal (a concurrent cleaner) are success, not a failure.
def test_remove_published_tolerates_concurrent_disappearance(root, monkeypatch):
    paths, candidate, data = sealed(root)
    real_unlink = store.Path.unlink

    def racing_unlink(self, *args, **kwargs):
        real_unlink(self)            # someone else removed it first
        return real_unlink(self, *args, **kwargs)
    monkeypatch.setattr(store.Path, 'unlink', racing_unlink)
    store.remove_published(root, candidate.relative_path)
    assert not paths.directory.exists()


# C2 review M9 (fixed in C5a): an owned-looking directory entry stops the removal before anything is deleted.
def test_owned_name_directory_entry_deletes_nothing(root):
    paths, candidate, data = sealed(root)
    (paths.directory / 'manifest.part').mkdir()
    with pytest.raises(store.ArtifactError):
        store.remove_published(root, candidate.relative_path)
    assert (root / candidate.relative_path).exists() and (paths.directory / 'manifest.json').exists()


def test_media_root_cli_provisions_then_refuses_relative(tmp_path):
    from app import media_root as cli
    target = tmp_path / 'volume'
    target.mkdir()
    cli.main([str(target.resolve())])
    store.check_root(target.resolve())
    with pytest.raises(SystemExit) as stop:
        cli.main(['relative/volume'])
    assert stop.value.code == 2


# C5b-2: bounded scan of the controlled root and kind-specific orphan removal (offline; also on Linux).
def entries_by_kind(entries):
    return {(entry.kind, entry.relative_path, entry.reason) for entry in entries}


def test_scan_root_lists_known_objects_and_skips_the_marker(root):
    paths, candidate, data = sealed(root)
    (root / '.probe-1-abababababababab.part').write_bytes(b'x')
    found = entries_by_kind(store.scan_root(root))
    assert ('job_dir', JOB, None) in found and ('attempt_dir', f'{JOB}/1-{ATTEMPT}', None) in found
    assert ('probe_file', '.probe-1-abababababababab.part', None) in found
    assert not any(store.ROOT_MARKER in relative for _, relative, _ in found)


def test_scan_root_flags_unknown_entries_without_descending(root):
    sealed(root)
    (root / 'stray.txt').write_bytes(b'x')
    (root / JOB / 'not-an-attempt').mkdir()
    found = entries_by_kind(store.scan_root(root))
    assert ('unknown', 'stray.txt', 'unknown_entry') in found
    assert ('unknown', f'{JOB}/not-an-attempt', 'unknown_entry') in found


@posix_only
def test_scan_root_flags_links_and_never_follows_them(root, tmp_path):
    outside = tmp_path / 'outside'
    (outside / f'1-{ATTEMPT}').mkdir(parents=True)
    (root / JOB).symlink_to(outside, target_is_directory=True)
    found = entries_by_kind(store.scan_root(root))
    assert found == {('unknown', JOB, 'link')}


@pytest.mark.skipif(os.name != 'nt', reason='junction test is Windows-specific')
def test_scan_root_flags_junctions_and_never_follows_them(root, tmp_path):
    import _winapi
    outside = tmp_path / 'outside'
    (outside / f'1-{ATTEMPT}').mkdir(parents=True)
    _winapi.CreateJunction(str(outside), str(root / JOB))
    assert entries_by_kind(store.scan_root(root)) == {('unknown', JOB, 'link')}


def test_scan_root_is_bounded(root):
    for index in range(5):
        (root / f'{uuid.uuid4()}').mkdir()
    assert len(store.scan_root(root, limit=3)) == 3


def test_scan_root_requires_a_provisioned_root(tmp_path):
    bare = tmp_path / 'bare'
    bare.mkdir()
    with pytest.raises(store.ArtifactError) as error:
        store.scan_root(bare.resolve())
    assert str(error.value) == 'artifact_root_unavailable'


def test_remove_orphan_attempt_job_and_probe(root):
    paths, candidate, data = sealed(root)
    probe = root / '.probe-1-abababababababab.part'
    probe.write_bytes(b'x')
    with pytest.raises(store.ArtifactError) as error:  # a job directory with an attempt inside is not removable
        store.remove_orphan(root, JOB, 'job_dir')
    assert str(error.value) == 'artifact_not_empty'
    store.remove_orphan(root, f'{JOB}/1-{ATTEMPT}', 'attempt_dir')
    store.remove_orphan(root, JOB, 'job_dir')
    store.remove_orphan(root, '.probe-1-abababababababab.part', 'probe_file')
    assert [entry.name for entry in root.iterdir()] == [store.ROOT_MARKER]
    store.remove_orphan(root, JOB, 'job_dir')  # already absent: success


def test_remove_orphan_refuses_unknown_kinds_and_paths(root):
    paths, candidate, data = sealed(root)
    (paths.directory / 'unexpected.bin').write_bytes(b'x')
    with pytest.raises(store.ArtifactError):
        store.remove_orphan(root, f'{JOB}/1-{ATTEMPT}', 'attempt_dir')  # unknown entry inside: kept
    for relative, kind in (('stray.txt', 'unknown'), ('../x', 'job_dir'), (store.ROOT_MARKER, 'probe_file'),
                           (f'{JOB}/1-{ATTEMPT}', 'job_dir')):
        with pytest.raises(store.ArtifactError):
            store.remove_orphan(root, relative, kind)
    assert (root / candidate.relative_path).exists()


# C5b-2 review I1: an entry vanishing between the listing and its stat is skipped, not a failed scan.
def test_scan_root_skips_entries_that_vanish_mid_scan(root, monkeypatch):
    paths, candidate, data = sealed(root)
    probe = root / ('.probe-1-' + 'ef' * 8 + '.part')
    probe.write_bytes(b'x')
    real = store._entry_nature

    def vanishing(entry):
        if entry.name == probe.name:
            probe.unlink()
        return real(entry)
    monkeypatch.setattr(store, '_entry_nature', vanishing)
    found = entries_by_kind(store.scan_root(root))
    assert ('attempt_dir', f'{JOB}/1-{ATTEMPT}', None) in found
    assert not any(relative == probe.name for _, relative, _ in found)


# C5b-2 review I2: a resumable scan sees every entry across rounds, whatever the limit.
def test_scan_root_resumes_after_a_cursor(root):
    names = sorted(str(uuid.uuid4()) for _ in range(5))
    for name in names:
        (root / name).mkdir()
    first = store.scan_root(root, limit=3)
    rest = store.scan_root(root, limit=3, start_after=first[-1].relative_path.split('/')[0])
    seen = {entry.relative_path for entry in first + rest}
    assert set(names) <= seen


# C5b-2 review I2: removing the last attempt of a finished Job also removes its now-empty job directory.
def test_remove_published_prunes_the_empty_job_directory(root):
    paths, candidate, data = sealed(root)
    store.remove_published(root, candidate.relative_path, prune_job_dir=True)
    assert not (root / JOB).exists()


# C5b-2 review I4: a job directory removed between the worker's two mkdirs is recreated once.
def test_prepare_attempt_recreates_a_job_directory_removed_concurrently(root, monkeypatch):
    real_mkdir = store.Path.mkdir
    state = {'raced': False}

    def racing_mkdir(self, *args, **kwargs):
        result = real_mkdir(self, *args, **kwargs)
        if self.name == JOB and not state['raced']:
            state['raced'] = True
            self.rmdir()  # an orphan scanner removed the (empty) job directory right after
        return result
    monkeypatch.setattr(store.Path, 'mkdir', racing_mkdir)
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    assert paths.directory.is_dir() and state['raced']


# C5b-2 review M12: "already absent" counts only on a root that is still the provisioned volume.
def test_remove_orphan_absent_on_vanished_root_is_unavailable(root, monkeypatch):
    calls = {'count': 0}
    real = store.check_root

    def root_goes_away(media_root):
        calls['count'] += 1
        if calls['count'] > 1:
            raise store.ArtifactError('artifact_root_unavailable')
        return real(media_root)
    monkeypatch.setattr(store, 'check_root', root_goes_away)
    with pytest.raises(store.ArtifactError) as error:
        store.remove_orphan(root, '.probe-1-' + 'ab' * 8 + '.part', 'probe_file')
    assert str(error.value) == 'artifact_root_unavailable'


# C5b-2 review M10: the filesystem's own lost+found at the volume root is not an orphan or an alert.
def test_scan_root_ignores_lost_and_found(root):
    (root / 'lost+found').mkdir()
    assert not any('lost+found' in entry.relative_path for entry in store.scan_root(root))


# C6a: the recovery reads back a sealed (renamed, manifest persisted) candidate and verifies it.
def rewrite_manifest(paths, **changes):
    manifest_path = paths.directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text('utf8'))
    manifest.update(changes)
    manifest_path.write_text(json.dumps(manifest), 'utf8')


def test_read_sealed_returns_the_verified_candidate(root):
    paths, candidate, data = sealed(root)
    assert store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024) == candidate


@pytest.mark.skipif(os.name == 'nt', reason='POSIX file ownership')
def test_read_sealed_refuses_a_manifest_the_worker_did_not_write(root, monkeypatch):
    # External gate G3/G4 review I3: an isolated child (another uid) could plant manifest.json in its
    # shared attempt directory; recovery must adopt only manifests written by this worker.
    sealed(root)
    real = os.geteuid()
    monkeypatch.setattr(store.os, 'geteuid', lambda: real + 1)
    with pytest.raises(store.ArtifactError) as error:
        store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024)
    assert str(error.value) == 'artifact_manifest_invalid'


def test_read_sealed_without_manifest_or_directory_has_no_candidate(root):
    assert store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024) is None  # no directory at all
    paths = store.prepare_attempt(root, JOB, 1, ATTEMPT)
    write_part(paths)
    assert store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024) is None  # only media.part


@pytest.mark.parametrize('changes', [dict(job_id=str(uuid.uuid4())), dict(epoch=2), dict(attempt_id='other'),
                                     dict(relative_path='x/1-y/media.mp4'), dict(media_format='MP4'),
                                     dict(media_check='unchecked'), dict(byte_size=0), dict(byte_size='21'),
                                     dict(sha256='A' * 64), dict(extra=1)])
def test_read_sealed_refuses_an_inconsistent_manifest(root, changes):
    paths, candidate, data = sealed(root)
    rewrite_manifest(paths, **changes)
    with pytest.raises(store.ArtifactError) as error:
        store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024)
    assert str(error.value) == 'artifact_manifest_invalid'


def test_read_sealed_refuses_an_oversized_or_unparsable_manifest(root):
    paths, candidate, data = sealed(root)
    (paths.directory / 'manifest.json').write_bytes(b'{' + b' ' * 8192 + b'}')
    with pytest.raises(store.ArtifactError, match='artifact_manifest_invalid'):
        store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024)
    (paths.directory / 'manifest.json').write_bytes(b'not json')
    with pytest.raises(store.ArtifactError, match='artifact_manifest_invalid'):
        store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024)


def test_read_sealed_refuses_changed_media(root):
    paths, candidate, data = sealed(root)
    (paths.directory / 'media.mp4').write_bytes(data[::-1])  # same size, different content
    with pytest.raises(store.ArtifactError, match='artifact_hash_mismatch'):
        store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024)
    (paths.directory / 'media.mp4').write_bytes(data + b'x')
    with pytest.raises(store.ArtifactError, match='artifact_changed'):
        store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024)
    (paths.directory / 'media.mp4').unlink()
    with pytest.raises(store.ArtifactError, match='artifact_path_missing'):
        store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024)


def test_read_sealed_refuses_a_candidate_over_the_size_limit(root):
    sealed(root)
    with pytest.raises(store.ArtifactError, match='artifact_manifest_invalid'):
        store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=5)


def test_read_sealed_refuses_a_junction_attempt_directory(root, tmp_path):
    if os.name != 'nt':
        pytest.skip('junctions are Windows-only')
    import _winapi
    import shutil
    paths, candidate, data = sealed(root)
    outside = tmp_path / 'outside'
    shutil.copytree(paths.directory, outside)
    shutil.rmtree(paths.directory)
    _winapi.CreateJunction(str(outside), str(paths.directory))
    with pytest.raises(store.ArtifactError, match='artifact_path_unsafe'):
        store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024)


def test_read_sealed_requires_the_provisioned_root(tmp_path):
    with pytest.raises(store.ArtifactError, match='artifact_root_unavailable'):
        store.read_sealed(tmp_path.resolve(), JOB, 1, ATTEMPT, max_bytes=1024)


def test_sealed_attempts_lists_every_attempt_with_a_manifest(root):
    sealed(root)
    other = str(uuid.uuid4())
    second = store.prepare_attempt(root, JOB, 2, other)
    write_part(second)
    assert store.sealed_attempts(root, JOB) == [f'1-{ATTEMPT}']  # media.part only is not a candidate
    store.seal_candidate(second, ext='mp4', max_bytes=1024, media_check='verified')
    assert store.sealed_attempts(root, JOB) == sorted([f'1-{ATTEMPT}', f'2-{other}'])
    assert store.sealed_attempts(root, str(uuid.uuid4())) == []


# C6a: an unreadable published file is diagnosed without guessing on transient errors.
def test_diagnose_published(root, monkeypatch):
    paths, candidate, data = sealed(root)
    assert store.diagnose_published(root, candidate.relative_path, candidate.byte_size) is None
    assert store.diagnose_published(root, candidate.relative_path, candidate.byte_size + 1) == 'corrupt'
    (paths.directory / 'media.mp4').unlink()
    assert store.diagnose_published(root, candidate.relative_path, candidate.byte_size) == 'missing'
    (paths.directory / 'media.mp4').mkdir()
    assert store.diagnose_published(root, candidate.relative_path, candidate.byte_size) == 'corrupt'
    assert store.diagnose_published(root, '../x/1-y/media.mp4', 1) == 'corrupt'


def test_diagnose_published_missing_job_directory_and_unavailable_root(root, tmp_path):
    paths, candidate, data = sealed(root)
    import shutil
    shutil.rmtree(root / JOB)
    assert store.diagnose_published(root, candidate.relative_path, candidate.byte_size) == 'missing'
    assert store.diagnose_published(tmp_path / 'nothing', candidate.relative_path, candidate.byte_size) is None


def test_diagnose_published_transient_error_is_not_a_diagnosis(root, monkeypatch):
    paths, candidate, data = sealed(root)
    real = Path.lstat

    def denied(self, *args, **kwargs):
        if self.name == 'media.mp4':
            raise PermissionError('denied')
        return real(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', denied)
    assert store.diagnose_published(root, candidate.relative_path, candidate.byte_size) is None


# C6a review M1: a damaged manifest of any shape is a fixed error, never an exception escaping recovery.
@pytest.mark.parametrize('raw', [None, 'deep'])
def test_read_sealed_refuses_unhashable_or_deeply_nested_manifests(root, raw):
    paths, candidate, data = sealed(root)
    if raw is None:
        rewrite_manifest(paths, media_check=[])
    else:
        (paths.directory / 'manifest.json').write_bytes(b'[' * 4000)
    with pytest.raises(store.ArtifactError, match='artifact_manifest_invalid'):
        store.read_sealed(root, JOB, 1, ATTEMPT, max_bytes=1024)


# C6a review M2: a root that disappears during the diagnosis is an outage, never a missing file.
def test_diagnose_published_rechecks_the_root_before_missing(root, monkeypatch):
    paths, candidate, data = sealed(root)
    (paths.directory / 'media.mp4').unlink()
    real, calls = store._root, []

    def unmounted_after_first(media_root):
        calls.append(1)
        if len(calls) > 1:
            raise store.ArtifactError('artifact_root_unavailable')
        return real(media_root)
    monkeypatch.setattr(store, '_root', unmounted_after_first)
    assert store.diagnose_published(root, candidate.relative_path, candidate.byte_size) is None


# C6b: an imported v1 file is opened under the old root's <job_id>/ without following links.
@pytest.fixture
def legacy(tmp_path):
    old = (tmp_path / 'old').resolve()
    (old / JOB).mkdir(parents=True)
    path = old / JOB / 'clip name.mp4'
    path.write_bytes(b'legacy-bytes')
    return old, path


def test_open_legacy_reads_the_recorded_file(legacy):
    old, path = legacy
    with store.open_legacy(old, JOB, str(path), 12) as handle:
        assert handle.read() == b'legacy-bytes'


@pytest.mark.parametrize('change, code', [
    (lambda old, path: (str(path), 13), 'artifact_changed'),
    (lambda old, path: (str(old / JOB / 'gone.mp4'), 12), 'artifact_path_missing'),
    (lambda old, path: (str(old / 'other' / 'x.mp4'), 12), 'artifact_path_unsafe'),
    (lambda old, path: (str(old / JOB / '..' / JOB / 'clip name.mp4'), 12), 'artifact_path_unsafe'),
    (lambda old, path: ('clip name.mp4', 12), 'artifact_path_unsafe'),
])
def test_open_legacy_refuses_changed_missing_or_unsafe(legacy, change, code):
    old, path = legacy
    file_path, size = change(old, path)
    with pytest.raises(store.ArtifactError) as error:
        store.open_legacy(old, JOB, file_path, size)
    assert str(error.value) == code


def test_open_legacy_refuses_hard_links_and_junctions(legacy, tmp_path):
    old, path = legacy
    os.link(path, tmp_path / 'second-name')
    with pytest.raises(store.ArtifactError, match='artifact_changed'):
        store.open_legacy(old, JOB, str(path), 12)
    if os.name == 'nt':
        import _winapi
        outside = tmp_path / 'outside'
        (outside).mkdir()
        (outside / 'x.mp4').write_bytes(b'legacy-bytes')
        _winapi.CreateJunction(str(outside), str(old / 'linked'))
        with pytest.raises(store.ArtifactError, match='artifact_path_unsafe'):
            store.open_legacy(old, 'linked', str(old / 'linked' / 'x.mp4'), 12)


def test_open_legacy_without_a_usable_root_is_unavailable(tmp_path, legacy):
    old, path = legacy
    with pytest.raises(store.ArtifactError, match='artifact_root_unavailable'):
        store.open_legacy(tmp_path / 'not-there', JOB, str(path), 12)


def test_diagnose_legacy(legacy):
    old, path = legacy
    assert store.diagnose_legacy(old, JOB, str(path), 12) is None
    assert store.diagnose_legacy(old, JOB, str(path), 13) == 'mismatch'
    path.unlink()
    assert store.diagnose_legacy(old, JOB, str(path), 12) == 'missing'
    assert store.diagnose_legacy(old / 'nothing', JOB, str(path), 12) is None



# C6b review I1: an empty mount point (no job directory) is no diagnosis; a gone file in a present one is.
def test_diagnose_legacy_never_revokes_on_a_missing_job_directory(legacy, tmp_path):
    old, path = legacy
    empty = (tmp_path / 'empty-mount').resolve()
    empty.mkdir()
    assert store.diagnose_legacy(empty, JOB, str(empty / JOB / 'clip name.mp4'), 12) is None
    os.link(path, tmp_path / 'snapshot-link')
    assert store.diagnose_legacy(old, JOB, str(path), 12) == 'mismatch'  # hard-linked (e.g. a backup snapshot)


# C6b review I2: every level is checked on POSIX too (O_NOFOLLOW guards only the last one).
@posix_only
@pytest.mark.parametrize('level', ['job_dir', 'sub_dir', 'file'])
def test_open_legacy_refuses_symlinks_at_every_level(legacy, tmp_path, level):
    old, path = legacy
    outside = tmp_path / 'outside'
    (outside / 'sub').mkdir(parents=True)
    (outside / 'sub' / 'x.mp4').write_bytes(b'legacy-bytes')
    (outside / 'x.mp4').write_bytes(b'legacy-bytes')
    if level == 'job_dir':
        (old / 'linked').symlink_to(outside, target_is_directory=True)
        job, target = 'linked', old / 'linked' / 'x.mp4'
    elif level == 'sub_dir':
        (old / JOB / 'sub').symlink_to(outside / 'sub', target_is_directory=True)
        job, target = JOB, old / JOB / 'sub' / 'x.mp4'
    else:
        (old / JOB / 'x.mp4').symlink_to(outside / 'x.mp4')
        job, target = JOB, old / JOB / 'x.mp4'
    with pytest.raises(store.ArtifactError) as error:
        store.open_legacy(old, job, str(target), 12)
    assert str(error.value) == 'artifact_path_unsafe'
    assert store.diagnose_legacy(old, job, str(target), 12) in ('mismatch', None)


def test_diagnose_legacy_unsafe_paths_are_not_diagnosed(legacy):
    old, path = legacy
    assert store.diagnose_legacy(old, JOB, str(old / 'other' / 'x.mp4'), 12) is None


# C6c: an expired imported v1 file is removed with the same path rules as open_legacy.
@pytest.fixture
def marked(legacy):
    old, path = legacy
    store.provision_legacy_root(old)
    return old, path


def test_remove_legacy_deletes_only_the_file(marked):
    old, path = marked
    store.remove_legacy(old, JOB, str(path))
    # The job directory stays: its presence is what proves the old root is mounted on a retry.
    assert not path.exists() and (old / JOB).is_dir()


def test_remove_legacy_keeps_other_entries_of_the_job_directory(marked):
    old, path = marked
    (old / JOB / 'other.txt').write_bytes(b'x')
    store.remove_legacy(old, JOB, str(path))
    assert not path.exists() and (old / JOB / 'other.txt').exists()


def test_remove_legacy_is_idempotent_when_already_gone(marked):
    old, path = marked
    path.unlink()
    store.remove_legacy(old, JOB, str(path))
    store.remove_legacy(old, JOB, str(path))  # a retry after a lost confirmation is still a success


def test_remove_legacy_refuses_unsafe_paths_and_links(marked, tmp_path):
    old, path = marked
    with pytest.raises(store.ArtifactError, match='artifact_path_outside'):
        store.remove_legacy(old, JOB, str(old / 'other' / 'x.mp4'))  # a per-row failure, never a deletion
    os.link(path, tmp_path / 'second-name')
    with pytest.raises(store.ArtifactError, match='artifact_path_unsafe'):
        store.remove_legacy(old, JOB, str(path))  # a hard-linked file is not this Job's own object
    assert path.exists()


def test_remove_legacy_on_an_unusable_root_is_unavailable(marked, tmp_path):
    old, path = marked
    with pytest.raises(store.ArtifactError, match='artifact_root_unavailable'):
        store.remove_legacy(tmp_path / 'not-mounted', JOB, str(path))
    empty = (tmp_path / 'empty-mount').resolve()
    empty.mkdir()  # an empty mount point carries no marker
    with pytest.raises(store.ArtifactError, match='artifact_root_unavailable'):
        store.remove_legacy(empty, JOB, str(empty / JOB / 'clip name.mp4'))


def test_remove_legacy_missing_job_directory_on_a_marked_root_is_gone(marked):
    old, path = marked
    import shutil
    shutil.rmtree(old / JOB)
    store.remove_legacy(old, JOB, str(path))  # the marker proves the mount: the file is simply gone


def test_remove_legacy_never_deletes_through_a_junction_or_symlink(marked, tmp_path):
    old, path = marked
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'clip.mp4').write_bytes(b'legacy-bytes')
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(outside), str(old / 'linked'))
    else:
        (old / 'linked').symlink_to(outside, target_is_directory=True)
    with pytest.raises(store.ArtifactError, match='artifact_path_unsafe'):
        store.remove_legacy(old, 'linked', str(old / 'linked' / 'clip.mp4'))
    assert (outside / 'clip.mp4').exists()


@posix_only
@pytest.mark.parametrize('level', ['sub_dir', 'file'])
def test_remove_legacy_never_follows_deeper_symlinks(marked, tmp_path, level):
    old, path = marked
    outside = tmp_path / 'outside'
    (outside / 'sub').mkdir(parents=True)
    (outside / 'sub' / 'x.mp4').write_bytes(b'legacy-bytes')
    (outside / 'x.mp4').write_bytes(b'legacy-bytes')
    if level == 'sub_dir':
        (old / JOB / 'sub').symlink_to(outside / 'sub', target_is_directory=True)
        target, kept = old / JOB / 'sub' / 'x.mp4', outside / 'sub' / 'x.mp4'
    else:
        (old / JOB / 'x.mp4').symlink_to(outside / 'x.mp4')
        target, kept = old / JOB / 'x.mp4', outside / 'x.mp4'
    with pytest.raises(store.ArtifactError, match='artifact_path_unsafe'):
        store.remove_legacy(old, JOB, str(target))
    assert kept.exists()


def test_provision_legacy_root_is_idempotent_and_checked(tmp_path):
    root = (tmp_path / 'old-root').resolve()
    root.mkdir()
    with pytest.raises(store.ArtifactError, match='artifact_root_unavailable'):
        store.check_legacy_root(root)
    store.provision_legacy_root(root)
    store.provision_legacy_root(root)
    assert store.check_legacy_root(root) == root
