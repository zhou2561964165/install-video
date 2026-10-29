"""C2 attempt-owned media files inside a controlled root (filesystem only, no DB).

Each attempt writes only inside <root>/<job_id>/<epoch>-<attempt_id>/: media.part
is checked, fsynced and renamed without overwriting to media.<ext>; the manifest
follows the same part -> fsync -> rename path. Nothing here ever writes a shared
final name; publishing to the database is artifact_publish's job.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat

_SEGMENT = re.compile(r'[A-Za-z0-9-]{1,64}\Z')
_EXT = re.compile(r'[a-z0-9]{1,8}\Z')
# 'verified': decode-level (reserved for C); 'signature': container-signature check (B5 U5b, b5_0012).
MEDIA_CHECKS = frozenset({'verified', 'signature'})
_REPARSE_POINT = 0x400
_BLOCK = 1 << 20


class ArtifactError(RuntimeError):
    """Fixed, path-free failure; callers treat the attempt as not publishable."""


def _fail(code='artifact_invalid'):
    error = ArtifactError(code)
    try:
        raise error
    except ArtifactError:
        error.__context__ = error.__cause__ = None
        raise


def _plain(path: Path, *, directory: bool) -> os.stat_result:
    """lstat a path and refuse symlinks, junctions and other reparse points."""
    try:
        info = path.lstat()
    except OSError:
        _fail('artifact_path_missing')
    kind_ok = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT or not kind_ok:
        _fail('artifact_path_unsafe')
    return info


@dataclass(frozen=True, slots=True)
class AttemptPaths:
    root: Path = field(repr=False)
    job_id: str
    epoch: int
    attempt_id: str

    @property
    def relative_dir(self) -> str:
        return f'{self.job_id}/{self.epoch}-{self.attempt_id}'

    @property
    def directory(self) -> Path:
        return self.root / self.job_id / f'{self.epoch}-{self.attempt_id}'

    @property
    def part(self) -> Path:
        return self.directory / 'media.part'


@dataclass(frozen=True, slots=True)
class ArtifactCandidate:
    job_id: str
    epoch: int
    attempt_id: str
    relative_path: str
    byte_size: int
    sha256: str
    media_format: str
    media_check: str


ROOT_MARKER = '.install-video-media-root'
_ROOT_MARKER_CONTENT = b'install-video media root v1\n'
# C6c: the old v1 file root gets its own operator marker before the cleaner may delete in it.
LEGACY_ROOT_MARKER = '.install-video-legacy-root'
_LEGACY_ROOT_MARKER_CONTENT = b'install-video legacy root v1\n'


def _canonical_dir(media_root) -> Path:
    if not isinstance(media_root, Path) or not media_root.is_absolute():
        _fail('artifact_root_invalid')
    _plain(media_root, directory=True)
    try:
        if media_root.resolve(strict=True) != media_root:
            _fail('artifact_root_invalid')
    except OSError:
        _fail('artifact_root_invalid')
    return media_root


def _root(media_root) -> Path:
    """A media root is a canonical directory holding the provisioned marker. An empty mount point
    (volume not attached) has no marker, so it is never mistaken for a root whose files are gone."""
    root = _canonical_dir(media_root)
    try:
        _plain(root / ROOT_MARKER, directory=False)
        content = (root / ROOT_MARKER).read_bytes()
    except (ArtifactError, OSError):
        content = None
    if content != _ROOT_MARKER_CONTENT:
        _fail('artifact_root_invalid')
    return root


def check_root(media_root) -> Path:
    """Public root check (each cleaner round, API reads): 'artifact_root_unavailable' on any failure."""
    try:
        return _root(media_root)
    except ArtifactError:
        pass
    _fail('artifact_root_unavailable')


def provision_root(media_root) -> None:
    """Operator step, once per media volume: write the root marker (idempotent; never overwrites
    a different marker). Workers, readers and the cleaner refuse a root without it."""
    root = _canonical_dir(media_root)
    marker = root / ROOT_MARKER
    try:
        with open(marker, 'xb') as handle:
            handle.write(_ROOT_MARKER_CONTENT)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(root)
    except FileExistsError:
        pass
    except OSError:
        _fail('artifact_root_invalid')
    _root(root)  # an existing marker must be the expected one


def _check_inside(paths: AttemptPaths) -> None:
    """Every level from root to the attempt directory is a plain directory under root."""
    _plain(paths.root, directory=True)
    for level in (paths.root / paths.job_id, paths.directory):
        _plain(level, directory=True)
    try:
        if not paths.directory.resolve(strict=True).is_relative_to(paths.root):
            _fail('artifact_path_unsafe')
    except OSError:
        _fail('artifact_path_unsafe')


def prepare_attempt(media_root, job_id: str, epoch: int, attempt_id: str) -> AttemptPaths:
    root = _root(media_root)
    if (type(job_id) is not str or not _SEGMENT.match(job_id) or type(attempt_id) is not str
            or not _SEGMENT.match(attempt_id) or type(epoch) is not int or epoch < 1):
        _fail('artifact_segment_invalid')
    paths = AttemptPaths(root, job_id, epoch, attempt_id)
    job_dir = root / job_id
    for last_try in (False, True):
        # An orphan round may remove an empty job directory between our two mkdirs (C5b-2 review I4):
        # recreate it once rather than failing the attempt.
        try:
            job_dir.mkdir(exist_ok=True)
        except OSError:
            _fail('artifact_path_unsafe')
        vanished = False
        try:
            _plain(job_dir, directory=True)
            paths.directory.mkdir()  # never reuse an existing attempt directory
        except FileExistsError:
            _fail('artifact_attempt_exists')
        except FileNotFoundError:
            vanished = True
        except ArtifactError as error:
            if str(error) != 'artifact_path_missing':
                raise
            vanished = True
        except OSError:
            _fail('artifact_path_unsafe')
        if not vanished:
            break
        if last_try:
            _fail('artifact_path_unsafe')
    _check_inside(paths)
    return paths


def _fsync_directory(directory: Path) -> None:
    if os.name == 'nt':
        return  # Windows cannot open directories for fsync; NTFS journals the rename.
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_no_overwrite(source: Path, target: Path) -> None:
    if os.name == 'nt':
        os.rename(source, target)  # fails if target exists
    else:
        os.link(source, target, follow_symlinks=False)  # fails if target exists; never replaces
        os.unlink(source)


def _identity(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def probe_root(media_root) -> None:
    """Startup check: media_root supports the no-overwrite rename (POSIX link+unlink)
    and keeps the file identity (dev, inode, size, mtime, single link) seal_candidate checks.

    Mounts without hard links (SMB/CIFS, some FUSE/volume drivers) or with unstable inode
    numbers would otherwise fail every seal after a full download. Best-effort cleanup;
    any failure (including a read-only root) is the fixed, path-free code.
    """
    root = _root(media_root)
    name = f'.probe-{os.getpid()}-{os.urandom(8).hex()}'
    part, final = root / f'{name}.part', root / f'{name}.final'
    try:
        with open(part, 'xb') as handle:
            handle.write(b'probe')
            handle.flush()
            os.fsync(handle.fileno())
            before = os.fstat(handle.fileno())
        _rename_no_overwrite(part, final)
        after = final.lstat()
        supported = before.st_nlink == 1 and after.st_nlink == 1 and _identity(after) == _identity(before)
    except OSError:
        supported = False
    for leftover in (part, final):
        try:
            leftover.unlink()
        except OSError:
            pass  # missing, or a read-only root: the probe already failed or left nothing
    if not supported:
        _fail('artifact_root_unsupported')


def _write_manifest(paths: AttemptPaths, candidate: ArtifactCandidate) -> None:
    part, final = paths.directory / 'manifest.part', paths.directory / 'manifest.json'
    data = json.dumps(dict(job_id=candidate.job_id, epoch=candidate.epoch, attempt_id=candidate.attempt_id,
                           relative_path=candidate.relative_path, byte_size=candidate.byte_size,
                           sha256=candidate.sha256, media_format=candidate.media_format,
                           media_check=candidate.media_check), sort_keys=True).encode('utf8')
    with open(part, 'xb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _rename_no_overwrite(part, final)


def seal_candidate(paths: AttemptPaths, *, ext: str, max_bytes: int, media_check: str) -> ArtifactCandidate:
    """Check, hash, fsync and rename media.part to media.<ext>; then persist the manifest.

    The caller (C3) must have reaped the writer's whole process group first. Hashing and
    fsync use one handle; the file's (dev, inode, size, mtime) must be unchanged after
    the fsync and must be the renamed file's, and media.part may have no other names.
    """
    if type(paths) is not AttemptPaths or type(ext) is not str or not _EXT.match(ext):
        _fail('artifact_format_invalid')
    if media_check not in MEDIA_CHECKS or type(max_bytes) is not int or max_bytes < 1:
        _fail('artifact_check_invalid')
    _check_inside(paths)
    final = paths.directory / f'media.{ext}'
    if final.exists() or (paths.directory / 'manifest.json').exists():
        _fail('artifact_final_exists')
    _plain(paths.part, directory=False)
    digest, counted = hashlib.sha256(), 0
    try:
        with open(paths.part, 'r+b') as handle:
            before = os.fstat(handle.fileno())
            size = before.st_size
            if before.st_nlink != 1:
                _fail('artifact_path_unsafe')
            if not 0 < size <= max_bytes:
                _fail('artifact_size_invalid')
            while block := handle.read(_BLOCK):
                counted += len(block)
                if counted > size:
                    _fail('artifact_size_invalid')
                digest.update(block)
            if counted != size:
                _fail('artifact_size_invalid')
            os.fsync(handle.fileno())
            if _identity(os.fstat(handle.fileno())) != _identity(before):
                _fail('artifact_changed')
        _rename_no_overwrite(paths.part, final)
        if _identity(_plain(final, directory=False)) != _identity(before):
            _fail('artifact_changed')
    except ArtifactError:
        raise
    except OSError:
        _fail('artifact_io_failed')
    candidate = ArtifactCandidate(paths.job_id, paths.epoch, paths.attempt_id,
                                  f'{paths.relative_dir}/media.{ext}', size, digest.hexdigest(), ext, media_check)
    try:
        _write_manifest(paths, candidate)
        _fsync_directory(paths.directory)
    except OSError:
        _fail('artifact_io_failed')
    return candidate


_PUBLISHED = re.compile(r'([A-Za-z0-9-]{1,64})/([1-9][0-9]{0,18})-([A-Za-z0-9-]{1,64})/media\.([a-z0-9]{1,8})\Z')


def open_published(media_root, relative_path: str, byte_size: int):
    """C4: open one published artifact for reading without following links; returns a binary file.

    Every level from the root is a plain directory or file (no symlink, junction or escape); POSIX
    opens with O_NOFOLLOW. The opened handle must be the same file as the checked path (dev, inode)
    and exactly byte_size long, or nothing is returned (fixed, path-free codes). A missing or unsafe
    root is 'artifact_root_unavailable' (a storage outage, not one missing file).
    """
    try:
        root = _root(media_root)
    except ArtifactError:
        root = None
    if root is None:
        _fail('artifact_root_unavailable')
    match = _PUBLISHED.match(relative_path) if type(relative_path) is str else None
    if match is None or type(byte_size) is not int or byte_size < 1:
        _fail('artifact_path_unsafe')
    job_id, epoch, attempt_id, _ = match.groups()
    paths = AttemptPaths(root, job_id, int(epoch), attempt_id)
    _check_inside(paths)
    final = root / relative_path
    checked = _plain(final, directory=False)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_CLOEXEC', 0)
    try:
        descriptor = os.open(final, flags)
    except OSError:
        descriptor = None
    if descriptor is None:
        _fail('artifact_path_missing')
    try:
        handle = os.fdopen(descriptor, 'rb')
    except OSError:
        os.close(descriptor)
        handle = None
    if handle is None:
        _fail('artifact_io_failed')
    try:
        opened = os.fstat(handle.fileno())
        same = (stat.S_ISREG(opened.st_mode) and (opened.st_dev, opened.st_ino) == (checked.st_dev, checked.st_ino)
                and opened.st_size == byte_size)
    except OSError:
        same = False
    if not same:
        handle.close()
        _fail('artifact_changed')
    return handle


# C6a: recovery of a sealed candidate whose publish never reached the database.
_HEX64 = re.compile(r'[0-9a-f]{64}\Z')
_MANIFEST_KEYS = frozenset({'job_id', 'epoch', 'attempt_id', 'relative_path', 'byte_size', 'sha256',
                            'media_format', 'media_check'})
_MANIFEST_MAX = 4096


def _read_manifest(path: Path) -> dict:
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_CLOEXEC', 0)
    checked = _plain(path, directory=False)
    try:
        with os.fdopen(os.open(path, flags), 'rb') as handle:
            opened = os.fstat(handle.fileno())
            raw = handle.read(_MANIFEST_MAX + 1)
    except OSError:
        _fail('artifact_io_failed')
    if (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino):
        _fail('artifact_changed')
    try:
        manifest = json.loads(raw.decode('utf8')) if len(raw) <= _MANIFEST_MAX else None
    except (ValueError, RecursionError):
        manifest = None
    if type(manifest) is not dict or set(manifest) != _MANIFEST_KEYS:
        _fail('artifact_manifest_invalid')
    return manifest


def read_sealed(media_root, job_id: str, epoch: int, attempt_id: str, *, max_bytes: int) -> ArtifactCandidate | None:
    """Read back and verify one attempt's sealed candidate (manifest persisted, media renamed).

    Returns None when the attempt has no persisted manifest (nothing was sealed). Otherwise the
    manifest must match the attempt's identity exactly and the media file must be a plain file of
    the recorded size and SHA256, at most max_bytes; any mismatch is a fixed, path-free error.
    Read only: nothing is moved or deleted.
    """
    try:
        root = _root(media_root)
    except ArtifactError:
        root = None
    if root is None:
        _fail('artifact_root_unavailable')
    if (type(job_id) is not str or not _SEGMENT.match(job_id) or type(attempt_id) is not str
            or not _SEGMENT.match(attempt_id) or type(epoch) is not int or epoch < 1):
        _fail('artifact_path_unsafe')
    paths = AttemptPaths(root, job_id, epoch, attempt_id)
    try:
        _check_inside(paths)
        manifest_path = paths.directory / 'manifest.json'
        _plain(manifest_path, directory=False)
    except ArtifactError as error:
        if str(error) == 'artifact_path_missing':
            return None
        raise
    if os.name != 'nt':
        # Only this worker writes manifests (seal); an isolated download child runs as another uid and
        # could plant one in its shared attempt directory (external gate G3/G4 review I3).
        try:
            owner = manifest_path.lstat().st_uid
        except OSError:
            _fail('artifact_io_failed')
        if owner != os.geteuid():
            _fail('artifact_manifest_invalid')
    manifest = _read_manifest(manifest_path)
    media_format, byte_size, sha256 = manifest['media_format'], manifest['byte_size'], manifest['sha256']
    if (manifest['job_id'] != job_id or manifest['epoch'] != epoch or type(manifest['epoch']) is not int
            or manifest['attempt_id'] != attempt_id or type(media_format) is not str or not _EXT.match(media_format)
            or manifest['relative_path'] != f'{paths.relative_dir}/media.{media_format}'
            or type(manifest['media_check']) is not str or manifest['media_check'] not in MEDIA_CHECKS
            or type(byte_size) is not int or type(max_bytes) is not int or not 0 < byte_size <= max_bytes
            or type(sha256) is not str or not _HEX64.match(sha256)):
        _fail('artifact_manifest_invalid')
    digest, counted = hashlib.sha256(), 0
    with open_published(root, manifest['relative_path'], byte_size) as handle:
        try:
            while block := handle.read(_BLOCK):
                counted += len(block)
                digest.update(block)
        except OSError:
            _fail('artifact_io_failed')
    if counted != byte_size:
        _fail('artifact_changed')
    if digest.hexdigest() != sha256:
        _fail('artifact_hash_mismatch')
    return ArtifactCandidate(job_id, epoch, attempt_id, manifest['relative_path'], byte_size, sha256,
                             media_format, manifest['media_check'])


def sealed_attempts(media_root, job_id: str) -> list[str]:
    """Names (`<epoch>-<attempt>`) of this job's attempt directories holding a manifest.json (sorted)."""
    if type(job_id) is not str or not _SEGMENT.match(job_id):
        _fail('artifact_path_unsafe')
    job_dir = check_root(media_root) / job_id
    try:
        _plain(job_dir, directory=True)
    except ArtifactError as error:
        if str(error) == 'artifact_path_missing':
            return []
        raise
    found = []
    try:
        for entry in _sorted_entries(job_dir):
            if not _ATTEMPT_DIR.match(entry.name):
                continue
            try:
                if _entry_nature(entry) == 'dir' and _exists(Path(entry.path) / 'manifest.json'):
                    found.append(entry.name)
            except FileNotFoundError:
                continue
    except OSError:
        _fail('artifact_io_failed')
    return found


