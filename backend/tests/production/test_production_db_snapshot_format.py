"""Synthetic wire-only contract. No DB/config/application imports or row fixtures."""
import base64
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, InvalidOperation, localcontext, getcontext
import hashlib
import json
import math
import random
import socket
import struct
import sys
import tracemalloc
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest

from tools.production_db_snapshot_format import (
    CodecLimits, DEFAULT_LIMITS, SnapshotError, canonical_json_bytes,
    strict_json_loads, encode_cell, decode_cell, encode_row, decode_row,
)
from tools.production_db_snapshot_profiles import KNOWN_PROFILE_IDS, require_source_profile


def rejected(call, code=None):
    caught = None
    try:
        call()
    except SnapshotError as error:
        caught = error
    assert caught is not None
    assert caught.__cause__ is None and caught.__context__ is None
    assert str(caught) == caught.code
    if code is not None:
        assert caught.code == code
    return caught


@pytest.mark.parametrize('value', [None, True, False, 0, 1, 2, -1, -(2**63), 2**100,
    '', 'pending', 'uncertain', 'unknown-new-state', 'not-a-date', '中文\0\n  ',
    ' { "z": 1, "a": 2 } \n', b'', bytes(range(256)), date(2024, 2, 29),
    datetime(2024, 11, 3, 1, 2, 3, 123456, fold=1),
    datetime(2024, 11, 3, 1, 2, 3, 123456, timezone(timedelta(hours=-4)), fold=1),
    datetime(2024, 1, 1, tzinfo=timezone(timedelta(seconds=9, microseconds=10))),
    Decimal('0'), Decimal('-0.000'), Decimal('1.2300'), Decimal('1E+4096'),
    0.0, -0.0, 5e-324, 1.7976931348623157e308])
def test_each_native_type_roundtrips(value):
    result = decode_cell(encode_cell(value))
    assert type(result) is type(value)
    if type(value) is float:
        assert result.hex() == value.hex()
    elif type(value) is Decimal:
        assert result.as_tuple() == value.as_tuple()
    elif type(value) is datetime:
        assert (result.isoformat(), result.fold) == (value.isoformat(), value.fold)
    else:
        assert result == value


def test_bytes_wrappers_and_noncontiguous_views_have_explicit_normalization():
    for value in (bytearray(b'abc'), memoryview(b'abc'), memoryview(b'abcdef')[::2]):
        result = decode_cell(encode_cell(value))
        assert type(result) is bytes and result == bytes(value)
    view = memoryview(b'abc')
    view.release()
    rejected(lambda: encode_cell(view))


def test_bool_and_sqlite_storage_ints_are_distinct_and_bad_business_facts_survive():
    values = ('synthetic-id', True, 1, 0, 2, -23, None, 'pending', 'uncertain',
              '{ "z":1, "a": 2 }', 'broken-date-text', 'new-unknown-state')
    record = encode_row(values)
    assert decode_row(record) == values
    assert record.endswith(b'\n') and b' ' not in record[:40]
    assert encode_cell(True) == ['b', True]
    assert encode_cell(1) == ['i', '1']
    assert encode_cell('2026-01-01 01:02:03.0000') == ['s', '2026-01-01 01:02:03.0000']


def test_json_is_canonical_ascii_sorted_and_lf_with_valid_unicode_pair():
    value = {'z': '\U0001f40b', 'a': ['\0', 2, None, False]}
    wire = canonical_json_bytes(value, max_bytes=4096)
    assert wire == b'{"a":["\\u0000",2,null,false],"z":"\\ud83d\\udc0b"}\n'
    assert strict_json_loads(wire, max_bytes=4096) == value
    assert hashlib.sha256(wire).hexdigest() == hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode() + b'\n').hexdigest()


def test_del_escape_size_is_rejected_before_json_allocation(monkeypatch):
    import tools.production_db_snapshot_format as module
    def encoder_must_not_run(*args, **kwargs):
        raise AssertionError('encoder_entered')
    monkeypatch.setattr(module.json, 'dumps', encoder_must_not_run)
    rejected(lambda: canonical_json_bytes('\x7f' * 10, max_bytes=23), 'json_resource_limit')


