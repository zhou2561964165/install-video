"""Restricted local synthetic/file primitives. No database or format knowledge.

Trusted parent acknowledgement is a caller contract, not a proof against a
host administrator, a malicious same-SID process, or an untrusted parent writer.
"""
import ctypes as c
from ctypes import wintypes as w
from dataclasses import dataclass
import functools
import hashlib
import os
import platform
import re
import stat
import sys
import threading


_KEY = object()
_CODES = frozenset(('filesystem_security_unsupported', 'snapshot_path_invalid',
    'snapshot_permissions_invalid', 'snapshot_destination_exists', 'snapshot_name_invalid',
    'snapshot_limits_invalid', 'snapshot_resource_limit', 'snapshot_identity_changed',
    'snapshot_file_invalid', 'snapshot_io_failed', 'snapshot_cleanup_failed',
    'snapshot_owner_mismatch', 'snapshot_inactive'))
_DATA_NAME = re.compile(r'(?:schema\.json|t[0-9]{2}-[0-9]{6}\.jsonl)\Z', re.ASCII)
_BASE_NAME = re.compile(r'[a-z0-9][a-z0-9-]{0,63}\Z', re.ASCII)


class SnapshotFileError(RuntimeError):
    def __init__(self, *args, **kwargs):
        code = args[0] if len(args) == 1 and not kwargs and type(args[0]) is str else ''
        self.code = code if code in _CODES else 'snapshot_io_failed'
        super().__init__(self.code)


def _fail(code):
    error = SnapshotFileError(code)
    try:
        raise error
    except SnapshotFileError:
        error.__cause__ = error.__context__ = None
        raise


def _safe(code='snapshot_io_failed'):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            failure = None
            try:
                return fn(*args, **kwargs)
            except SnapshotFileError as error:
                failure = error.code
            except Exception:
                failure = code
            _fail(failure)
        return wrapper
    return decorate


class _SafeMeta(type):
    def __call__(cls, *args, **kwargs):
        failure = None
        try:
            return super().__call__(*args, **kwargs)
        except SnapshotFileError as error:
            failure = error.code
        except Exception:
            failure = 'snapshot_limits_invalid' if cls.__name__ == 'FileLimits' else 'snapshot_inactive'
        _fail(failure)