def _exists(path: Path) -> bool:
    """lstat-based existence (never follows a link)."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def diagnose_published(media_root, relative_path: str, byte_size: int) -> str | None:
    """Classify a published file that could not be opened: 'missing', 'corrupt', or None.

    None means no diagnosis: the root is unavailable (an outage) or a level could not be
    examined for another reason (transient). Only a definite absence is 'missing'; a link,
    junction, wrong type or a wrong size is 'corrupt'. Read only.
    """
    try:
        root = _root(media_root)
    except ArtifactError:
        return None
    match = _PUBLISHED.match(relative_path) if type(relative_path) is str else None
    if match is None:
        return 'corrupt'
    job_id, epoch, attempt_id, _ = match.groups()
    levels = ((root / job_id, True), (root / job_id / f'{epoch}-{attempt_id}', True), (root / relative_path, False))
    for path, directory in levels:
        try:
            info = path.lstat()
        except (FileNotFoundError, NotADirectoryError):
            try:
                _root(media_root)  # an unmounted volume is an outage, never a missing file
            except ArtifactError:
                return None
            return 'missing'
        except OSError:
            return None
        kind_ok = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT or not kind_ok:
            return 'corrupt'
    return 'corrupt' if info.st_size != byte_size else None



# C6b: imported v1 (legacy) files live under the old root (settings.temp_dir) as <job_id>/<name>.
def _legacy_levels(old_root, job_id, file_path):
    """Root and the literal path's levels below root/<job_id>; any '.'/'..' or escape is unsafe."""
    if not isinstance(old_root, Path) or not old_root.is_absolute():
        _fail('artifact_root_unavailable')
    if type(job_id) is not str or not _SEGMENT.match(job_id) or type(file_path) is not str or '\x00' in file_path:
        _fail('artifact_path_unsafe')
    candidate = Path(file_path)
    job_dir = old_root / job_id
    if (not candidate.is_absolute() or any(part in ('.', '..') for part in candidate.parts)
            or job_dir not in candidate.parents):
        _fail('artifact_path_unsafe')
    levels = [job_dir]
    for part in candidate.relative_to(job_dir).parts[:-1]:
        levels.append(levels[-1] / part)
    return levels, candidate


