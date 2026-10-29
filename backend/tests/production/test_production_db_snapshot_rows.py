"""E2 T2: synthetic SQLite preflight and original-value rows; no app/real DB/network."""
import math
from pathlib import Path
import sqlite3
import time

import pytest

import tools.production_db_snapshot_catalog as catalog
import tools.production_db_snapshot_read_contract as rc
import tools.production_db_snapshot_rows as rows
from tools.production_db_snapshot_catalog import catalog_snapshot

FIXTURES = Path(__file__).parent / 'fixtures' / 'snapshot_catalog'

USERS = [
    ('u1', 'a@example.com', 'h1', '2026-10-25 01:02:03'),
    ('u2', 'bé\U0001f600@example.com', '', 'not-a-date'),
    ('u3', 'c@example.com', 'x\x00y', '2026-10-25T01:02:03.123456+08:00'),
]


def make_db(tmp_path, version=17, script='', wal=False, encoding=None):
    path = tmp_path / f'rows{version}.db'
    writer = sqlite3.connect(str(path))
    try:
        if encoding:
            writer.execute(f"PRAGMA encoding='{encoding}'")
        if wal:
            writer.execute('PRAGMA journal_mode=WAL')
        writer.executescript((FIXTURES / f'sqlite{version}.sql').read_text('utf8'))
        writer.executemany('INSERT INTO user VALUES (?,?,?,?)', USERS)
        if script:
            writer.executescript(script)
        writer.commit()
    finally:
        writer.close()
    return str(path.resolve())


def oracle(path, table, pk):
    """Independent plain sqlite3 read of the same file (no project code)."""
    connection = sqlite3.connect(path)
    try:
        order = ','.join('"' + name + '"' for name in pk)
        return connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}').fetchall()
    finally:
        connection.close()


def same(left, right):
    assert len(left) == len(right)
    for a, b in zip(left, right):
        assert type(a) is type(b)
        if type(a) is float:
            assert math.copysign(1, a) == math.copysign(1, b) and (a == b or (a != a and b != b))
        else:
            assert a == b


class Session:
    def __init__(self, path, limits=None, seconds=300):
        self.path, self.limits, self.seconds = path, limits or rows.RowLimits(), seconds

    def __enter__(self):
        self.bootstrap = rc._open_synthetic_sqlite(self.path)
        self.connection, self.contract = self.bootstrap.__enter__()
        self.catalog = catalog._catalog_for_export(self.connection, self.contract, rc.ReadBudget(self.seconds))
        self.source = self.catalog.__enter__()
        self.rows = rows._open_rows(self.source, self.contract, self.limits)
        self.reader = self.rows.__enter__()
        return self

    def __exit__(self, *exc):
        try:
            self.rows.__exit__(*exc)
        finally:
            try:
                self.catalog.__exit__(*exc)
            finally:
                self.bootstrap.__exit__(*exc)
        return False


def expect(code, function, *args):
    with pytest.raises(rows.SnapshotRowsError) as caught:
        function(*args)
    assert caught.value.code == code
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    return caught.value


def test_preflight_then_all_tables_match_independent_oracle(tmp_path):
    script = ("INSERT INTO quota VALUES ('q1','u1','2026-10-25',0,9223372036854775807),"
              "('q2','u2','2026-10-26',1,5);")
    path = make_db(tmp_path, script=script)
    with Session(path) as session:
        summary = session.reader.preflight()
        names = [table.name for table in rows.table_order(session.source.descriptor)]
        assert names == sorted(names) and len(names) == 17
        assert summary.counts[names.index('user')] == 3
        assert summary.counts[names.index('quota')] == 2
        assert sum(summary.counts) == 5
        for index, table in enumerate(rows.table_order(session.source.descriptor)):
            got = list(session.reader.iter_table(index))
            same_rows = oracle(path, table.name, table.primary_key)
            assert len(got) == len(same_rows) == summary.counts[index]
            for left, right in zip(got, same_rows):
                assert type(left) is tuple
                same(left, right)
        assert 'u1' not in repr(summary) and 'u1' not in repr(session.reader)