@dataclass(frozen=True, slots=True, kw_only=True)
class FileLimits(metaclass=_SafeMeta):
    max_files: int = 4096
    max_total_bytes: int = 8589934592
    max_file_bytes: int = 67108864
    max_metadata_bytes: int = 2097152
    max_record_bytes: int = 33554432

    def __post_init__(self):
        for name, upper in (('max_files', 4096), ('max_total_bytes', 8589934592),
                            ('max_file_bytes', 67108864), ('max_metadata_bytes', 2097152),
                            ('max_record_bytes', 33554432)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= upper:
                _fail('snapshot_limits_invalid')


DEFAULT_FILE_LIMITS = FileLimits()


@dataclass(frozen=True, slots=True)
class FileDigest(metaclass=_SafeMeta):
    name: str
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PublishResult(metaclass=_SafeMeta):
    status: str
    published: bool
    cleanup_complete: bool
    directory_synced: bool | None
    codes: tuple[str, ...]
    marker: FileDigest


@dataclass(frozen=True, slots=True, repr=False)
class _Info:
    identity: tuple
    directory: bool
    size: int
    links: int
    mtime: int
    ctime: int
    owner: object
    access: object

    def directory_key(self):
        return self.identity, self.directory, self.owner, self.access


def _number(value, upper):
    if type(value) is not int or not 1 <= value <= upper:
        _fail('snapshot_limits_invalid')
    return value


def _matches_lstat(info, before):
    if os.name == 'nt':
        # CPython >=3.12 exposes NTFS FILE_ID_128 as its 128-bit st_ino.
        return before.st_ino == int.from_bytes(info.identity[1], 'little')
    return info.identity == (before.st_dev, before.st_ino)


def _path(path):
    if type(path) is not str or not 1 <= len(path) <= 240 or any(ord(x) < 32 or ord(x) == 127 for x in path):
        _fail('snapshot_path_invalid')
    if os.name == 'nt':
        if not re.match(r'^[A-Za-z]:\\', path) or '/' in path or ':' in path[2:]:
            _fail('snapshot_path_invalid')
        anchor, parts = path[:3], path[3:].split('\\') if len(path) > 3 else []
        for part in parts:
            if ('~' in part or any(x in part for x in '<>"|?*') or part.endswith((' ', '.')) or
                    re.match(r'^(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)', part, re.I)):
                _fail('snapshot_path_invalid')
    else:
        if not path.startswith('/') or path.startswith('//') or '//' in path or ':' in path:
            _fail('snapshot_path_invalid')
        anchor, parts = '/', path[1:].split('/') if len(path) > 1 else []
    if len(parts) > 64 or any(not x or x in ('.', '..') or len(x) > 128 for x in parts):
        _fail('snapshot_path_invalid')
    return anchor, parts


def _name(name, *, marker=False):
    if type(name) is not str or not (_DATA_NAME.fullmatch(name) or (marker and name == 'manifest.json')):
        _fail('snapshot_name_invalid')
    return name


class _Windows:
    def __init__(self):
        if c.sizeof(c.c_void_p) != 8:
            _fail('filesystem_security_unsupported')
        self.k = c.WinDLL('kernel32', use_last_error=True)
        self.a = c.WinDLL('advapi32', use_last_error=True)
        def bind(dll, name, args, result):
            fn = getattr(dll, name)
            fn.argtypes, fn.restype = args, result
            return fn
        H, D, P, B = w.HANDLE, w.DWORD, w.LPVOID, w.BOOL
        self.current_process = bind(self.k, 'GetCurrentProcess', [], H)
        self.current_thread = bind(self.k, 'GetCurrentThread', [], H)
        self.open_token = bind(self.a, 'OpenProcessToken', [H, D, c.POINTER(H)], B)
        self.thread_token = bind(self.a, 'OpenThreadToken', [H, D, B, c.POINTER(H)], B)
        self.token_info = bind(self.a, 'GetTokenInformation', [H, c.c_int, P, D, c.POINTER(D)], B)
        self.sid_text = bind(self.a, 'ConvertSidToStringSidW', [P, c.POINTER(w.LPWSTR)], B)
        self.sd_convert = bind(self.a, 'ConvertStringSecurityDescriptorToSecurityDescriptorW', [w.LPCWSTR, D, c.POINTER(P), c.POINTER(D)], B)
        self.valid_sd = bind(self.a, 'IsValidSecurityDescriptor', [P], B)
        self.control = bind(self.a, 'GetSecurityDescriptorControl', [P, c.POINTER(w.WORD), c.POINTER(D)], B)
        self.security = bind(self.a, 'GetSecurityInfo', [H, c.c_int, D, c.POINTER(P), P, c.POINTER(P), P, c.POINTER(P)], D)
        self.get_ace = bind(self.a, 'GetAce', [P, D, c.POINTER(P)], B)
        self.acl_info = bind(self.a, 'GetAclInformation', [P, P, D, c.c_int], B)
        self.free = bind(self.k, 'LocalFree', [P], P)
        self.close_handle = bind(self.k, 'CloseHandle', [H], B)
        class SA(c.Structure):
            _fields_ = [('length', D), ('descriptor', P), ('inherit', B)]
        self.SA = SA
        self.mkdir_api = bind(self.k, 'CreateDirectoryW', [w.LPCWSTR, c.POINTER(SA)], B)
        self.create = bind(self.k, 'CreateFileW', [w.LPCWSTR, D, D, c.POINTER(SA), D, D, H], H)
        self.get_type = bind(self.k, 'GetFileType', [H], D)
        self.get_info = bind(self.k, 'GetFileInformationByHandleEx', [H, c.c_int, P, D], B)
        self.drive_type = bind(self.k, 'GetDriveTypeW', [w.LPCWSTR], w.UINT)
        self.volume_info = bind(self.k, 'GetVolumeInformationByHandleW', [H, w.LPWSTR, D, c.POINTER(D), c.POINTER(D), c.POINTER(D), w.LPWSTR, D], B)
        self.final_path = bind(self.k, 'GetFinalPathNameByHandleW', [H, w.LPWSTR, D, D], D)
        self.first_stream = bind(self.k, 'FindFirstStreamW', [w.LPCWSTR, c.c_int, P, D], H)
        self.next_stream = bind(self.k, 'FindNextStreamW', [H, P], B)
        self.find_close = bind(self.k, 'FindClose', [H], B)
        self._no_impersonation()
        token, needed = H(), D()
        self._ok(self.open_token(self.current_process(), 8, c.byref(token)))
        try:
            self.token_info(token, 1, None, 0, c.byref(needed))
            if not 0 < needed.value <= 65536:
                _fail('filesystem_security_unsupported')
            buf = c.create_string_buffer(needed.value)
            self._ok(self.token_info(token, 1, buf, needed, c.byref(needed)))
            self.sid = self._sid(c.cast(buf, c.POINTER(P))[0])
        finally:
            self.close_handle(token)
        self.trusted = {self.sid, 'S-1-5-18', 'S-1-5-32-544',
            'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464'}

    def _ok(self, value):
        if not value:
            _fail('filesystem_security_unsupported')
        return value

    def _no_impersonation(self):
        token = w.HANDLE()
        if self.thread_token(self.current_thread(), 8, True, c.byref(token)):
            self.close_handle(token)
            _fail('filesystem_security_unsupported')
        if c.get_last_error() != 1008:
            _fail('filesystem_security_unsupported')

    def _sid(self, ptr):
        text = w.LPWSTR()
        self._ok(self.sid_text(ptr, c.byref(text)))
        try:
            return text.value
        finally:
            self.free(c.cast(text, w.LPVOID))

    def _acl(self, handle, private):
        owner, acl, sd = w.LPVOID(), w.LPVOID(), w.LPVOID()
        if self.security(handle, 1, 5, c.byref(owner), None, c.byref(acl), None, c.byref(sd)):
            _fail('snapshot_permissions_invalid')
        try:
            self._ok(self.valid_sd(sd))
            ctl, rev = w.WORD(), w.DWORD()
            self._ok(self.control(sd, c.byref(ctl), c.byref(rev)))
            owner_sid = self._sid(owner)
            if not acl or not ctl.value & 4:
                _fail('snapshot_permissions_invalid')
            # ACL_SIZE_INFORMATION, not a guessed variable-sized ACL buffer.
            size_info = (w.DWORD * 3)()
            self._ok(self.acl_info(acl, size_info, c.sizeof(size_info), 2))
            if size_info[0] > 128 or size_info[1] > 65536:
                _fail('snapshot_permissions_invalid')
            entries = []
            for i in range(size_info[0]):
                ace = w.LPVOID()
                self._ok(self.get_ace(acl, i, c.byref(ace)))
                header = c.string_at(ace, 4)
                kind, flags = header[0], header[1]
                if int.from_bytes(header[2:4], 'little') < 16 or kind not in (0, 1):
                    _fail('snapshot_permissions_invalid')
                mask = c.cast(ace.value + 4, c.POINTER(w.DWORD))[0]
                sid = self._sid(ace.value + 8)
                entries.append((kind, flags, int(mask), sid))
            if private:
                expected = {(0, 0, 0x1F01FF, x) for x in (self.sid, 'S-1-5-18')}
                if owner_sid != self.sid or not ctl.value & 0x1000 or set(entries) != expected or len(entries) != len(expected):
                    _fail('snapshot_permissions_invalid')
            else:
                if owner_sid not in self.trusted:
                    _fail('snapshot_permissions_invalid')
                for kind, flags, mask, sid in entries:
                    # INHERIT_ONLY does not apply to this existing ancestor.
                    if kind == 0 and not flags & 8 and sid not in self.trusted and mask & (0xD0000 | 0x40 | 0x50000000):
                        _fail('snapshot_permissions_invalid')
            return owner_sid, (ctl.value & 0x1004, tuple(entries))
        finally:
            if sd:
                self.free(sd)

    def _descriptor(self):
        sd = w.LPVOID()
        sddl = 'O:' + self.sid + 'D:P' + ''.join('(A;;FA;;;' + x + ')' for x in dict.fromkeys((self.sid, 'S-1-5-18')))
        self._ok(self.sd_convert(sddl, 1, c.byref(sd), None))
        try:
            self._ok(self.valid_sd(sd))
            ctl, rev = w.WORD(), w.DWORD()
            self._ok(self.control(sd, c.byref(ctl), c.byref(rev)))
            if ctl.value & 0x1004 != 0x1004:
                _fail('snapshot_permissions_invalid')
        except BaseException:
            self.free(sd)
            raise
        return sd

    def streams(self, path, directory):
        class Stream(c.Structure):
            _fields_ = [('size', c.c_longlong), ('name', w.WCHAR * 296)]
        value = Stream()
        handle = self.first_stream(path, 0, c.byref(value), 0)
        if handle == c.c_void_p(-1).value:
            if c.get_last_error() == 38 and directory:
                return
            _fail('snapshot_file_invalid')
        try:
            if directory or value.name != '::$DATA':
                _fail('snapshot_file_invalid')
            if self.next_stream(handle, c.byref(value)) or c.get_last_error() != 38:
                _fail('snapshot_file_invalid')
        finally:
            self.find_close(handle)

    def info(self, handle, private, *, directory):
        self._no_impersonation()
        class ID(c.Structure):
            _fields_ = [('volume', c.c_ulonglong), ('value', c.c_ubyte * 16)]
        class Standard(c.Structure):
            _fields_ = [('allocation', c.c_longlong), ('size', c.c_longlong), ('links', w.DWORD), ('pending', c.c_ubyte), ('directory', c.c_ubyte)]
        class Basic(c.Structure):
            _fields_ = [('creation', c.c_longlong), ('access', c.c_longlong), ('write', c.c_longlong), ('change', c.c_longlong), ('attributes', w.DWORD)]
        ident, standard, basic = ID(), Standard(), Basic()
        for number, obj in ((18, ident), (1, standard), (0, basic)):
            self._ok(self.get_info(handle, number, c.byref(obj), c.sizeof(obj)))
        if (self.get_type(handle) != 1 or basic.attributes & (0x400 | 0x1000) or
                bool(standard.directory) != directory or standard.pending):
            _fail('snapshot_file_invalid')
        owner, acl = self._acl(handle, private)
        flags, fsname = w.DWORD(), c.create_unicode_buffer(32)
        self._ok(self.volume_info(handle, None, 0, None, None, c.byref(flags), fsname, 32))
        if fsname.value != 'NTFS' or flags.value & 0x400008 != 0x400008:
            _fail('filesystem_security_unsupported')
        return _Info((ident.volume, bytes(ident.value)), directory, standard.size,
                     standard.links, basic.write, basic.change, owner, acl)

    def directory(self, path, parent=None, name=None):
        self._no_impersonation()
        if self.drive_type(path[:3]) != 3:
            _fail('filesystem_security_unsupported')
        handle = self.create(path, 0x20080, 3, None, 3, 0x02200000, None)
        if handle == c.c_void_p(-1).value:
            _fail('snapshot_io_failed')
        try:
            tags = (w.DWORD * 2)()
            self._ok(self.get_info(handle, 9, tags, c.sizeof(tags)))
            if tags[0] & 0x400:
                _fail('snapshot_file_invalid')
            target = c.create_unicode_buffer(512)
            count = self.final_path(handle, target, 512, 0)
            if not 0 < count < 512 or target.value[4:].rstrip('\\').casefold() != path.rstrip('\\').casefold():
                _fail('snapshot_path_invalid')
            self.streams(path, True)
        except BaseException:
            self.close_handle(handle)
            raise
        return handle

    def mkdir(self, path, parent, name):
        sd = self._descriptor()
        try:
            if not self.mkdir_api(path, c.byref(self.SA(c.sizeof(self.SA), sd, False))):
                if c.get_last_error() in (80, 183):
                    _fail('snapshot_destination_exists')
                _fail('snapshot_io_failed')
        finally:
            self.free(sd)

    def create_file(self, path, parent, name, created):
        import msvcrt
        sd = self._descriptor()
        handle, fd = None, None
        try:
            handle = self.create(path, 0xC0020000, 0, c.byref(self.SA(c.sizeof(self.SA), sd, False)), 1, 0x200080, None)
            if handle == c.c_void_p(-1).value:
                handle = None
                _fail('snapshot_destination_exists' if c.get_last_error() in (80, 183) else 'snapshot_io_failed')
            # Record creation before any fallible CRT transfer/configuration.
            # A CREATE_NEW collision never invokes this ownership callback.
            created()
            fd = msvcrt.open_osfhandle(handle, os.O_BINARY | os.O_RDWR)
            handle = None  # the CRT descriptor owns the HANDLE from here
            os.set_inheritable(fd, False)
            return fd
        except BaseException:
            # Close at most once, without replacing the original exception.
            # The caller keeps an unknown journal entry on any such failure.
            try:
                if fd is not None:
                    os.close(fd)
                elif handle is not None:
                    self.close_handle(handle)
            except BaseException:
                pass
            raise
        finally:
            self.free(sd)

    def read_file(self, path, parent, name):
        import msvcrt
        handle = self.create(path, 0x80020080, 3, None, 3, 0x200080, None)
        if handle == c.c_void_p(-1).value:
            _fail('snapshot_io_failed')
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_BINARY | os.O_RDONLY)
        except BaseException:
            self.close_handle(handle)
            raise
        try:
            os.set_inheritable(fd, False)
            tags = (w.DWORD * 2)()
            self._ok(self.get_info(handle, 9, tags, c.sizeof(tags)))
            if tags[0] & 0x400:
                _fail('snapshot_file_invalid')
            self.streams(path, False)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def file_info(self, fd):
        import msvcrt
        return self.info(msvcrt.get_osfhandle(fd), True, directory=False)

    def close_directory(self, handle):
        if not self.close_handle(handle):
            _fail('snapshot_io_failed')

    def sync_directory(self, handle):
        return None