def open_legacy(old_root, job_id: str, file_path: str, byte_size: int):
    """Open one imported v1 file for reading without following links; returns a binary file.

    The old root must be a plain directory (it has no media-root marker); every level below it is a
    plain directory, the file a plain single-link file of exactly byte_size, and the opened handle
    the same file as the checked path. Fixed, path-free codes as in open_published.
    """
    try:
        if not isinstance(old_root, Path) or not old_root.is_absolute():
            _fail('artifact_root_unavailable')
        _plain(old_root, directory=True)  # an unusable root is an outage, checked before any path
    except ArtifactError:
        _fail('artifact_root_unavailable')
    levels, candidate = _legacy_levels(old_root, job_id, file_path)
    if type(byte_size) is not int or byte_size < 0:
        _fail('artifact_changed')
    for level in levels:
        _plain(level, directory=True)
    checked = _plain(candidate, directory=False)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_CLOEXEC', 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError:
        descriptor = None
    if descriptor is None:
        _fail('artifact_path_missing')
    try:
        handle = os.fdopen(descriptor, 'rb')
    except OSError:
        os.close(descriptor)
        handle = None
    if handle is None:
        _fail('artifact_io_failed')
    try:
        opened = os.fstat(handle.fileno())
        same = (stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1
                and (opened.st_dev, opened.st_ino) == (checked.st_dev, checked.st_ino)
                and opened.st_size == byte_size)
    except OSError:
        same = False
    if not same:
        handle.close()
        _fail('artifact_changed')
    return handle