def test_integer_codec_and_generic_json_ignore_global_digit_conversion_limit():
    original = sys.get_int_max_str_digits()
    value = 10**4095 + 12345
    digits = '1' + '0' * 4090 + '12345'
    try:
        # Change only within this test, restore in finally. Production codec
        # must neither depend on this setting nor modify it.
        sys.set_int_max_str_digits(640)
        assert encode_cell(value) == ['i', digits]
        assert decode_cell(['i', digits]) == value
        encoded = canonical_json_bytes({'n': value}, max_bytes=8192)
        assert encoded == b'{"n":' + digits.encode('ascii') + b'}\n'
        assert strict_json_loads(encoded, max_bytes=8192) == {'n': value}
        assert sys.get_int_max_str_digits() == 640
    finally:
        sys.set_int_max_str_digits(original)


def test_zoneinfo_roundtrip_keeps_fields_offset_fold_and_instant_not_zone_key():
    # A synthetic valid TZif v1 fixed-offset zone; no local timezone files read.
    tzif = b'TZif\0' + b'\0' * 15 + struct.pack('!6i', 0, 0, 0, 0, 1, 4)
    tzif += struct.pack('!iBB', 3600, 0, 0) + b'SYN\0'
    zone = ZoneInfo.from_file(BytesIO(tzif), key='Synthetic/E1a')
    value = datetime(2024, 1, 1, 1, 2, 3, 456789, tzinfo=zone, fold=1)
    decoded = decode_cell(encode_cell(value))
    assert type(decoded.tzinfo) is timezone
    assert decoded.isoformat() == value.isoformat() and decoded.fold == value.fold
    assert decoded.timestamp() == value.timestamp()


@pytest.mark.parametrize('microseconds', [1, -1, 500000, -500000, 999999, -999999,
    1000000, -1000000, 1000001, -1000001, 0, 86_399_999_999, -86_399_999_999])
def test_aware_datetime_preserves_every_offset_precision_including_subsecond_zero_hour(microseconds):
    value = datetime(2024, 2, 29, 1, 2, 3, 456789,
                     tzinfo=timezone(timedelta(microseconds=microseconds)), fold=1)
    decoded = decode_cell(encode_cell(value))
    assert decoded.utcoffset() == value.utcoffset()
    assert decoded.isoformat() == value.isoformat() and decoded.fold == 1
    assert decoded.timestamp() == value.timestamp()


def test_multidimensional_memoryview_uses_explicit_c_order_bytes():
    view = memoryview(bytes(range(12))).cast('B', shape=[3, 4])
    assert decode_cell(encode_cell(view)) == view.tobytes(order='C')


def test_codec_constructor_and_public_argument_misuse_has_only_fixed_errors():
    rejected(lambda: CodecLimits(unrecognized_private_argument=Hostile()))
    rejected(lambda: encode_cell('x', unrecognized_private_argument=Hostile()))
    rejected(lambda: decode_row())


@pytest.mark.parametrize('data', [b'{}', b'{}\n\n', b'{ "a":1}\n', b'{"z":1,"a":2}\n',
    b'"\\u0061"\n', b'-0\n', b'[1,]\n', b'NaN\n', b'Infinity\n', b'1.0\n', b'1e2\n',
    b'{"a":1,"a":2}\n', b'{"a":1,"\\u0061":2}\n', b'"\\ud800"\n',
    b'"\\udc00"\n', b'"\\ud800x"\n', b'"\xff"\n', b'\xef\xbb\xbf{}\n'])
def test_strict_json_rejects_malformed_or_noncanonical(data):
    rejected(lambda: strict_json_loads(data, max_bytes=4096))


def test_duplicate_key_has_specific_code():
    rejected(lambda: strict_json_loads(b'{"a":1,"a":2}\n', max_bytes=100), 'json_duplicate_key')


def test_preflight_bounds_before_json_loads(monkeypatch):
    import tools.production_db_snapshot_format as module
    def parser_must_not_run(*args, **kwargs):
        raise AssertionError('parser_entered')
    monkeypatch.setattr(module.json, 'loads', parser_must_not_run)
    limits = replace(DEFAULT_LIMITS, max_json_depth=4, max_json_nodes=4, max_integer_digits=3)
    for data in (b'[[[[[]]]]]\n', b'[0,0,0,0]\n', b'1000\n', b'1' * 5000 + b'\n'):
        rejected(lambda: strict_json_loads(data, max_bytes=8192, limits=limits), 'json_resource_limit')