def test_original_values_preserved(tmp_path):
    path = make_db(tmp_path, script=(
        "INSERT INTO quota VALUES ('q3','u3','2026-13-45',-1,3),('q4','u1',X'00FF',2.5,4),"
        "('q5','u2','d',0,-9223372036854775808);"))
    with Session(path) as session:
        session.reader.preflight()
        order = rows.table_order(session.source.descriptor)
        quota = [index for index, table in enumerate(order) if table.name == 'quota'][0]
        got = list(session.reader.iter_table(quota))
    assert [row[0] for row in got] == ['q3', 'q4', 'q5']
    assert got[0][2] == '2026-13-45' and got[0][3] == -1
    assert got[1][2] == b'\x00\xff' and got[1][3] == 2.5 and type(got[1][3]) is float
    assert got[2][4] == -9223372036854775808


def test_empty_database_counts_zero(tmp_path):
    path = tmp_path / 'empty.db'
    writer = sqlite3.connect(str(path))
    writer.executescript((FIXTURES / 'sqlite9.sql').read_text('utf8'))
    writer.commit()
    writer.close()
    with Session(str(path.resolve())) as session:
        summary = session.reader.preflight()
        assert summary.counts == (0,) * 9
        for index in range(9):
            assert list(session.reader.iter_table(index)) == []