class _Linux:
    def __init__(self):
        if (sys.platform != 'linux' or platform.machine().lower() not in ('x86_64', 'aarch64')
                or c.sizeof(c.c_long) != 8 or c.sizeof(c.c_void_p) != 8):
            _fail('filesystem_security_unsupported')
        self.libc = c.CDLL(None, use_errno=True)
        self.fstatfs = self.libc.fstatfs
        self.fstatfs.argtypes, self.fstatfs.restype = [c.c_int, c.c_void_p], c.c_int

    def _volume(self, fd):
        class FS(c.Structure):
            _fields_ = [('kind', c.c_long), ('bsize', c.c_long), ('blocks', c.c_ulong),
                ('bfree', c.c_ulong), ('bavail', c.c_ulong), ('files', c.c_ulong),
                ('ffree', c.c_ulong), ('fsid', c.c_int * 2), ('namelen', c.c_long),
                ('frsize', c.c_long), ('flags', c.c_long), ('spare', c.c_long * 4)]
        value = FS()
        if self.fstatfs(fd, c.byref(value)) or value.kind & 0xFFFFFFFF not in (0xEF53, 0x58465342, 0x9123683E, 0x01021994):
            _fail('filesystem_security_unsupported')

    def info(self, fd, private, *, directory):
        self._volume(fd)
        s = os.fstat(fd)
        if (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)) is False:
            _fail('snapshot_file_invalid')
        mode = stat.S_IMODE(s.st_mode)
        if private:
            if s.st_uid != os.geteuid() or mode != (0o700 if directory else 0o600):
                _fail('snapshot_permissions_invalid')
        elif s.st_uid not in (0, os.geteuid()) or mode & 0o022:
            _fail('snapshot_permissions_invalid')
        return _Info((s.st_dev, s.st_ino), directory, s.st_size, s.st_nlink,
                     s.st_mtime_ns, s.st_ctime_ns, s.st_uid, mode)

    def directory(self, path, parent=None, name=None):
        return os.open(path if parent is None else name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            **({} if parent is None else {'dir_fd': parent}))

    def mkdir(self, path, parent, name):
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            _fail('snapshot_destination_exists')

    def create_file(self, path, parent, name, created):
        try:
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600, dir_fd=parent)
        except FileExistsError:
            _fail('snapshot_destination_exists')
        try:
            created()
            os.fchmod(fd, 0o600)
        except BaseException:
            try:
                os.close(fd)
            except BaseException:
                pass
            raise
        return fd

    def read_file(self, path, parent, name):
        return os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)

    def file_info(self, fd):
        return self.info(fd, True, directory=False)

    def close_directory(self, fd):
        os.close(fd)

    def sync_directory(self, fd):
        os.fsync(fd)
        return True