def test_depth_node_exact_edges_and_escaped_brackets():
    limits = replace(DEFAULT_LIMITS, max_json_depth=3, max_json_nodes=4)
    assert strict_json_loads(b'[[[0]]]\n', max_bytes=128, limits=limits) == [[[0]]]
    assert strict_json_loads(b'["[\\\"\\\\]",0]\n', max_bytes=128, limits=limits) == ['["\\]', 0]
    rejected(lambda: strict_json_loads(b'[[[[0]]]]\n', max_bytes=128, limits=limits), 'json_resource_limit')
    rejected(lambda: canonical_json_bytes([0, 0, 0, 0], max_bytes=128, limits=limits), 'json_resource_limit')


@pytest.mark.parametrize('cell', [[], ['n', None], ['bogus'], ['s'], ['s', 1], ['b', 1], ['i', True],
    ['i', '+1'], ['i', '01'], ['i', '-0'], ['i', ''], ['f', 'nan'], ['f', 'inf'],
    ['f', '0x1p+0'], ['f', '0x1.0000000000000p+99999'], ['d', True, '1', 0],
    ['d', 0, '', 0], ['d', 0, '00', 0], ['d', 0, '01', 0], ['d', 0, '1', True],
    ['d', 0, '1', 4097], ['d', 2, '1', 0], ['x', 'AA'], ['x', 'AB=='], ['x', 'AA==\n'],
    ['x', '===='], ['date', '2023-02-29'], ['date', '2024-1-1'],
    ['dt_naive', '2024-01-01T00:00:00.000000+00:00', 0],
    ['dt', '2024-01-01T00:00:00.000000', 0], ['dt', '2024-01-01T00:00:00.000000Z', 0],
    ['dt_naive', '2024-01-01T00:00:00.000000', True]])
def test_bad_cells_are_fixed_safe_errors(cell):
    rejected(lambda: decode_cell(cell))


class Hostile:
    def __str__(self):
        raise AssertionError('must_not_stringify')
    def __repr__(self):
        raise AssertionError('must_not_repr')


class HostileTZ(tzinfo):
    def utcoffset(self, dt):
        raise AssertionError('must_not_call_custom_tz')


class IntSubclass(int):
    pass


@pytest.mark.parametrize('value', [Hostile(), IntSubclass(1), {1: 2}, (1, 2),
    float('nan'), float('inf'), float('-inf'), Decimal('NaN'), Decimal('sNaN'),
    Decimal('Infinity'), '\ud800', '\udc00', datetime(2024, 1, 1, tzinfo=HostileTZ())])
def test_invalid_native_values_do_not_invoke_str_or_repr(value):
    rejected(lambda: encode_cell(value))


def test_integer_and_decimal_boundaries_without_python_digit_limit_changes():
    original = sys.get_int_max_str_digits()
    limit = replace(DEFAULT_LIMITS, max_integer_digits=3, max_decimal_digits=3, max_decimal_exponent=3)
    assert decode_cell(encode_cell(-999, limits=limit), limits=limit) == -999
    for value in (1000, -1000, 10**100_000):
        rejected(lambda: encode_cell(value, limits=limit))
    rejected(lambda: decode_cell(['i', '1' * 4097]))
    assert len(encode_cell(10**4095)[1]) == 4096
    for value in (Decimal('1234'), Decimal('1E+4'), Decimal('1E-4')):
        rejected(lambda: encode_cell(value, limits=limit))
    assert sys.get_int_max_str_digits() == original


def test_decimal_global_context_is_unchanged_and_irrelevant():
    value = Decimal('-123456789.2300')
    with localcontext() as context:
        context.prec = 1
        context.Emax = 1
        context.Emin = -1
        context.traps[InvalidOperation] = True
        before = context.copy()
        decoded = decode_cell(encode_cell(value))
        assert decoded.as_tuple() == value.as_tuple()
        assert context.prec == before.prec and context.Emax == before.Emax and context.Emin == before.Emin
        assert context.traps == before.traps and context.flags == before.flags