def provision_legacy_root(old_root) -> None:
    """Operator step, once: mark the old v1 file root (as v1 wrote it) as the mounted volume."""
    root = _canonical_dir(old_root)
    try:
        with open(root / LEGACY_ROOT_MARKER, 'xb') as handle:
            handle.write(_LEGACY_ROOT_MARKER_CONTENT)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(root)
    except FileExistsError:
        pass
    except OSError:
        _fail('artifact_root_invalid')
    check_legacy_root(root)


def check_legacy_root(old_root) -> Path:
    """The marked old root, or 'artifact_root_unavailable' (unmounted, unmarked or not canonical)."""
    try:
        root = _canonical_dir(old_root)
        _plain(root / LEGACY_ROOT_MARKER, directory=False)
        content = (root / LEGACY_ROOT_MARKER).read_bytes()
    except (ArtifactError, OSError):
        content = None
    if content != _LEGACY_ROOT_MARKER_CONTENT:
        _fail('artifact_root_unavailable')
    return root


def _gone_on_marked_root(old_root) -> None:
    """'Already gone' only counts while the marked root is still the mounted volume."""
    check_legacy_root(old_root)


def remove_legacy(old_root, job_id: str, file_path: str) -> None:
    """C6c: delete one expired imported v1 file, nothing else; already gone is success.

    The old root must carry the operator marker, so a missing job directory or file means the file
    is gone (re-checked against the marker), not an empty mount point. Same literal path rules as
    open_legacy; a path outside root/<job_id>/ is 'artifact_path_outside' (a per-row failure).
    Only this Job's own single-name regular file is unlinked; directories are never removed.
    Codes: artifact_root_unavailable (stop), artifact_path_unsafe (refuse), artifact_path_outside /
    artifact_io_failed (retry with backoff).
    """
    check_legacy_root(old_root)
    try:
        levels, candidate = _legacy_levels(old_root, job_id, file_path)
    except ArtifactError:
        levels = None
    if levels is None:
        _fail('artifact_path_outside')
    for path, directory in [(level, True) for level in levels] + [(candidate, False)]:
        try:
            info = path.lstat()
        except (FileNotFoundError, NotADirectoryError):
            _gone_on_marked_root(old_root)
            return
        except OSError:
            _fail('artifact_io_failed')  # e.g. permission: transient, retried with backoff
        kind_ok = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if (stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT
                or not kind_ok or (not directory and info.st_nlink != 1)):
            _fail('artifact_path_unsafe')  # never follow or widen: refused
    try:
        candidate.unlink()
    except FileNotFoundError:
        _gone_on_marked_root(old_root)
        return
    except OSError:
        _fail('artifact_io_failed')