class _Capability(metaclass=_SafeMeta):
    def __init__(self, *, _key=None):
        if _key is not _KEY:
            _fail('snapshot_inactive')
        self._pid, self._thread, self._active = os.getpid(), threading.get_ident(), True

    def __repr__(self):
        return '<snapshot-file-capability>'

    def _assert(self):
        if not self._active:
            _fail('snapshot_inactive')
        if self._pid != os.getpid() or self._thread != threading.get_ident():
            _fail('snapshot_owner_mismatch')

    @_safe()
    def __enter__(self):
        self._assert()
        return self


class TrustedParent(_Capability):
    def _check(self):
        self._assert()
        for index, (path, handle, original) in enumerate(self._chain):
            latest = self._os.info(handle, index == len(self._chain) - 1, directory=True)
            if latest.directory_key() != original.directory_key():
                _fail('snapshot_identity_changed')
            before = os.lstat(path)
            if stat.S_ISLNK(before.st_mode) or getattr(before, 'st_file_attributes', 0) & 0x400:
                _fail('snapshot_identity_changed')
            if not _matches_lstat(original, before):
                _fail('snapshot_identity_changed')

    @_safe()
    def close(self):
        self._assert()
        self._active = False
        failed = False
        for _, handle, _ in reversed(self._chain):
            try:
                self._os.close_directory(handle)
            except Exception:
                failed = True
        if failed:
            _fail('snapshot_io_failed')

    @_safe()
    def __exit__(self, kind, value, traceback):
        try:
            self.close()
        except Exception:
            if kind is None or issubclass(kind, Exception):
                raise
        return False