@pytest.mark.parametrize('exponent', [0, -999999])
def test_oversized_decimal_coefficient_is_rejected_before_full_tuple_allocation(exponent):
    # Input construction occurs before tracing. This threshold is a coarse
    # regression witness for the old >9MB tuple allocation, not an API memory SLA.
    value = Decimal('1' * 1_000_000 + 'e' + str(exponent))
    limits = CodecLimits(max_decimal_digits=1)
    tracemalloc.start()
    try:
        rejected(lambda: encode_cell(value, limits=limits), 'codec_value_invalid')
        unused, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 128 * 1024


@pytest.mark.parametrize('text', ['-0E-4096', '-0E+4096', '1.00', '1E-4096',
    '1E+4096', '123456789.2300', '1' * 4096 + 'e-4095'],
    ids=['negative-zero-min-exp', 'negative-zero-max-exp', 'trailing-zeros', 'min-exp',
         'max-exp', 'scale', 'coefficient-4096'])
def test_decimal_preflight_keeps_allowed_tuple_and_all_ambient_traps_flags(text):
    value = Decimal(text)
    expected = value.as_tuple()
    with localcontext() as context:
        context.prec = 1
        context.Emax = 1
        context.Emin = -1
        for signal in context.traps:
            context.traps[signal] = True
        before = context.copy()
        assert decode_cell(encode_cell(value)).as_tuple() == expected
        assert context.prec == before.prec and context.Emax == before.Emax and context.Emin == before.Emin
        assert context.traps == before.traps and context.flags == before.flags


@pytest.mark.parametrize('text,limit,expected_probes,accepted', [
    ('0E-4096', 4096, 1, True), ('-0E+4096', 4096, 1, True),
    ('1' + '0' * 4095 + 'e-4095', 4096, 4096, True),
    ('1' * 100_000 + 'e-99999', 4096, 4096, False),
    ('1' * 100_000 + 'e-99999', 1, 1, False),
], ids=['zero-min-exp', 'negative-zero-max-exp', '4096-tailzero-worst',
         'oversize-cancel-4096-probes', 'oversize-cancel-1-probe'])
def test_decimal_public_preflight_has_local_digit_bounded_probe_count(text, limit, expected_probes, accepted):
    value = Decimal(text)
    expected = value.as_tuple() if accepted else None
    probes = 0
    def profile(frame, event, argument):
        nonlocal probes
        if event == 'c_call' and getattr(argument, '__name__', None) == 'same_quantum':
            probes += 1
    previous = sys.getprofile()
    try:
        sys.setprofile(profile)
        if accepted:
            encoded = encode_cell(value, limits=CodecLimits(max_decimal_digits=limit))
        else:
            rejected(lambda: encode_cell(value, limits=CodecLimits(max_decimal_digits=limit)), 'codec_value_invalid')
    finally:
        sys.setprofile(previous)
    assert probes == expected_probes and probes <= limit
    if accepted:
        assert decode_cell(encoded).as_tuple() == expected


def test_cell_row_record_and_base64_caps_are_independent():
    limits = replace(DEFAULT_LIMITS, max_cell_bytes=4, max_row_bytes=6, max_record_bytes=40)
    assert decode_row(encode_row(['abcd', 'ef'], limits=limits), limits=limits) == ('abcd', 'ef')
    rejected(lambda: encode_cell('中中', limits=limits), 'codec_cell_limit')
    rejected(lambda: encode_cell(b'abcde', limits=limits), 'codec_cell_limit')
    rejected(lambda: decode_cell(['x', base64.b64encode(b'abcde').decode()], limits=limits), 'codec_cell_limit')
    rejected(lambda: encode_row(['abcd', 'efg'], limits=limits), 'codec_row_limit')
    rejected(lambda: decode_row(b'[["s","abcd"],["s","efg"]]\n', limits=limits), 'codec_row_limit')
    tiny = replace(DEFAULT_LIMITS, max_record_bytes=10)
    rejected(lambda: encode_row(['abcdef'], limits=tiny), 'codec_record_limit')
    rejected(lambda: decode_row(b'[["s","abcdef"]]\n', limits=tiny), 'codec_record_limit')