def diagnose_legacy(old_root, job_id: str, file_path: str, byte_size: int) -> str | None:
    """'missing', 'mismatch' or None (no diagnosis: unusable root or a transient error). Read only."""
    try:
        levels, candidate = _legacy_levels(old_root, job_id, file_path)
        _plain(old_root, directory=True)
    except ArtifactError:
        return None
    for index, (path, directory) in enumerate([(level, True) for level in levels] + [(candidate, False)]):
        try:
            info = path.lstat()
        except (FileNotFoundError, NotADirectoryError):
            # The v1 cleaner unlinks files but never their job directory, and the import saw it; a
            # missing job directory therefore looks like an unmounted or wrong root: no diagnosis.
            if index == 0:
                return None
            try:
                _plain(old_root, directory=True)  # a vanished root is an outage, never a missing file
            except ArtifactError:
                return None
            return 'missing'
        except OSError:
            return None
        kind_ok = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT or not kind_ok:
            return 'mismatch'
    return 'mismatch' if info.st_size != byte_size or info.st_nlink != 1 else None

_OWNED_NAMES = re.compile(r'(media\.part|media\.[a-z0-9]{1,8}|manifest\.part|manifest\.json)\Z')
SCRATCH_DIR = 'scratch'  # B5 U5b: the controlled download writes here before media.part (C3-3)
_SCRATCH_NAMES = re.compile(r'(media\.bin|media\.bin\.part|video\.bin|audio\.bin)\Z')