@pytest.fixture
def no_payload(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('payload_before_preflight_passed')
    monkeypatch.setattr(rows, '_payload_sql', forbidden)


def test_large_cell_rejected_before_payload(tmp_path, no_payload):
    path = make_db(tmp_path)
    with Session(path, rows.RowLimits(max_cell_bytes=12)) as session:
        expect('snapshot_resource_limit', session.reader.preflight)
        expect('snapshot_inactive', session.reader.iter_table, 0)


def test_text_with_nul_measured_in_bytes(tmp_path, no_payload):
    # 'x\x00y' is 3 bytes; a NUL-truncating length(TEXT) would see 1.
    path = make_db(tmp_path, script="DELETE FROM user WHERE id IN ('u1','u2');")
    connection = sqlite3.connect(path)
    connection.execute("UPDATE user SET id='a', email='b', created_at='c' WHERE id='u3'")
    connection.commit()
    connection.close()
    with Session(path, rows.RowLimits(max_cell_bytes=2)) as session:
        expect('snapshot_resource_limit', session.reader.preflight)
    with Session(path, rows.RowLimits(max_cell_bytes=3)) as session:
        session.reader.preflight()


def test_multi_column_row_limit(tmp_path, no_payload):
    path = make_db(tmp_path)
    # Every cell <= 32 bytes, but u3's four-column raw row is 2+13+3+32 = 50.
    with Session(path, rows.RowLimits(max_cell_bytes=40, max_row_bytes=49)) as session:
        expect('snapshot_resource_limit', session.reader.preflight)


def test_total_rows_limit(tmp_path, no_payload):
    path = make_db(tmp_path)
    with Session(path, rows.RowLimits(max_total_rows=2)) as session:
        expect('snapshot_resource_limit', session.reader.preflight)
    with Session(path, rows.RowLimits(max_total_rows=3)) as session:
        assert sum(session.reader.preflight().counts) == 3


def test_iterator_rules(tmp_path):
    path = make_db(tmp_path)
    with Session(path) as session:
        expect('snapshot_inactive', session.reader.iter_table, 0)
        session.reader.preflight()
        expect('snapshot_inactive', session.reader.preflight)
        for value in (True, -1, 17, '0', 1.0, None):
            expect('snapshot_arguments_invalid', session.reader.iter_table, value)
        iterator = session.reader.iter_table(0)
        expect('snapshot_inactive', session.reader.iter_table, 1)  # one open iterator at a time
        list(iterator)
        expect('snapshot_inactive', session.reader.iter_table, 0)  # each table once


def test_rows_inactive_after_exit(tmp_path):
    path = make_db(tmp_path)
    with Session(path) as session:
        session.reader.preflight()
        reader = session.reader
    expect('snapshot_inactive', reader.iter_table, 0)


def test_requires_export_contract(tmp_path):
    path = make_db(tmp_path)
    with rc._open_synthetic_sqlite(path) as (connection, contract):
        with catalog_snapshot(connection) as source:
            with pytest.raises(rows.SnapshotRowsError) as caught:
                with rows._open_rows(source, contract, rows.RowLimits()):
                    pytest.fail('unexpected rows')
            assert caught.value.code == 'driver_contract_required'
    for value in (None, True, object()):
        with rc._open_synthetic_sqlite(path) as (connection, contract):
            with catalog._catalog_for_export(connection, contract, rc.ReadBudget(300)) as source:
                with pytest.raises(rows.SnapshotRowsError) as caught:
                    with rows._open_rows(source, value, rows.RowLimits()):
                        pytest.fail('unexpected rows')
                assert caught.value.code == 'driver_contract_required'


def test_snapshot_isolated_from_concurrent_writes(tmp_path):
    path = make_db(tmp_path, wal=True)
    writer = sqlite3.connect(path)
    try:
        with Session(path) as session:
            summary = session.reader.preflight()
            order = rows.table_order(session.source.descriptor)
            user = [index for index, table in enumerate(order) if table.name == 'user'][0]
            writer.execute("INSERT INTO user VALUES ('u9','z@example.com','h','t')")
            writer.execute("DELETE FROM user WHERE id='u1'")
            writer.commit()
            got = list(session.reader.iter_table(user))
            assert [row[0] for row in got] == ['u1', 'u2', 'u3']
            assert summary.counts[user] == 3
        assert [row[0] for row in oracle(path, 'user', ('id',))] == ['u2', 'u3', 'u9']
    finally:
        writer.close()


def test_row_count_mismatch_detected(tmp_path, monkeypatch):
    path = make_db(tmp_path)
    original = rows._fetchone
    seen = []

    def drop_second(cursor):
        row = original(cursor)
        seen.append(row)
        return None if len(seen) == 2 else row
    with Session(path) as session:
        session.reader.preflight()
        order = rows.table_order(session.source.descriptor)
        user = [index for index, table in enumerate(order) if table.name == 'user'][0]
        monkeypatch.setattr(rows, '_fetchone', drop_second)
        with pytest.raises(rows.SnapshotRowsError) as caught:
            list(session.reader.iter_table(user))
        assert caught.value.code == 'source_row_count_mismatch'


@pytest.mark.parametrize('bad', [('x', 'unknown'), ('x', 'integer'), (True, 'integer'), (b'x', 'text')],
    ids=['unknown-typeof', 'str-as-integer', 'bool', 'bytes-as-text'])
def test_driver_type_drift_rejected(tmp_path, monkeypatch, bad):
    path = make_db(tmp_path)
    original = rows._fetchone

    def drift(cursor):
        row = original(cursor)
        if row is None:
            return row
        return (bad[0], bad[1]) + row[2:]
    with Session(path) as session:
        session.reader.preflight()
        order = rows.table_order(session.source.descriptor)
        user = [index for index, table in enumerate(order) if table.name == 'user'][0]
        monkeypatch.setattr(rows, '_fetchone', drift)
        with pytest.raises(rows.SnapshotRowsError) as caught:
            list(session.reader.iter_table(user))
        assert caught.value.code == 'source_read_failed'


def test_deadline_during_iteration(tmp_path, monkeypatch):
    path = make_db(tmp_path)
    clock = [time.monotonic()]
    monkeypatch.setattr(rc, '_monotonic', lambda: clock[0])
    with Session(path, seconds=5) as session:
        session.reader.preflight()
        order = rows.table_order(session.source.descriptor)
        user = [index for index, table in enumerate(order) if table.name == 'user'][0]
        iterator = session.reader.iter_table(user)
        next(iterator)
        clock[0] += 60
        with pytest.raises(rows.SnapshotRowsError) as caught:
            next(iterator)
        assert caught.value.code == 'snapshot_resource_limit'


def test_non_utf8_database_unsupported(tmp_path):
    path = make_db(tmp_path, encoding='UTF-16le')
    with Session(path) as session:
        expect('source_codec_unsupported', session.reader.preflight)


def test_cursors_closed_on_exit(tmp_path):
    path = make_db(tmp_path)
    with Session(path) as session:
        session.reader.preflight()
        iterator = session.reader.iter_table(0)
        opened = session.reader._cursors_for_test()
        assert opened
    for cursor in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            cursor.execute('SELECT 1')


@pytest.mark.parametrize('value', [0, -1, True, 1.5], ids=['zero', 'neg', 'bool', 'float'])
def test_limits_validation(value):
    with pytest.raises(ValueError):
        rows.RowLimits(max_cell_bytes=value)
    with pytest.raises(ValueError):
        rows.RowLimits(max_cell_bytes=(1 << 20) + 1)