@_safe('filesystem_security_unsupported')
def open_trusted_parent(path, *, trusted_parent_ack):
    anchor, parts = _path(path)
    if trusted_parent_ack is not True:
        _fail('snapshot_permissions_invalid')
    adapter = _Windows() if os.name == 'nt' else _Linux()
    if os.name == 'nt' and adapter.drive_type(anchor) != 3:
        _fail('filesystem_security_unsupported')
    chain, running = [], anchor
    try:
        allparts = [None, *parts]
        for i, part in enumerate(allparts):
            if part is not None:
                running = os.path.join(running, part)
            before = os.lstat(running)
            if not stat.S_ISDIR(before.st_mode) or getattr(before, 'st_file_attributes', 0) & 0x400:
                _fail('snapshot_path_invalid')
            handle = adapter.directory(running, chain[-1][1] if chain else None, part)
            try:
                info = adapter.info(handle, i == len(allparts) - 1, directory=True)
                if not _matches_lstat(info, before):
                    _fail('snapshot_identity_changed')
            except BaseException:
                adapter.close_directory(handle)
                raise
            chain.append((running, handle, info))
        result = TrustedParent(_key=_KEY)
        result._os, result._path, result._chain = adapter, path, chain
        return result
    except BaseException:
        for _, handle, _ in reversed(chain):
            try:
                adapter.close_directory(handle)
            except Exception:
                pass
        raise