def test_full_default_cell_and_row_edges_and_escaped_expansion():
    cell = 'a' * DEFAULT_LIMITS.max_cell_bytes
    assert decode_cell(encode_cell(cell)) == cell
    row = [cell] * 4
    record = encode_row(row)
    assert len(record) > DEFAULT_LIMITS.max_row_bytes
    assert decode_row(record) == tuple(row)
    rejected(lambda: encode_row(row + ['x']), 'codec_row_limit')
    rejected(lambda: encode_cell(cell + 'x'), 'codec_cell_limit')
    expanded = encode_row(['\0' * (1 << 20)] * 4)
    assert len(expanded) < DEFAULT_LIMITS.max_record_bytes
    assert decode_row(expanded) == tuple(['\0' * (1 << 20)] * 4)


def test_columns_shape_and_allowed_tags_do_not_correct_business_values():
    tags = (frozenset({'i'}), frozenset({'s', 'n'}))
    assert decode_row(encode_row([-2, 'bad-date'], allowed_tags=tags), allowed_tags=tags) == (-2, 'bad-date')
    for fn in (lambda: encode_row([True, 'bad-date'], allowed_tags=tags),
               lambda: decode_row(b'[["b",true],["s","bad-date"]]\n', allowed_tags=tags)):
        rejected(fn, 'codec_tag_invalid')
    rejected(lambda: encode_row([1], allowed_tags=tags), 'codec_column_mismatch')
    rejected(lambda: encode_row([None] * 97), 'codec_column_mismatch')
    rejected(lambda: decode_row(b'{"a":1}\n'), 'codec_shape_invalid')
    rejected(lambda: encode_row(iter([1])))
    rejected(lambda: encode_row([1], allowed_tags=[frozenset({'i'})]))
    rejected(lambda: encode_row([1], allowed_tags=(frozenset({'bogus'}),)))


@pytest.mark.parametrize('field', tuple(CodecLimits.__dataclass_fields__))
def test_limits_only_tighten_exact_positive_integers(field):
    original = getattr(DEFAULT_LIMITS, field)
    for bad in (0, -1, True, original + 1, '1', Hostile()):
        rejected(lambda: replace(DEFAULT_LIMITS, **{field: bad}), 'codec_limits_invalid')
    tightened = replace(DEFAULT_LIMITS, **{field: 1})
    assert getattr(tightened, field) == 1
    with pytest.raises(FrozenInstanceError):
        tightened.max_columns = 2


def test_limits_argument_and_max_bytes_cannot_be_untrusted_or_widened():
    for bad in (None, {}, Hostile(), True):
        rejected(lambda: encode_cell('x', limits=bad), 'codec_limits_invalid')
    for bad in (None, True, 0, 32 * 1024 * 1024 + 1, Hostile()):
        rejected(lambda: strict_json_loads(b'0\n', max_bytes=bad))
    rejected(lambda: canonical_json_bytes('abcdef', max_bytes=5), 'json_resource_limit')
    rejected(lambda: strict_json_loads(b'"abcdef"\n', max_bytes=5), 'json_resource_limit')
    rejected(lambda: strict_json_loads('0\n', max_bytes=10))
    rejected(lambda: canonical_json_bytes(Hostile(), max_bytes=10))
    rejected(lambda: canonical_json_bytes({'x': float('nan')}, max_bytes=100))
    rejected(lambda: canonical_json_bytes({1: 'x'}, max_bytes=100))
    cyclic = []
    cyclic.append(cyclic)
    rejected(lambda: canonical_json_bytes(cyclic, max_bytes=100), 'json_resource_limit')


def test_errors_clear_context_even_inside_caller_except_and_never_emit_values(capsys):
    for fn in (lambda: encode_cell(Hostile()), lambda: decode_cell(['i', 'secret-canary']),
               lambda: strict_json_loads(b'"\\ud800"\n', max_bytes=100),
               lambda: require_source_profile('secret-canary')):
        try:
            raise RuntimeError('B6_E1A_SYNTHETIC_PRIVATE_password_email_signed_url')
        except RuntimeError:
            error = rejected(fn)
            assert 'secret-canary' not in str(error) and 'PRIVATE' not in repr(error)
    assert SnapshotError(Hostile()).code == 'codec_value_invalid'
    assert capsys.readouterr() == ('', '')


