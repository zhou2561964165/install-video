"""Pure bounded snapshot wire codec; no DB, configuration, filesystem or network.

Physical values survive independently of business validity. A codec roundtrip
does not authorize import. Mutable byte wrappers decode as bytes; aware datetime
timezone names are not serialized, only wall fields, offset and fold.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps
import json
import math
import re
from typing import NoReturn
from zoneinfo import ZoneInfo


_CODES = frozenset({
    'codec_limits_invalid', 'codec_type_unsupported', 'codec_value_invalid',
    'codec_cell_limit', 'codec_row_limit', 'codec_record_limit',
    'codec_shape_invalid', 'codec_tag_invalid', 'codec_column_mismatch',
    'json_invalid', 'json_noncanonical', 'json_duplicate_key', 'json_resource_limit',
    'source_profile_unsupported',
})
TAGS = frozenset({'n', 'b', 'i', 'f', 's', 'd', 'x', 'date', 'dt', 'dt_naive'})
_HARD = {
    'max_cell_bytes': 1 << 20, 'max_row_bytes': 4 << 20,
    'max_record_bytes': 32 << 20, 'max_columns': 96,
    'max_integer_digits': 4096, 'max_decimal_digits': 4096,
    'max_decimal_exponent': 4096, 'max_json_depth': 32, 'max_json_nodes': 100_000,
}
_INT = re.compile(r'(?:0|-[1-9][0-9]*|[1-9][0-9]*)\Z')
_DIGITS = re.compile(r'[0-9]+\Z')
_OFFSET = re.compile(r'([+-])([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]{6}))?)?\Z')


class SnapshotError(RuntimeError):
    """Constant codes only; never retain source values or original exceptions."""

    def __init__(self, code):
        self.code = code if type(code) is str and code in _CODES else 'codec_value_invalid'
        super().__init__(self.code)


def _raise_safe(code: str) -> NoReturn:
    # `from None` hides a context but leaves it reachable. Clear the same safe
    # exception and bare re-raise, including inside a caller's active except.
    error = SnapshotError(code)
    try:
        raise error
    except SnapshotError:
        error.__context__ = None
        error.__cause__ = None
        raise


def _safe(function):
    @wraps(function)
    def boundary(*args, **kwargs):
        code = None
        try:
            return function(*args, **kwargs)
        except SnapshotError as error:
            code = error.code
        except Exception:
            code = 'codec_value_invalid'
        # Do not retain either exception through its context or traceback.
        _raise_safe(code)
    return boundary


@dataclass(frozen=True, slots=True, init=False)
class CodecLimits:
    max_cell_bytes: int = 1 << 20
    max_row_bytes: int = 4 << 20
    max_record_bytes: int = 32 << 20
    max_columns: int = 96
    max_integer_digits: int = 4096
    max_decimal_digits: int = 4096
    max_decimal_exponent: int = 4096
    max_json_depth: int = 32
    max_json_nodes: int = 100_000

    def __init__(self, *args, **values):
        # Keep invalid constructor arguments behind the same fixed-code API,
        # rather than dataclass TypeError text echoing an unknown argument name.
        if args or any(name not in _HARD for name in values):
            _raise_safe('codec_limits_invalid')
        for name, ceiling in _HARD.items():
            object.__setattr__(self, name, values.get(name, ceiling))
        self.__post_init__()

    def __post_init__(self):
        for name, ceiling in _HARD.items():
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                _raise_safe('codec_limits_invalid')


DEFAULT_LIMITS = CodecLimits()


def _limits(limits):
    if type(limits) is not CodecLimits:
        _raise_safe('codec_limits_invalid')
    limits.__post_init__()


def _integer_text(value, digits):
    # Every allowed decimal integer is <10**digits <2**(4*digits).
    # This cheap conservative test avoids str(giantint) and Python's digit cap.
    if value.bit_length() > digits * 4:
        _raise_safe('codec_value_invalid')
    # Compare before str too: bitlength is deliberately only a coarse bound.
    if abs(value) >= 10 ** digits:
        _raise_safe('codec_value_invalid')
    if value == 0:
        return '0'
    remainder = abs(value)
    chunks = []
    while remainder:
        remainder, chunk = divmod(remainder, 1_000_000_000)
        # Only convert <=9 decimal digits; independent of sys's global setting.
        chunks.append(str(chunk))
    return ('-' if value < 0 else '') + chunks[-1] + ''.join(
        chunk.zfill(9) for chunk in reversed(chunks[:-1]))


def _integer_from_text(text):
    negative = text.startswith('-')
    start = 1 if negative else 0
    value = 0
    for index in range(start, len(text), 9):
        chunk = text[index:index + 9]
        value = value * (10 ** len(chunk)) + int(chunk)
    return -value if negative else value


def _text_size(value, ceiling, code):
    if len(value) > ceiling:
        _raise_safe(code)
    # Strict UTF8 rejects lone surrogate codepoints; NUL remains valid.
    size = len(value.encode('utf8', errors='strict'))
    if size > ceiling:
        _raise_safe(code)
    return size


def _cell_size(cell, limits):
    tag = cell[0]
    if tag in ('n', 'b'):
        size = 1
    elif tag == 's':
        size = _text_size(cell[1], limits.max_cell_bytes, 'codec_cell_limit')
    elif tag == 'x':
        text = cell[1]
        size = (len(text) // 4) * 3 - (2 if text.endswith('==') else 1 if text.endswith('=') else 0)
    elif tag == 'd':
        size = 1 + len(cell[2]) + len(str(cell[3]))
    elif tag in ('dt', 'dt_naive'):
        size = len(cell[1]) + 1
    else:
        size = len(cell[1])
    if size > limits.max_cell_bytes:
        _raise_safe('codec_cell_limit')
    return size


def _decimal_tuple_bounded(value, limits):
    # adjusted = exponent + coefficient_digit_count - 1 (also for zero's
    # one-digit coefficient). Thus a legal exponent must lie in this interval.
    # same_quantum tests exponents without expanding/copying the coefficient;
    # it is quiet and independent of the ambient Decimal context. Each probe
    # constructs only a one-digit zero, and at most max_decimal_digits probes
    # run. A huge negative exponent cancelling huge digits still has no match.
    adjusted = value.adjusted()
    low = max(-limits.max_decimal_exponent, adjusted - limits.max_decimal_digits + 1)
    high = min(limits.max_decimal_exponent, adjusted)
    for exponent in range(high, low - 1, -1):
        if value.same_quantum(Decimal((0, (0,), exponent))):
            parts = value.as_tuple()  # coefficient now proven within local cap
            if (len(parts.digits) != adjusted - exponent + 1
                    or parts.exponent != exponent):
                _raise_safe('codec_value_invalid')
            return parts
    _raise_safe('codec_value_invalid')


def _encode_cell(value, limits):
    kind = type(value)
    if value is None:
        cell = ['n']
    elif kind is bool:
        cell = ['b', value]
    elif kind is int:
        cell = ['i', _integer_text(value, limits.max_integer_digits)]
    elif kind is float:
        if not math.isfinite(value):
            _raise_safe('codec_value_invalid')
        cell = ['f', value.hex()]
    elif kind is str:
        _text_size(value, limits.max_cell_bytes, 'codec_cell_limit')
        cell = ['s', value]
    elif kind is Decimal:
        if not value.is_finite():
            _raise_safe('codec_value_invalid')
        parts = _decimal_tuple_bounded(value, limits)
        cell = ['d', parts.sign, ''.join(chr(48 + digit) for digit in parts.digits), parts.exponent]
    elif kind in (bytes, bytearray, memoryview):
        size = value.nbytes if kind is memoryview else len(value)
        if size > limits.max_cell_bytes:
            _raise_safe('codec_cell_limit')
        # bytes(memoryview) is explicitly logical C order, also for strided or
        # multidimensional views. Wrapper shape/strides are not serialized.
        cell = ['x', base64.b64encode(bytes(value)).decode('ascii')]
    elif kind is datetime:
        if value.tzinfo is None:
            cell = ['dt_naive', value.isoformat(timespec='microseconds'), value.fold]
        elif type(value.tzinfo) in (timezone, ZoneInfo):
            if value.utcoffset() is None:
                _raise_safe('codec_value_invalid')
            cell = ['dt', value.isoformat(timespec='microseconds'), value.fold]
        else:
            _raise_safe('codec_type_unsupported')
    elif kind is date:
        cell = ['date', value.isoformat()]
    else:
        _raise_safe('codec_type_unsupported')
    _cell_size(cell, limits)
    return cell


@_safe
def encode_cell(value: object, *, limits: CodecLimits = DEFAULT_LIMITS) -> list:
    """Encode one exact native physical value to its fixed tagged list."""
    _limits(limits)
    return _encode_cell(value, limits)


def _decode_cell(cell, limits):
    if type(cell) is not list or not 1 <= len(cell) <= 4:
        _raise_safe('codec_shape_invalid')
    tag = cell[0]
    if type(tag) is not str or tag not in TAGS:
        _raise_safe('codec_tag_invalid')
    arity = 1 if tag == 'n' else 4 if tag == 'd' else 3 if tag in ('dt', 'dt_naive') else 2
    if len(cell) != arity:
        _raise_safe('codec_shape_invalid')
    if tag == 'n':
        value = None
    elif tag == 'b':
        if type(cell[1]) is not bool:
            _raise_safe('codec_value_invalid')
        value = cell[1]
    else:
        text = cell[2] if tag == 'd' else cell[1]
        if type(text) is not str:
            _raise_safe('codec_value_invalid')
        if tag == 's':
            value = text
        elif tag == 'i':
            if len(text) > limits.max_integer_digits + (1 if text.startswith('-') else 0) or not _INT.fullmatch(text):
                _raise_safe('codec_value_invalid')
            value = _integer_from_text(text)
        elif tag == 'f':
            if len(text) > 32:
                _raise_safe('codec_value_invalid')
            value = float.fromhex(text)
            if not math.isfinite(value) or value.hex() != text:
                _raise_safe('codec_value_invalid')
        elif tag == 'd':
            sign, exponent = cell[1], cell[3]
            if (type(sign) is not int or sign not in (0, 1) or type(exponent) is not int
                    or abs(exponent) > limits.max_decimal_exponent or len(text) > limits.max_decimal_digits
                    or not _DIGITS.fullmatch(text)):
                _raise_safe('codec_value_invalid')
            digits = tuple(ord(char) - 48 for char in text)
            # Decimal(tuple) is exact and independent of current precision/traps.
            value = Decimal((sign, digits, exponent))
            parts = value.as_tuple()
            if parts.sign != sign or parts.digits != digits or parts.exponent != exponent:
                _raise_safe('codec_value_invalid')
        elif tag == 'x':
            if len(text) > 4 * ((limits.max_cell_bytes + 2) // 3):
                _raise_safe('codec_cell_limit')
            if len(text) % 4:
                _raise_safe('codec_value_invalid')
            _cell_size(cell, limits)  # decoded-size precheck before allocating
            value = base64.b64decode(text, validate=True)
            if base64.b64encode(value).decode('ascii') != text:
                _raise_safe('codec_value_invalid')
        elif tag == 'date':
            if len(text) != 10:
                _raise_safe('codec_value_invalid')
            value = date.fromisoformat(text)
            if value.isoformat() != text:
                _raise_safe('codec_value_invalid')
        else:
            fold = cell[2]
            if type(fold) is not int or fold not in (0, 1) or not 26 <= len(text) <= 42:
                _raise_safe('codec_value_invalid')
            wall = datetime.fromisoformat(text[:26])
            if wall.tzinfo is not None or wall.isoformat(timespec='microseconds') != text[:26]:
                _raise_safe('codec_value_invalid')
            if tag == 'dt_naive':
                value = wall.replace(fold=fold)
            else:
                # Some Python versions discard fractional offset seconds when
                # the whole HH:MM:SS portion is zero. Parse only our fixed,
                # bounded offset grammar, then reconstruct exact microseconds.
                match = _OFFSET.fullmatch(text[26:])
                if match is None:
                    _raise_safe('codec_value_invalid')
                sign, hours, minutes, seconds, micros = match.groups()
                hours, minutes = int(hours), int(minutes)
                seconds, micros = int(seconds or '0'), int(micros or '0')
                if hours >= 24 or minutes >= 60 or seconds >= 60:
                    _raise_safe('codec_value_invalid')
                offset = timedelta(hours=hours, minutes=minutes, seconds=seconds, microseconds=micros)
                if sign == '-':
                    offset = -offset
                value = wall.replace(tzinfo=timezone(offset), fold=fold)
            if value.isoformat(timespec='microseconds') != text:
                _raise_safe('codec_value_invalid')
    _cell_size(cell, limits)
    return value


@_safe
def decode_cell(cell: list, *, limits: CodecLimits = DEFAULT_LIMITS) -> object:
    """Recover one physical value; malformed/oversized cells are never repaired."""
    _limits(limits)
    return _decode_cell(cell, limits)


def _json_string_size(text, ceiling):
    if len(text) > ceiling:
        _raise_safe('json_resource_limit')
    size = 2
    for char in text:
        point = ord(char)
        if 0xD800 <= point <= 0xDFFF:
            _raise_safe('json_invalid')
        size += (2 if char in '"\\\b\f\n\r\t' else 6 if point < 32 or 127 <= point < 65536
                 else 12 if point >= 65536 else 1)
        if size > ceiling:
            _raise_safe('json_resource_limit')
    return size


def _json_measure(value, ceiling, limits):
    """Iterative type/resource/encoded-size check before JSON allocates strings."""
    stack = [(value, 0)]
    nodes = 0
    size = 1  # final LF
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > limits.max_json_nodes:
            _raise_safe('json_resource_limit')
        kind = type(item)
        if item is None:
            size += 4
        elif kind is bool:
            size += 4 if item else 5
        elif kind is int:
            size += len(_integer_text(item, limits.max_integer_digits))
        elif kind is str:
            size += _json_string_size(item, ceiling)
        elif kind in (list, dict):
            if depth + 1 > limits.max_json_depth:
                _raise_safe('json_resource_limit')
            count = len(item)
            projected = count if kind is list else count * 2
            if nodes + len(stack) + projected > limits.max_json_nodes:
                _raise_safe('json_resource_limit')
            size += 2 + max(0, count - 1) + (count if kind is dict else 0)
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        _raise_safe('json_invalid')
                    stack.append((key, depth + 1))
                    stack.append((child, depth + 1))
            else:
                stack.extend((child, depth + 1) for child in item)
        else:
            _raise_safe('json_invalid')
        if size > ceiling:
            _raise_safe('json_resource_limit')


def _byte_limit(max_bytes, limits):
    if type(max_bytes) is not int or not 1 <= max_bytes <= limits.max_record_bytes:
        _raise_safe('codec_limits_invalid')


def _canonical_json_bytes(value, max_bytes, limits):
    _json_measure(value, max_bytes, limits)
    # Serialize exact permitted JSON types after measuring. JSONEncoder's int
    # path uses global decimal-digit settings, so keep integers on our bounded
    # chunk conversion; its string encoder supplies the ensure_ascii contract.
    output = bytearray()
    stack = [(False, value)]
    while stack:
        raw, item = stack.pop()
        if raw:
            output.extend(item)
        elif item is None:
            output.extend(b'null')
        elif type(item) is bool:
            output.extend(b'true' if item else b'false')
        elif type(item) is int:
            output.extend(_integer_text(item, limits.max_integer_digits).encode('ascii'))
        elif type(item) is str:
            output.extend(json.dumps(item, ensure_ascii=True).encode('ascii'))
        elif type(item) is list:
            output.extend(b'[')
            stack.append((True, b']'))
            for index in range(len(item) - 1, -1, -1):
                stack.append((False, item[index]))
                if index:
                    stack.append((True, b','))
        else:
            output.extend(b'{')
            stack.append((True, b'}'))
            keys = sorted(item)
            for index in range(len(keys) - 1, -1, -1):
                key = keys[index]
                stack.append((False, item[key]))
                stack.append((True, b':'))
                stack.append((False, key))
                if index:
                    stack.append((True, b','))
    output.extend(b'\n')
    if len(output) > max_bytes:
        _raise_safe('json_resource_limit')
    return bytes(output)


@_safe
def canonical_json_bytes(value: object, *, max_bytes: int,
                         limits: CodecLimits = DEFAULT_LIMITS) -> bytes:
    """Bounded ASCII canonical JSON + LF; float values use explicit wire tags."""
    _limits(limits)
    _byte_limit(max_bytes, limits)
    return _canonical_json_bytes(value, max_bytes, limits)


def _json_preflight(data, limits):
    """Lexically cap JSON before recursive parser/token integer construction.

    This scanner is a resource guard, not a replacement grammar parser. strings
    count as nodes (including keys); brackets inside escaped strings do not.
    """
    depth = 0
    nodes = 0
    index = 0
    length = len(data)
    while index < length:
        char = data[index]
        if char > 127:
            _raise_safe('json_noncanonical')
        if char in (32, 9, 10, 13, 44, 58):
            index += 1
            continue
        if char in (91, 123):
            depth += 1
            nodes += 1
            if depth > limits.max_json_depth:
                _raise_safe('json_resource_limit')
            index += 1
        elif char in (93, 125):
            depth -= 1
            if depth < 0:
                _raise_safe('json_invalid')
            index += 1
        elif char == 34:
            nodes += 1
            index += 1
            closed = False
            while index < length:
                char = data[index]
                if char > 127:
                    _raise_safe('json_noncanonical')
                if char == 34:
                    index += 1
                    closed = True
                    break
                if char == 92:
                    # Escaped quote/backslash can't change string boundaries.
                    index += 2
                else:
                    index += 1
            if not closed:
                _raise_safe('json_invalid')
        else:
            start = index
            while index < length and data[index] not in (32, 9, 10, 13, 44, 58, 91, 93, 123, 125, 34):
                index += 1
                if index - start > limits.max_integer_digits + 1:
                    _raise_safe('json_resource_limit')
            token = data[start:index]
            if token not in (b'true', b'false', b'null'):
                digits = len(token) - (1 if token.startswith(b'-') else 0)
                if digits > limits.max_integer_digits:
                    _raise_safe('json_resource_limit')
                if not token or any(char not in b'-0123456789' for char in token):
                    _raise_safe('json_invalid')
            nodes += 1
        if nodes > limits.max_json_nodes:
            _raise_safe('json_resource_limit')
    if depth != 0:
        _raise_safe('json_invalid')


def _strict_json_loads(data, max_bytes, limits):
    if type(data) is not bytes:
        _raise_safe('json_invalid')
    if len(data) > max_bytes:
        _raise_safe('json_resource_limit')
    _json_preflight(data, limits)

    def pairs_hook(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _raise_safe('json_duplicate_key')
            result[key] = value
        return result

    def bounded_int(text):
        if len(text) - (1 if text.startswith('-') else 0) > limits.max_integer_digits:
            _raise_safe('json_resource_limit')
        return _integer_from_text(text)

    def refuse_number(text):
        _raise_safe('json_invalid')

    failed = False
    try:
        value = json.loads(data, object_pairs_hook=pairs_hook, parse_int=bounded_int,
                           parse_float=refuse_number, parse_constant=refuse_number)
    except SnapshotError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        failed = True
    if failed:
        _raise_safe('json_invalid')
    if _canonical_json_bytes(value, max_bytes, limits) != data:
        _raise_safe('json_noncanonical')
    return value


@_safe
def strict_json_loads(data: bytes, *, max_bytes: int,
                      limits: CodecLimits = DEFAULT_LIMITS) -> object:
    """Preflight bounded JSON, reject duplicate keys and require canonical bytes."""
    _limits(limits)
    _byte_limit(max_bytes, limits)
    return _strict_json_loads(data, max_bytes, limits)


def _columns(count, allowed_tags, limits):
    if count > limits.max_columns:
        _raise_safe('codec_column_mismatch')
    if allowed_tags is not None:
        if type(allowed_tags) is not tuple:
            _raise_safe('codec_shape_invalid')
        if len(allowed_tags) != count:
            _raise_safe('codec_column_mismatch')
        for column in allowed_tags:
            if (type(column) is not frozenset or not column
                    or any(type(tag) is not str or tag not in TAGS for tag in column)):
                _raise_safe('codec_tag_invalid')


@_safe
def encode_row(values: tuple | list, *, allowed_tags: tuple[frozenset[str], ...] | None = None,
               limits: CodecLimits = DEFAULT_LIMITS) -> bytes:
    """Encode one raw row as canonical JSONL; preserve physical business facts."""
    _limits(limits)
    if type(values) not in (list, tuple):
        _raise_safe('codec_shape_invalid')
    _columns(len(values), allowed_tags, limits)
    cells = []
    raw_bytes = 0
    for index, value in enumerate(values):
        cell = _encode_cell(value, limits)
        if allowed_tags is not None and cell[0] not in allowed_tags[index]:
            _raise_safe('codec_tag_invalid')
        raw_bytes += _cell_size(cell, limits)
        if raw_bytes > limits.max_row_bytes:
            _raise_safe('codec_row_limit')
        cells.append(cell)
    code = None
    try:
        return _canonical_json_bytes(cells, limits.max_record_bytes, limits)
    except SnapshotError as error:
        code = 'codec_record_limit' if error.code == 'json_resource_limit' else error.code
    _raise_safe(code)


@_safe
def decode_row(record: bytes, *, allowed_tags: tuple[frozenset[str], ...] | None = None,
               limits: CodecLimits = DEFAULT_LIMITS) -> tuple:
    """Decode exactly one complete bounded canonical JSONL row, never repair it."""
    _limits(limits)
    if type(record) is not bytes:
        _raise_safe('codec_shape_invalid')
    if len(record) > limits.max_record_bytes:
        _raise_safe('codec_record_limit')
    cells = _strict_json_loads(record, limits.max_record_bytes, limits)
    if type(cells) is not list:
        _raise_safe('codec_shape_invalid')
    _columns(len(cells), allowed_tags, limits)
    values = []
    raw_bytes = 0
    for index, cell in enumerate(cells):
        value = _decode_cell(cell, limits)
        if allowed_tags is not None and cell[0] not in allowed_tags[index]:
            _raise_safe('codec_tag_invalid')
        raw_bytes += _cell_size(cell, limits)
        if raw_bytes > limits.max_row_bytes:
            _raise_safe('codec_row_limit')
        values.append(value)
    return tuple(values)