def _mp4_family(head: bytes) -> bool:
    # ISO base media files may begin with any top-level box, not only ftyp.
    return head[4:8] in (b'ftyp', b'moov', b'mdat', b'wide', b'free', b'skip')


# Container-signature checks (media_check 'signature'): the leading bytes of each container a
# controlled download may produce. Not a decode; 'verified' stays reserved for that (C stage).
# Known limits: a signature cannot tell a truncated or corrupt body from a good one, and the
# mp4/m4a/mov family shares one box check (an audio-only mp4 named .mp4 passes too).
CONTAINER_SIGNATURES = {
    'mp4': _mp4_family, 'm4a': _mp4_family, 'mov': _mp4_family,
    'webm': lambda head: head[:4] == b'\x1aE\xdf\xa3', 'mkv': lambda head: head[:4] == b'\x1aE\xdf\xa3',
    'flv': lambda head: head[:3] == b'FLV',
    # MPEG audio frame sync with a non-zero layer (ADTS AAC has layer 00 and is not an mp3).
    'mp3': lambda head: head[:3] == b'ID3' or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0
                                               and head[1] & 0x06 != 0),
    'ogg': lambda head: head[:4] == b'OggS', 'opus': lambda head: head[:4] == b'OggS',
    'aac': lambda head: head[:4] == b'ADIF' or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0),
    'wav': lambda head: head[:4] == b'RIFF' and head[8:12] == b'WAVE',
}


def container_signature_ok(path: Path, ext: str) -> bool:
    """Whether a plain (non-link) file starts like the named container."""
    check = CONTAINER_SIGNATURES.get(ext)
    if check is None:
        return False
    _plain(path, directory=False)
    try:
        with open(path, 'rb') as handle:
            head = handle.read(64)
    except OSError:
        _fail('artifact_io_failed')
    return len(head) >= 12 and check(head)