class ReadDirectory(_Capability):
    def _check(self):
        self._assert()
        self._parent._check()
        now = self._os.info(self._handle, True, directory=True)
        if now.directory_key() != self._original.directory_key():
            _fail('snapshot_identity_changed')
        if self._os.directory is not None:
            # Re-open the name with no-follow, compare against the held handle.
            handle = self._os.directory(self._path, self._parent._chain[-1][1], self._basename)
            try:
                other = self._os.info(handle, True, directory=True)
                if other.identity != now.identity:
                    _fail('snapshot_identity_changed')
            finally:
                self._os.close_directory(handle)

    def _cap(self, name):
        return self._limits.max_metadata_bytes if name in ('schema.json', 'manifest.json', '.manifest.part') else self._limits.max_file_bytes

    def _open(self, name, *, owned=False):
        self._check()
        _name(name, marker=not owned)
        if owned and name not in self._journal:
            _fail('snapshot_file_invalid')
        path = os.path.join(self._path, name)
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode) or getattr(before, 'st_file_attributes', 0) & 0x400 or before.st_nlink != 1:
            _fail('snapshot_file_invalid')
        fd = self._os.read_file(path, self._handle, name)
        try:
            info = self._os.file_info(fd)
            if info.links != 1 or info.size > self._cap(name):
                _fail('snapshot_resource_limit' if info.size > self._cap(name) else 'snapshot_file_invalid')
            if not _matches_lstat(info, before):
                _fail('snapshot_identity_changed')
            if owned and info != self._journal[name]:
                _fail('snapshot_identity_changed')
            reader = BoundedReader(_key=_KEY)
            reader._directory, reader._name, reader._fd, reader._info = self, name, fd, info
            reader._read, reader._buffer = 0, bytearray()
            self._readers.add(reader)
            return reader
        except BaseException:
            os.close(fd)
            raise

    @_safe()
    def open_file(self, name):
        return self._open(name)

    @_safe()
    def file_names(self):
        self._check()
        names = []
        with os.scandir(self._path if os.name == 'nt' else self._handle) as scan:
            for entry in scan:
                if len(names) >= self._limits.max_files:
                    _fail('snapshot_resource_limit')
                _name(entry.name, marker=True)
                if not entry.is_file(follow_symlinks=False):
                    _fail('snapshot_file_invalid')
                names.append(entry.name)
        self._check()
        return tuple(sorted(names))

    @_safe()
    def close(self):
        self._assert()
        failed = False
        for reader in tuple(self._readers):
            try:
                reader.close()
            except Exception:
                failed = True
        self._active = False
        self._os.close_directory(self._handle)
        if failed:
            _fail('snapshot_io_failed')

    @_safe()
    def __exit__(self, kind, value, traceback):
        try:
            self.close()
        except Exception:
            if kind is None or issubclass(kind, Exception):
                raise
        return False


def _directory(parent, basename, limits, *, create):
    if type(parent) is not TrustedParent or type(limits) is not FileLimits:
        _fail('snapshot_limits_invalid')
    if type(basename) is not str or not _BASE_NAME.fullmatch(basename):
        _fail('snapshot_name_invalid')
    parent._check()
    path, adapter = os.path.join(parent._path, basename), parent._os
    created = False
    try:
        if create:
            adapter.mkdir(path, parent._chain[-1][1], basename)
            created = True
        handle = adapter.directory(path, parent._chain[-1][1], basename)
        try:
            if create and os.name == 'posix':
                os.fchmod(handle, 0o700)
            info = adapter.info(handle, True, directory=True)
            if info.identity[0] != parent._chain[-1][2].identity[0]:
                _fail('filesystem_security_unsupported')
        except BaseException:
            adapter.close_directory(handle)
            raise
        obj = (OwnedDirectory if create else ReadDirectory)(_key=_KEY)
        obj._parent, obj._os, obj._path, obj._basename = parent, adapter, path, basename
        obj._handle, obj._original, obj._limits, obj._readers = handle, info, limits, set()
        if create:
            obj._journal, obj._total, obj._published, obj._aborted, obj._failed = {}, 0, False, False, False
            obj._writing = False
            obj._commit_uncertain = False
        return obj
    except Exception:
        if created:
            # Creation without a safely captured identity is not deletion authority.
            _fail('snapshot_cleanup_failed')
        raise


@_safe()
def reserve_directory(parent, basename, *, limits=DEFAULT_FILE_LIMITS):
    return _directory(parent, basename, limits, create=True)


@_safe()
def open_directory(parent, basename, *, limits=DEFAULT_FILE_LIMITS):
    return _directory(parent, basename, limits, create=False)