def test_baseexception_is_not_translated(monkeypatch):
    import tools.production_db_snapshot_format as module
    def stop(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(module.json, 'loads', stop)
    with pytest.raises(KeyboardInterrupt):
        strict_json_loads(b'null\n', max_bytes=100)


@pytest.mark.parametrize('profile', sorted({
    'legacy_sqlite9_v1', 'sqlite_models17_v1', 'pg_b1_0001_v1',
    'pg_b1b_0002_v1', 'pg_b1b_0003_v1', 'pg_b3b_0004_v1'}))
def test_profile_id_alone_never_authorizes_schema(profile):
    assert profile in KNOWN_PROFILE_IDS and len(KNOWN_PROFILE_IDS) == 6
    rejected(lambda: require_source_profile(profile), 'source_profile_unsupported')


def test_unknown_profile_and_hostile_id_are_unsupported():
    for value in ('unknown', '', None, Hostile()):
        rejected(lambda: require_source_profile(value), 'source_profile_unsupported')
    rejected(lambda: require_source_profile(), 'source_profile_unsupported')
    rejected(lambda: require_source_profile(unrecognized_private_argument=Hostile()), 'source_profile_unsupported')


def test_profile_duplicate_bindings_and_any_call_shape_fail_safely_in_outer_except():
    calls = (lambda: require_source_profile('legacy_sqlite9_v1', profile_id='unknown'),
             lambda: require_source_profile(Hostile(), Hostile(), profile_id=Hostile()),
             lambda: require_source_profile(profile_id=Hostile(), args=Hostile(), kwargs=Hostile()))
    for call in calls:
        try:
            raise RuntimeError('B6_E1A_SYNTHETIC_PRIVATE_password_email_signed_url')
        except RuntimeError:
            rejected(call, 'source_profile_unsupported')


def test_preimport_network_guard_is_installed_and_no_app_modules_loaded():
    for call in (lambda: socket.socket().connect(('127.0.0.1', 1)),
                 lambda: socket.getaddrinfo('example.invalid', 80)):
        with pytest.raises(RuntimeError, match='b6_snapshot_format_network_forbidden'):
            call()
    assert not any(name == 'app' or name.startswith('app.') for name in sys.modules)
    assert 'sqlalchemy' not in sys.modules


def test_fixedseed_fuzz_native_values_roundtrip_exactly():
    rng = random.Random(640106)
    for unused in range(400):
        float_value = struct.unpack('!d', rng.getrandbits(64).to_bytes(8, 'big'))[0]
        if math.isfinite(float_value):
            assert decode_cell(encode_cell(float_value)).hex() == float_value.hex()
        integer = rng.randrange(-(10**100), 10**100)
        assert decode_cell(encode_cell(integer)) == integer
        blob = rng.randbytes(rng.randrange(80))
        assert decode_cell(encode_cell(blob)) == blob
        value = Decimal((rng.randrange(2), tuple(rng.randrange(10) for _ in range(rng.randrange(1, 60))), rng.randrange(-100, 100)))
        assert decode_cell(encode_cell(value)).as_tuple() == value.as_tuple()
        text = ''.join(chr(rng.choice([rng.randrange(0xD800), rng.randrange(0xE000, 0x110000)])) for _ in range(20))
        assert decode_row(encode_row([text])) == (text,)


def test_fixedseed_canonical_json_matches_stdlib_and_exact_byte_edges():
    rng = random.Random(640107)
    alphabet = ['\0', '\x01', '\x1f', '\b', '\f', '\n', '\r', '\t', '"', '\\', '\x7f', '中', '鲸', '\U0001f40b', 'a']
    for unused in range(200):
        text = ''.join(rng.choices(alphabet, k=20))
        value = {'z': [text, rng.randrange(-10**20, 10**20), {'x': None, 'b': False}], 'a': [True, []]}
        expected = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii') + b'\n'
        assert canonical_json_bytes(value, max_bytes=len(expected)) == expected
        assert strict_json_loads(expected, max_bytes=len(expected)) == value
        rejected(lambda: canonical_json_bytes(value, max_bytes=len(expected) - 1), 'json_resource_limit')


def test_fixed_audit_wire_is_exact():
    value = (None, True, -42, -0.0, 'row\0', b'\0\xff')
    expected = b'[["n"],["b",true],["i","-42"],["f","-0x0.0p+0"],["s","row\\u0000"],["x","AP8="]]\n'
    assert encode_row(value) == expected
    assert decode_row(expected) == value