def remove_own_attempt(paths: AttemptPaths) -> None:
    """Delete only this attempt's known files and its directory; never the job dir or siblings.

    The attempt's 'scratch' directory (B5 U5b download area, C3-3) is a known object holding only
    media.bin / media.bin.part; anything else anywhere is unknown and nothing is deleted.
    """
    if type(paths) is not AttemptPaths:
        _fail('artifact_path_unsafe')
    _check_inside(paths)
    scratch = paths.directory / SCRATCH_DIR
    try:
        entries = list(paths.directory.iterdir())
        has_scratch = any(entry.name == SCRATCH_DIR for entry in entries)
        if has_scratch:
            _plain(scratch, directory=True)
            entries = [entry for entry in entries if entry.name != SCRATCH_DIR] + list(scratch.iterdir())
    except OSError:
        entries = None
    if entries is None:
        _fail('artifact_io_failed')  # outside the except: the fixed code carries no path context
    if any(not (_SCRATCH_NAMES if entry.parent.name == SCRATCH_DIR and entry.parent.parent == paths.directory
                else _OWNED_NAMES).match(entry.name) for entry in entries):
        _fail('artifact_unknown_entry')  # unknown object: keep for inspection, never widen deletion
    present = []
    for entry in entries:  # every entry checked before anything is deleted (no partial delete)
        try:
            _plain(entry, directory=False)
        except ArtifactError as error:
            if str(error) != 'artifact_path_missing':
                raise
            continue  # removed concurrently (another cleaner): nothing to do for it
        present.append(entry)
    try:
        for entry in present:
            entry.unlink(missing_ok=True)
        if has_scratch:
            try:
                scratch.rmdir()
            except FileNotFoundError:
                pass
        try:
            paths.directory.rmdir()
        except FileNotFoundError:
            pass
    except OSError:
        _fail('artifact_io_failed')


def remove_published(media_root, relative_path: str, *, prune_job_dir: bool = False) -> None:
    """C5a: delete one published attempt's controlled objects and its directory, nothing else.

    Already absent (job or attempt directory) is success, so a retried cleanup is idempotent.
    Unknown entries, links/junctions or a path outside the published format are refused
    without widening the deletion; a missing/unsafe root is 'artifact_root_unavailable'.
    With prune_job_dir (the Job is finished: no new attempt can appear), an emptied job
    directory is removed too, so finished Jobs do not pile up as orphans (C5b-2 review I2).
    """
    _remove_published(media_root, relative_path)
    if prune_job_dir and type(relative_path) is str and '/' in relative_path:
        try:
            (media_root / relative_path.split('/', 1)[0]).rmdir()  # only ever removes an empty directory
        except OSError:
            pass  # other attempts remain, or already gone: the orphan scan covers what is left


def _remove_published(media_root, relative_path: str) -> None:
    try:
        root = _root(media_root)
    except ArtifactError:
        root = None
    if root is None:
        _fail('artifact_root_unavailable')
    match = _PUBLISHED.match(relative_path) if type(relative_path) is str else None
    if match is None:
        _fail('artifact_path_unsafe')
    job_id, epoch, attempt_id, _ = match.groups()
    paths = AttemptPaths(root, job_id, int(epoch), attempt_id)
    if not _present(paths):
        check_root(root)  # "already gone" only counts on a root that is still the provisioned volume
        return
    try:
        remove_own_attempt(paths)
    except ArtifactError:
        check_root(root)  # a volume that vanished mid-removal is an outage, not a per-file failure
        if not _present(paths):
            return  # removed concurrently: success
        raise


def _present(paths: AttemptPaths) -> bool:
    for level in (paths.root / paths.job_id, paths.directory):
        try:
            os.lstat(level)  # never follows a link
        except FileNotFoundError:
            return False
        except OSError:
            _fail('artifact_io_failed')
    return True


# C5b-2: bounded scan of the controlled root and kind-specific orphan removal. Ownership is decided
# in the database (orphan_repository); this layer only lists and removes known controlled objects.
SCAN_LIMIT = 10_000
_ATTEMPT_DIR = re.compile(r'([1-9][0-9]{0,18})-([A-Za-z0-9-]{1,64})\Z')
_PROBE_FILE = re.compile(r'\.probe-[0-9]{1,10}-[0-9a-f]{16}\.(part|final)\Z')


@dataclass(frozen=True, slots=True)
class ScanEntry:
    relative_path: str
    kind: str  # job_dir | attempt_dir | probe_file | unknown
    reason: str | None = None  # unknown: 'link' or 'unknown_entry'