class OwnedDirectory(ReadDirectory):
    def _write(self, name, blocks):
        self._check()
        if self._published or self._aborted or self._failed or self._writing or self._commit_uncertain:
            _fail('snapshot_inactive')
        if name in self._journal:
            _fail('snapshot_destination_exists')
        if name != '.manifest.part' and len(self._journal) + 2 > self._limits.max_files:
            _fail('snapshot_resource_limit')
        path = os.path.join(self._path, name)
        fd = None
        base_error = False
        self._writing = True
        try:
            fd = self._os.create_file(path, self._handle, name,
                lambda: self._journal.__setitem__(name, None))
            first = self._os.file_info(fd)
            self._journal[name] = first
            if first.links != 1 or first.identity[0] != self._original.identity[0]:
                _fail('snapshot_file_invalid')
            count, digest = 0, hashlib.sha256()
            for block in blocks:
                if type(block) is not bytes or not 1 <= len(block) <= 65536:
                    _fail('snapshot_file_invalid')
                if count + len(block) > self._cap(name) or (name != '.manifest.part' and self._total + len(block) > self._limits.max_total_bytes):
                    _fail('snapshot_resource_limit')
                position = 0
                while position < len(block):
                    self._check()
                    current = self._os.file_info(fd)
                    if current.identity != first.identity or current.links != 1:
                        _fail('snapshot_identity_changed')
                    try:
                        n = os.write(fd, block[position:])
                    except InterruptedError:
                        continue
                    if n <= 0:
                        _fail('snapshot_io_failed')
                    position += n
                    count += n
                    if name != '.manifest.part':
                        self._total += n
                digest.update(block)
            os.fsync(fd)
            final = self._os.file_info(fd)
            if final.identity != first.identity or final.size != count or final.links != 1:
                _fail('snapshot_identity_changed')
            self._journal[name] = final
            return FileDigest(name, count, digest.hexdigest())
        except BaseException as error:
            base_error = not isinstance(error, Exception)
            self._failed = True
            # Current size/time can change during our own failed partial write;
            # capture it only while still holding our original object handle.
            try:
                current = self._os.file_info(fd) if fd is not None else None
                if current is not None and self._journal.get(name) is not None and current.identity == self._journal[name].identity:
                    self._journal[name] = current
            except Exception:
                pass
            raise
        finally:
            self._writing = False
            try:
                if fd is not None:
                    os.close(fd)
            except Exception:
                self._failed = True
                # A failed close leaves handle ownership uncertain. Do not
                # reuse/retry its integer or infer later deletion authority.
                self._journal[name] = None
                if not base_error:
                    raise

    @_safe()
    def write_file(self, name, blocks):
        _name(name)
        return self._write(name, blocks)

    @_safe()
    def open_owned(self, name):
        return self._open(name, owned=True)

    def _unlink(self, name):
        os.unlink(os.path.join(self._path, name) if os.name == 'nt' else name,
                  **({} if os.name == 'nt' else {'dir_fd': self._handle}))

    @_safe()
    def abort(self):
        self._assert()
        if self._published:
            _fail('snapshot_inactive')
        if self._commit_uncertain:
            _fail('snapshot_cleanup_failed')
        if self._aborted:
            return
        if self._readers or self._writing:
            _fail('snapshot_cleanup_failed')
        failed = False
        try:
            self._check()
        except Exception:
            _fail('snapshot_cleanup_failed')
        for name, original in tuple(self._journal.items()):
            try:
                if original is None:
                    _fail('snapshot_cleanup_failed')
                fd = self._os.read_file(os.path.join(self._path, name), self._handle, name)
                try:
                    now = self._os.file_info(fd)
                    if now != original or now.links != 1:
                        _fail('snapshot_cleanup_failed')
                finally:
                    os.close(fd)
                self._unlink(name)
                del self._journal[name]
            except Exception:
                failed = True
        try:
            self._check()
            # rmdir itself is the empty-only assertion. Never enumerate to delete.
            if not failed:
                self._os.close_directory(self._handle)
                self._handle = None
                os.rmdir(self._path if os.name == 'nt' else self._basename,
                    **({} if os.name == 'nt' else {'dir_fd': self._parent._chain[-1][1]}))
                self._aborted = True
        except Exception:
            failed = True
        if failed:
            _fail('snapshot_cleanup_failed')

    @_safe()
    def publish_marker(self, data):
        self._check()
        if type(data) is not bytes or len(data) > self._limits.max_metadata_bytes:
            _fail('snapshot_resource_limit')
        if self._published or self._failed or self._aborted or self._readers or self._writing or self._commit_uncertain:
            _fail('snapshot_inactive')
        digest = self._write('.manifest.part', (data[i:i + 65536] for i in range(0, len(data), 65536)))
        part, final = os.path.join(self._path, '.manifest.part'), os.path.join(self._path, 'manifest.json')
        fd = self._os.read_file(part, self._handle, '.manifest.part')
        try:
            if self._os.file_info(fd) != self._journal['.manifest.part']:
                _fail('snapshot_identity_changed')
        finally:
            os.close(fd)
        # Protect the external commit boundary before invoking the OS. A
        # synchronous exception can arrive after the link has taken effect.
        self._commit_uncertain = True
        try:
            if os.name == 'nt':
                os.link(part, final, follow_symlinks=False)
            else:
                os.link('.manifest.part', 'manifest.json', src_dir_fd=self._handle,
                        dst_dir_fd=self._handle, follow_symlinks=False)
            self._published = True
            self._commit_uncertain = False
        except BaseException:
            self._failed = True
            try:
                self._reconcile_link_attempt()
            except BaseException:
                # Retain all data on an unprovable outcome. Never replace the
                # original BaseException with a metadata/close/cleanup error.
                pass
            raise
        codes, cleanup, synced = [], True, None
        try:
            for name in ('.manifest.part', 'manifest.json'):
                fd = self._os.read_file(os.path.join(self._path, name), self._handle, name)
                try:
                    now = self._os.file_info(fd)
                    if now.identity != self._journal['.manifest.part'].identity or now.links != 2 or now.size != digest.byte_count:
                        _fail('snapshot_identity_changed')
                finally:
                    os.close(fd)
        except Exception:
            cleanup = False
            codes.append('published_identity_check_failed')
        if cleanup:
            try:
                self._unlink('.manifest.part')
                del self._journal['.manifest.part']
            except Exception:
                cleanup = False
                codes.append('part_cleanup_failed')
        try:
            synced = self._os.sync_directory(self._handle)
        except Exception:
            synced = False
            codes.append('directory_sync_failed')
        status = 'published_cleanup_pending' if not cleanup else ('published_durability_pending' if synced is False else 'published')
        return PublishResult(status, True, cleanup, synced, tuple(codes),
                             FileDigest('manifest.json', digest.byte_count, digest.sha256))

    def _reconcile_link_attempt(self):
        """Resolve only our known part/final identities; do not delete anything."""
        self._check()
        expected = self._journal['.manifest.part']
        fd = self._os.read_file(os.path.join(self._path, '.manifest.part'), self._handle, '.manifest.part')
        try:
            part = self._os.file_info(fd)
        finally:
            os.close(fd)
        if (part.identity != expected.identity or part.size != expected.size or
                part.owner != expected.owner or part.access != expected.access):
            _fail('snapshot_identity_changed')
        try:
            os.lstat(os.path.join(self._path, 'manifest.json'))
        except FileNotFoundError:
            self._check()
            if part.links == 1:
                self._commit_uncertain = False  # no final and original part intact
            return
        fd = self._os.read_file(os.path.join(self._path, 'manifest.json'), self._handle, 'manifest.json')
        try:
            final = self._os.file_info(fd)
        finally:
            os.close(fd)
        if (final.identity == expected.identity and final.size == expected.size and
                final.owner == expected.owner and final.access == expected.access and
                part.links == final.links == 2):
            self._published = True
            self._commit_uncertain = False

    @_safe()
    def close(self):
        self._assert()
        if self._writing:
            _fail('snapshot_inactive')
        failed = False
        for reader in tuple(self._readers):
            try:
                reader.close()
            except Exception:
                failed = True
        self._active = False
        if self._handle is not None:
            self._os.close_directory(self._handle)
            self._handle = None
        if failed:
            _fail('snapshot_io_failed')

    @_safe()
    def __exit__(self, kind, value, traceback):
        cleanup_error = False
        try:
            if not self._published:
                self.abort()
        except Exception:
            cleanup_error = True
        finally:
            try:
                self.close()
            except Exception:
                cleanup_error = True
        if cleanup_error and (kind is None or issubclass(kind, Exception)):
            _fail('snapshot_cleanup_failed')
        return False