def _entry_nature(entry) -> str:
    """Kind of one listed entry from a fresh lstat (never follows links). A cached DirEntry stat
    could report an entry that is already gone, so the current state is read; FileNotFoundError
    means it vanished after the listing (normal churn) and the caller skips it."""
    info = os.lstat(entry.path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT:
        return 'link'
    if stat.S_ISDIR(info.st_mode):
        return 'dir'
    return 'file' if stat.S_ISREG(info.st_mode) else 'other'


def _sorted_entries(directory: Path):
    with os.scandir(directory) as listing:
        return sorted(listing, key=lambda entry: entry.name)


def scan_root(media_root, *, limit: int = SCAN_LIMIT, start_after: str | None = None) -> list[ScanEntry]:
    """List the root's job and attempt directories and probe leftovers, never following links.

    Unknown entries and links are reported (for quarantine), never descended into. Attempt
    directories are not opened: their contents are judged only at removal. Entries that vanish
    during the scan are skipped. With start_after, top-level names up to and including it are
    skipped, so a bounded scan can resume where the previous one stopped (the caller wraps).
    """
    if type(limit) is not int or not 1 <= limit <= SCAN_LIMIT:
        raise ValueError('limit_invalid')
    root = check_root(media_root)
    found: list[ScanEntry] = []

    def add(relative, kind, reason=None) -> bool:
        found.append(ScanEntry(relative, kind, reason))
        return len(found) >= limit

    try:
        for entry in _sorted_entries(root):
            name = entry.name
            if name in (ROOT_MARKER, 'lost+found') or (start_after is not None and name <= start_after):
                continue
            try:
                nature = _entry_nature(entry)
            except FileNotFoundError:
                continue
            if nature == 'link':
                full = add(name, 'unknown', 'link')
            elif nature == 'file' and _PROBE_FILE.match(name):
                full = add(name, 'probe_file')
            elif nature == 'dir' and _SEGMENT.match(name):
                full = add(name, 'job_dir')
                try:
                    children = _sorted_entries(root / name)
                except FileNotFoundError:
                    children = []
                for child in children:
                    if full:
                        break
                    try:
                        child_nature = _entry_nature(child)
                    except FileNotFoundError:
                        continue
                    relative = f'{name}/{child.name}'
                    if child_nature == 'link':
                        full = add(relative, 'unknown', 'link')
                    elif child_nature == 'dir' and _ATTEMPT_DIR.match(child.name):
                        full = add(relative, 'attempt_dir')
                    else:
                        full = add(relative, 'unknown', 'unknown_entry')
            else:
                full = add(name, 'unknown', 'unknown_entry')
            if full:
                break
    except OSError:
        found = None
    if found is None:
        _fail('artifact_io_failed')
    return found


def remove_orphan(media_root, relative_path: str, kind: str) -> None:
    """Remove one orphan by kind; already absent is success. Unknown kinds/paths are refused."""
    root = check_root(media_root)
    if type(relative_path) is not str:
        _fail('artifact_path_unsafe')
    if kind == 'attempt_dir':
        parts = relative_path.split('/')
        match = _ATTEMPT_DIR.match(parts[1]) if len(parts) == 2 and _SEGMENT.match(parts[0]) else None
        if match is None:
            _fail('artifact_path_unsafe')
        paths = AttemptPaths(root, parts[0], int(match.group(1)), match.group(2))
        if _present(paths):
            remove_own_attempt(paths)
        return
    if kind == 'job_dir':
        if not _SEGMENT.match(relative_path):
            _fail('artifact_path_unsafe')
        target = root / relative_path
    elif kind == 'probe_file':
        if not _PROBE_FILE.match(relative_path):
            _fail('artifact_path_unsafe')
        target = root / relative_path
    else:
        _fail('artifact_path_unsafe')  # unknown objects are quarantined, never removed
    try:
        os.lstat(target)
    except FileNotFoundError:
        check_root(root)  # "already gone" only counts on a root that is still the provisioned volume
        return
    except OSError:
        _fail('artifact_io_failed')
    _plain(target, directory=kind == 'job_dir')
    try:
        if kind == 'job_dir':
            if any(target.iterdir()):
                raise _NotEmpty()
            target.rmdir()
        else:
            target.unlink(missing_ok=True)
    except _NotEmpty:
        _fail('artifact_not_empty')
    except OSError:
        _fail('artifact_io_failed')


class _NotEmpty(Exception):
    """Internal: a job directory still holds entries."""