class BoundedReader(_Capability):
    def _check(self):
        self._assert()
        self._directory._check()
        now = self._directory._os.file_info(self._fd)
        if now != self._info:
            _fail('snapshot_identity_changed')
        path = os.path.join(self._directory._path, self._name)
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode) or getattr(before, 'st_file_attributes', 0) & 0x400 or before.st_nlink != 1:
            _fail('snapshot_identity_changed')
        if not _matches_lstat(self._info, before):
            _fail('snapshot_identity_changed')

    def _read_os(self, size):
        self._check()
        block = os.read(self._fd, size)
        self._read += len(block)
        self._check()
        if self._read > self._info.size or (not block and self._read != self._info.size):
            _fail('snapshot_identity_changed')
        return block

    @_safe()
    def read_chunk(self, size):
        _number(size, 65536)
        self._check()
        if self._buffer:
            result = bytes(self._buffer[:size])
            del self._buffer[:size]
            return result
        return self._read_os(size)

    @_safe()
    def read_bounded(self, max_bytes):
        _number(max_bytes, self._directory._limits.max_metadata_bytes)
        if self._name not in ('schema.json', 'manifest.json'):
            _fail('snapshot_file_invalid')
        result = bytearray()
        while len(result) <= max_bytes:
            block = self.read_chunk(min(65536, max_bytes + 1 - len(result)))
            if not block:
                return bytes(result)
            result.extend(block)
        _fail('snapshot_resource_limit')

    @_safe()
    def readline(self, limit):
        _number(limit, self._directory._limits.max_record_bytes)
        self._check()
        while True:
            pos = self._buffer.find(b'\n')
            if pos >= 0:
                if pos + 1 > limit:
                    _fail('snapshot_resource_limit')
                result = bytes(self._buffer[:pos + 1])
                del self._buffer[:pos + 1]
                return result
            if len(self._buffer) > limit:
                _fail('snapshot_resource_limit')
            block = self._read_os(min(65536, limit + 1 - len(self._buffer)))
            if not block:
                result = bytes(self._buffer)
                self._buffer.clear()
                return result
            self._buffer.extend(block)

    @_safe()
    def close(self):
        self._assert()
        failure = False
        try:
            self._check()
        except Exception:
            failure = True
        finally:
            self._active = False
            os.close(self._fd)
            self._directory._readers.discard(self)
        if failure:
            _fail('snapshot_identity_changed')

    @_safe()
    def __exit__(self, kind, value, traceback):
        try:
            self.close()
        except Exception:
            if kind is None or issubclass(kind, Exception):
                raise
        return False
