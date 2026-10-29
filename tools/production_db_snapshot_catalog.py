"""Bounded SQLite/PG catalog in one E0 snapshot, synthetic driver gate only.

DDL is parsed as data and never executed. Matching a schema does not certify
driver callbacks/converters, ACL, timeout, source suitability or export.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import threading

from sqlalchemy.engine import Connection
from tools.production_db_snapshot import readonly_snapshot, SnapshotConnectionError
from tools import production_db_snapshot_read_contract as _read_contract
from tools.production_db_snapshot_format import SnapshotError
from tools.production_db_snapshot_profiles import require_source_profile
from tools._production_db_snapshot_catalog_pg import _collect_pg, _assert_pg_active, _PgCatalogError
from tools.production_db_snapshot_schema import (PhysicalType, ColumnDescriptor,
    UniqueDescriptor, ForeignKeyDescriptor, IndexDescriptor, TableDescriptor, SchemaDescriptor)

_CODES = frozenset({'source_profile_unsupported', 'catalog_failed', 'catalog_limit_exceeded',
    'connection_required', 'active_transaction_refused', 'unsupported_dialect',
    'sql_logging_refused', 'sqlite_readonly_uri_required', 'postgres_driver_unsupported',
    'connection_restore_failed', 'snapshot_failed', 'snapshot_inactive', 'snapshot_owner_mismatch',
    'driver_contract_required', 'snapshot_resource_limit'})
_MAX_RECORDS = 2048
_MAX_DDL = 65536
_MAX_TOTAL = 2 << 20
_MAX_TOKENS = 32768
_MAX_DEPTH = 32
_NAME = re.compile(r'[a-z_][a-z0-9_]{0,127}\Z')
_ACTIVE = {}
_KEY = object()


class CatalogError(RuntimeError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in _CODES else 'catalog_failed'
        super().__init__(self.code)


def _fail(code='source_profile_unsupported'):
    error = CatalogError(code)
    try:
        raise error
    except CatalogError:
        error.__cause__ = error.__context__ = None
        raise


def _need(condition, code='source_profile_unsupported'):
    if not condition:
        _fail(code)


def _lex(sql):
    _need(type(sql) is str)
    _need(len(sql) <= _MAX_DDL and len(sql.encode('utf8')) <= _MAX_DDL, 'catalog_limit_exceeded')
    tokens = []
    offset = depth = 0
    while offset < len(sql):
        char = sql[offset]
        if char in ' \t\r\n':
            offset += 1
            continue
        match = re.match(r'[A-Za-z_][A-Za-z_0-9]*', sql[offset:])
        if match:
            word = match[0].lower()
            _need(len(word) <= 128, 'catalog_limit_exceeded')
            tokens.append(('w', word)); offset += len(match[0])
        elif char in "'\"":
            quote = char; value = ''; offset += 1
            while offset < len(sql):
                if sql[offset] == quote:
                    if offset+1 < len(sql) and sql[offset+1] == quote:
                        value += quote; offset += 2; continue
                    offset += 1; break
                value += sql[offset]; offset += 1
            else:
                _fail()
            if quote == '"':
                _need(_NAME.fullmatch(value) is not None)
                tokens.append(('q', value))
            else:
                _need(len(value) <= 65536, 'catalog_limit_exceeded')
                tokens.append(('s', value))
        elif char.isascii() and char.isdigit():
            match = re.match(r'[0-9]+', sql[offset:])[0]
            _need(len(match) <= 10, 'catalog_limit_exceeded')
            tokens.append(('n', int(match))); offset += len(match)
        elif sql[offset:offset+2] in ('>=', '<=', '<>'):
            tokens.append(('p', sql[offset:offset+2])); offset += 2
        elif char in '(),;=><':
            if char == '(':
                depth += 1; _need(depth <= _MAX_DEPTH, 'catalog_limit_exceeded')
            if char == ')':
                depth -= 1; _need(depth >= 0)
            tokens.append(('p', char)); offset += 1
        else:
            _fail()
        _need(len(tokens) <= _MAX_TOKENS, 'catalog_limit_exceeded')
    _need(depth == 0)
    return tokens


class _Parser:
    def __init__(self, sql):
        self.tokens = _lex(sql); self.pos = 0

    def peek(self, value):
        return self.pos < len(self.tokens) and self.tokens[self.pos] == ('p' if value in '(),;=><' or value in ('>=','<=','<>') else 'w', value)

    def take(self, value):
        if self.peek(value):
            self.pos += 1; return True
        return False

    def expect(self, value):
        _need(self.take(value))

    def name(self):
        _need(self.pos < len(self.tokens))
        kind, value = self.tokens[self.pos]; self.pos += 1
        _need(kind in ('w','q') and _NAME.fullmatch(value) is not None)
        return value

    def end(self):
        self.take(';'); _need(self.pos == len(self.tokens))

    def names(self):
        self.expect('('); names = [self.name()]
        self.take('asc')
        while self.take(','):
            names.append(self.name()); self.take('asc')
            _need(len(names) <= 96, 'catalog_limit_exceeded')
        self.expect(')'); return tuple(names)

    def physical(self):
        word = self.name()
        _need(word in ('integer','bigint','float','boolean','date','datetime','text','varchar'))
        args = ()
        if self.take('('):
            _need(word == 'varchar' and self.pos < len(self.tokens))
            kind, size = self.tokens[self.pos]; self.pos += 1
            _need(kind == 'n' and 1 <= size <= 1048576)
            args = (size,); self.expect(')')
        return PhysicalType('sqlite_'+word, args)

    def expression(self):
        node = self.binary_or()
        pending = [(node, 1)]
        while pending:
            item, depth = pending.pop()
            _need(depth <= _MAX_DEPTH, 'catalog_limit_exceeded')
            if type(item) is tuple:
                pending.extend((part, depth+1) for part in item if type(part) is tuple)
        return node

    def binary_or(self):
        node = self.binary_and()
        while self.take('or'):node = ('or', node, self.binary_and())
        return node

    def binary_and(self):
        node = self.comparison()
        while self.take('and'):node = ('and', node, self.comparison())
        return node

    def atom(self):
        if self.take('('):
            node = self.expression(); self.expect(')'); return node
        _need(self.pos < len(self.tokens))
        kind, value = self.tokens[self.pos]; self.pos += 1
        if kind in ('s','n'):return (kind, value)
        if kind == 'q':return ('column',value)
        _need(kind == 'w')
        if value in ('true','false'):return ('bool', value)
        if self.take('('):
            _need(value == 'length'); column = self.name(); self.expect(')')
            return ('length', ('column', column))
        return ('column', value)

    def comparison(self):
        node = self.atom()
        if self.take('is'):
            negate = self.take('not'); self.expect('null')
            return ('is_not_null' if negate else 'is_null', node)
        if self.take('in'):
            self.expect('('); values = []
            while True:
                _need(self.pos < len(self.tokens) and self.tokens[self.pos][0] == 's')
                values.append(self.tokens[self.pos]); self.pos += 1
                if not self.take(','):break
            self.expect(')'); return ('in', node, tuple(values))
        if self.take('between'):
            low = self.atom(); self.expect('and'); high = self.atom()
            return ('between', node, low, high)
        for operator in ('=', '<>', '>', '>=', '<='):
            if self.take(operator):return (operator, node, self.atom())
        return node

    def fk(self, columns):
        self.expect('references'); target = self.name(); target_columns = self.names()
        update = delete = 'NO_ACTION'; seen = set()
        while self.take('on'):
            action_type = self.name(); _need(action_type in ('update','delete') and action_type not in seen)
            seen.add(action_type)
            if self.take('no'):
                self.expect('action'); action = 'NO_ACTION'
            elif self.take('restrict'):action = 'RESTRICT'
            elif self.take('cascade'):action = 'CASCADE'
            elif self.take('set'):
                if self.take('null'):action = 'SET_NULL'
                else:self.expect('default'); action = 'SET_DEFAULT'
            else:_fail()
            if action_type == 'update':update = action
            else:delete = action
        return ForeignKeyDescriptor(columns, 'main', target, target_columns, update, delete, 'SIMPLE', False, False, True)

    def table(self):
        self.expect('create'); self.expect('table'); name = self.name(); self.expect('(')
        columns = []; pk = (); uniques = []; fks = []; checks = []; constraint_names = set()
        while True:
            named = False
            if self.take('constraint'):
                cname = self.name(); _need(cname not in constraint_names); constraint_names.add(cname)
                named = True
            if self.take('primary'):
                self.expect('key'); _need(not pk); pk = self.names()
            elif self.take('unique'):uniques.append(self.names())
            elif self.take('foreign'):
                self.expect('key'); fks.append(self.fk(self.names()))
            elif self.take('check'):
                self.expect('('); checks.append(self.expression()); self.expect(')')
            else:
                _need(not named)
                column = self.name(); physical = self.physical(); nullable = True; seen = set()
                while not self.peek(',') and not self.peek(')'):
                    if self.take('constraint'):
                        cname=self.name(); _need(cname not in constraint_names); constraint_names.add(cname)
                        continue
                    if self.take('not'):
                        self.expect('null'); _need('null' not in seen); seen.add('null'); nullable = False
                    elif self.take('null'):
                        _need('null' not in seen); seen.add('null')
                    elif self.take('primary'):
                        self.expect('key'); _need(not pk); pk = (column,)
                    elif self.take('unique'):uniques.append((column,))
                    elif self.peek('references'):fks.append(self.fk((column,)))
                    elif self.take('check'):
                        self.expect('('); checks.append(self.expression()); self.expect(')')
                    else:_fail()
                columns.append(ColumnDescriptor(column, physical, nullable, 'absent', 'absent', 'absent', 'dialect_default'))
            _need(len(columns) <= 96 and all(len(items) <= 96 for items in (uniques,fks,checks)), 'catalog_limit_exceeded')
            if not self.take(','):break
        self.expect(')'); self.end()
        return name, tuple(columns), pk, tuple(uniques), tuple(fks), tuple(checks)

    def index(self):
        self.expect('create'); unique = self.take('unique'); self.expect('index')
        name = self.name(); self.expect('on'); table = self.name(); columns = self.names()
        predicate = None
        if self.take('where'):predicate = self.expression()
        self.end(); return name, table, columns, unique, predicate


# Frozen source-expression definitions from the reviewed S17 DDL attachment.
# Not read from fixtures, profiles or a database at runtime.
_CHECK_TEXT = (
    ('billingcheckout', 'billingcheckout.reconciliation.v1', "reconciliation IS NULL OR reconciliation IN ('not_started','unknown','verified','needs_review','closed')"),
    ('billingcheckout', 'billingcheckout.reconcile_attempts.v1', 'reconcile_attempts >= 0 AND reconcile_attempts <= 3'),
    ('billingevent', 'billingevent.scope_mode.v1', "(provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL)"),
    ('billingfact', 'billingfact.amount_total.v1', 'amount_total IS NULL OR amount_total >= 0'),
    ('billingfact', 'billingfact.amount_refunded.v1', 'amount_refunded IS NULL OR amount_refunded >= 0'),
    ('billingfact', 'billingfact.reconciliation.v1', "reconciliation IN ('unknown','verified','needs_review')"),
    ('billingfact', 'billingfact.scope_mode.v1', "(provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL)"),
    ('billinginbox', 'billinginbox.status.v1', "status IN ('received','processing','retry_wait','waiting_binding','applied','ignored','needs_review')"),
    ('billinginbox', 'billinginbox.budget.v1', 'attempt_count >= 0 AND attempt_limit > 0 AND attempt_count <= attempt_limit AND lease_epoch >= 0'),
    ('billinginbox', 'billinginbox.canonical_version.v1', 'canonical_version > 0'),
    ('billinginbox', 'billinginbox.lease_pair.v1', '(lease_owner IS NULL) = (lease_deadline IS NULL)'),
    ('billinginbox', 'billinginbox.processing_lease.v1', "status <> 'processing' OR lease_owner IS NOT NULL"),
    ('billinginbox', 'billinginbox.budget_deadline.v1', 'budget_deadline >= received_at'),
    ('billingreconciliationaudit', 'billingreconciliationaudit.sequence_version.v1', 'seq>0 AND projection_version=1'),
    ('billingreconciliationaudit', 'billingreconciliationaudit.event_ordinal.v1', "(event_kind IN ('task_started','task_finished') AND get_ordinal IS NULL) OR (event_kind IN ('get_reserved','get_observed') AND get_ordinal IS NOT NULL AND get_ordinal BETWEEN 1 AND 3)"),
    ('billingreconciliationaudit', 'billingreconciliationaudit.reason.v1', "reason_code IN ('unknown_create','missing_reference','legacy_verification')"),
    ('billingreconciliationtask', 'billingreconciliationtask.scope.v1', "provider_account_scope <> 'legacy_unknown' AND length(provider_account_scope)>0"),
    ('billingreconciliationtask', 'billingreconciliationtask.reason.v1', "reason_code IN ('unknown_create','missing_reference','legacy_verification')"),
    ('billingreconciliationtask', 'billingreconciliationtask.versions_limits.v1', 'input_version=1 AND budget_version=1 AND get_limit=3'),
    ('billingreconciliationtask', 'billingreconciliationtask.revisions.v1', 'initial_checkout_revision>=0 AND expected_checkout_revision>=initial_checkout_revision AND membership_revision>=0 AND revision>=0 AND next_audit_seq>=1'),
    ('billingreconciliationtask', 'billingreconciliationtask.get_budget.v1', 'get_attempts>=0 AND get_attempts<=get_limit'),
    ('billingreconciliationtask', 'billingreconciliationtask.deadline.v1', 'budget_deadline>=started_at'),
    ('billingreconciliationtask', 'billingreconciliationtask.terminal.v1', "(status='running' AND completed_at IS NULL) OR (status IN ('verified','needs_review') AND completed_at IS NOT NULL)"),
    ('downloadoperation', 'downloadoperation.state.v1', "state IN ('resolving','accepted_server','direct_ready','succeeded','failed','needs_review')"),
    ('downloadoperation', 'downloadoperation.access_snapshot.v1', 'membership_revision >= 0 AND (max_height IS NULL OR max_height > 0)'),
    ('downloadoperation', 'downloadoperation.resolve_budget.v1', 'resolve_epoch >= 0 AND resolve_attempts_used >= 0 AND resolve_attempts_used <= resolve_attempts_limit AND resolve_attempts_limit > 0'),
    ('downloadoperation', 'downloadoperation.budget_checkpoint.v1', 'budget_version > 0 AND length(budget_checkpoint_json) > 0'),
    ('downloadoperation', 'downloadoperation.resolve_lease_pair.v1', '(resolve_owner IS NULL) = (resolve_lease_deadline IS NULL)'),
    ('downloadoperation', 'downloadoperation.deadline.v1', 'deadline_at >= accepted_at'),
    ('downloadoperation', 'downloadoperation.resolve_deadline.v1', 'resolve_deadline_at >= accepted_at AND resolve_deadline_at <= deadline_at'),
    ('downloadoperation', 'downloadoperation.checkpoint_time.v1', 'budget_checkpoint_at >= accepted_at'),
    ('job', 'job.status.v1', "status IN ('queued','downloading','merging','done','error')"),
    ('quotacharge', 'quotacharge.delta_one.v1', 'delta = 1'),
    ('resourcecounter', 'resourcecounter.used_nonnegative.v1', 'used >= 0'),
    ('resourcereservation', 'resourcereservation.units_positive.v1', 'units > 0'),
    ('resourcereservation', 'resourcereservation.release_state.v1', '(released = false AND released_at IS NULL) OR (released = true AND released_at IS NOT NULL)'),
)


def _expression(text):
    parser = _Parser(text); node = parser.expression(); parser.end(); return node


def _fetch(result, limit):
    failure = None
    try:
        rows = []
        while True:
            row = result.fetchone()
            if row is None:break
            _need(len(rows) < limit, 'catalog_limit_exceeded')
            rows.append(tuple(row))
    except BaseException as error:
        failure = error
    finally:
        try:
            result.close()
        except Exception:
            if failure is None:raise
    if failure is not None:raise failure
    return rows


def _read(connection, sql, parameters=(), limit=2048):
    return _fetch(connection.exec_driver_sql(sql, parameters), limit)


def _pragma(connection, name, identifier):
    # Function name is internal; catalog identifiers are bound values.
    return _read(connection, 'SELECT * FROM pragma_'+name+'(?, ?)', (identifier, 'main'), 193)


def _index_columns(connection, index_name, table_columns):
    rows = _pragma(connection, 'index_xinfo', index_name)
    _need(1 < len(rows) <= 97)
    keys = []
    for seq, row in enumerate(rows):
        _need(len(row) == 6)
        number, cid, name, desc, collation, key = row
        _need(type(number) is int and number == seq and type(cid) is int and type(desc) is int and desc == 0 and collation == 'BINARY' and type(key) is int)
        if key == 1:
            _need(not any(r[5] == 0 for r in rows[:seq]))
            _need(0 <= cid < len(table_columns) and name == table_columns[cid].name)
            keys.append(name)
        else:
            _need(key == 0 and seq == len(rows)-1 and cid == -1 and name is None)
    _need(rows[-1][5] == 0 and keys)
    return tuple(keys)


def _collect(connection):
    # First main read fixes the SQLite schema snapshot inside E0's physical BEGIN.
    counts = _read(connection, 'SELECT count(*), coalesce(max(length(CAST(sql AS BLOB))),0), coalesce(sum(length(CAST(sql AS BLOB))),0), coalesce(max(length(CAST(name AS BLOB))),0), coalesce(max(length(CAST(tbl_name AS BLOB))),0), coalesce(max(length(CAST(type AS BLOB))),0), coalesce(sum(typeof(type) <> \'text\' OR typeof(name) <> \'text\' OR typeof(tbl_name) <> \'text\' OR typeof(sql) NOT IN (\'text\',\'null\')),0) FROM main.sqlite_master', limit=1)
    _need(len(counts) == 1 and all(type(v) is int for v in counts[0]))
    _need(len(counts[0]) == 7)
    count, maximum, total, max_name, max_table, max_type, invalid = counts[0]
    _need(count <= _MAX_RECORDS and maximum <= _MAX_DDL and total <= _MAX_TOTAL and max_name <= 128 and max_table <= 128 and max_type <= 16, 'catalog_limit_exceeded')
    _need(invalid == 0)
    databases = _read(connection, 'PRAGMA database_list', limit=3)
    _need(all(len(row)==3 and row[1] in ('main','temp') for row in databases) and sum(row[1]=='main' for row in databases)==1)
    _need(_read(connection, 'SELECT count(*) FROM temp.sqlite_master', limit=1) == [(0,)])
    records = _read(connection, 'SELECT type, name, tbl_name, sql FROM main.sqlite_master ORDER BY type, name', limit=_MAX_RECORDS)
    _need(len(records) == count)
    tables = {}; indexes = {}; seen = set()
    for kind, name, table, sql in records:
        _need(type(kind) is str and type(name) is str and type(table) is str)
        _need(_NAME.fullmatch(name) is not None and _NAME.fullmatch(table) is not None)
        _need(name not in seen); seen.add(name)
        _need(kind in ('table','index'))
        if kind == 'table':
            _need(not name.startswith('sqlite_') and name == table and type(sql) is str)
            _need(len(tables) < 18, 'catalog_limit_exceeded')
            parsed = _Parser(sql).table(); _need(parsed[0] == name); tables[name] = parsed
        else:
            _need(sql is None or type(sql) is str)
            indexes[name] = (table, sql)
    descriptors = []; consumed_indexes = set()
    templates = {(table, _expression(text)): check_id for table, check_id, text in _CHECK_TEXT}
    for name, columns, pk, uniques, fks, checks in tables.values():
        xinfo = _pragma(connection, 'table_xinfo', name)
        _need(len(xinfo) == len(columns))
        for seq, (row, column) in enumerate(zip(xinfo, columns)):
            _need(len(row) == 7)
            cid, colname, declared, notnull, default, position, hidden = row
            _need(type(cid) is int and cid == seq and colname == column.name and type(declared) is str)
            parser = _Parser(declared); physical = parser.physical(); parser.end()
            _need(physical == column.physical_type and type(notnull) is int and notnull == int(not column.nullable) and default is None and type(hidden) is int and hidden == 0)
            _need(type(position) is int and position == (pk.index(colname)+1 if colname in pk else 0))
        fkrows = _pragma(connection, 'foreign_key_list', name); groups = {}
        for row in fkrows:
            _need(len(row) == 8 and type(row[0]) is int and type(row[1]) is int)
            groups.setdefault(row[0], []).append(row)
        reflected_fks = []
        _need(set(groups) == set(range(len(groups))))
        for group in groups.values():
            group.sort(key=lambda r:r[1]); first=group[0]
            _need([r[1] for r in group] == list(range(len(group))))
            _need(all((r[2],r[5],r[6],r[7]) == (first[2],first[5],first[6],first[7]) for r in group) and first[7] == 'NONE')
            reflected_fks.append(ForeignKeyDescriptor(tuple(r[3] for r in group),'main',first[2],tuple(r[4] for r in group),first[5].replace(' ','_'),first[6].replace(' ','_'),'SIMPLE',False,False,True))
        _need(len(fks) == len(reflected_fks) and set(fks) == set(reflected_fks))
        # Match backing indexes to exact parsed constraint instances and origin.
        backing = [('u', cols) for cols in uniques]
        if pk and not (len(pk)==1 and next(c for c in columns if c.name==pk[0]).physical_type == PhysicalType('sqlite_integer',())):
            backing.append(('pk',pk))
        explicit=[]
        for position, row in enumerate(_pragma(connection, 'index_list', name)):
            _need(len(row) == 5)
            seq, iname, unique, origin, partial = row
            _need(type(seq) is int and seq == position and type(iname) is str and type(unique) is int and unique in (0,1) and type(partial) is int and partial in (0,1) and origin in ('pk','u','c'))
            _need(iname in indexes and iname not in consumed_indexes and indexes[iname][0] == name)
            consumed_indexes.add(iname)
            indexcols = _index_columns(connection,iname,columns); sql = indexes[iname][1]
            if origin in ('pk','u'):
                _need(unique == 1 and partial == 0 and sql is None and (origin,indexcols) in backing)
                backing.remove((origin,indexcols))
            else:
                _need(type(sql) is str)
                parsed_name, parsed_table, parsed_cols, parsed_unique, predicate = _Parser(sql).index()
                _need(parsed_name==iname and parsed_table==name and parsed_cols==indexcols and parsed_unique==bool(unique) and bool(partial)==(predicate is not None))
                predicate_id = 'absent'
                if predicate is not None:
                    _need(name=='billingreconciliationaudit' and indexcols==('task_id','event_kind') and unique==1 and predicate==('is_null',('column','get_ordinal')))
                    predicate_id = 'get_ordinal_is_null_v1'
                explicit.append(IndexDescriptor(indexcols,bool(unique),'btree',('asc',)*len(indexcols),('dialect_default',)*len(indexcols),predicate_id,(),True))
        _need(not backing)
        check_ids=[]
        for check in checks:
            _need((name,check) in templates); check_ids.append(templates[name,check])
        descriptors.append(TableDescriptor(name,columns,pk,tuple(UniqueDescriptor(cols,True,False,False,True) for cols in uniques),fks,tuple(explicit),tuple(check_ids),(),'sqlite_ordinary_rowid_v1','nondeferrable_validated_v1'))
    _need(consumed_indexes == set(indexes))
    descriptor = SchemaDescriptor(1,'sqlite','main',(),tuple(descriptors),(),(),())
    return descriptor, require_source_profile(descriptor)


@dataclass(frozen=True, slots=True, init=False, repr=False, eq=False)
class CatalogSnapshot:
    descriptor: SchemaDescriptor
    profile: object

    def __init__(self, descriptor, profile, *, _key=None):
        _need(_key is _KEY)
        object.__setattr__(self,'descriptor',descriptor); object.__setattr__(self,'profile',profile)

    def assert_active(self):
        code=None
        try:
            _resolve(self)
            return
        except CatalogError as error:code=error.code
        except SnapshotConnectionError as error:code=error.code
        except Exception:code='snapshot_inactive'
        _fail(code)


def _resolve(source):
    _need(type(source) is CatalogSnapshot, 'snapshot_inactive')
    entry = _ACTIVE.get(id(source))
    _need(entry is not None and entry[0] is source, 'snapshot_inactive')
    _, token, connection, transaction, raw, pid, thread = entry
    _need(pid==os.getpid() and thread==threading.get_ident(), 'snapshot_owner_mismatch')
    token.assert_active()
    _need(token.connection is connection and not connection.closed and connection.get_transaction() is transaction and transaction.is_active and connection.connection.driver_connection is raw, 'snapshot_inactive')
    if token.dialect == 'postgresql':
        _assert_pg_active(connection, raw)
    else:
        _need(raw.in_transaction, 'snapshot_inactive')
        _need(_fetch(raw.execute('PRAGMA query_only'), 1) == [(1,)], 'snapshot_inactive')
    return connection


class _CatalogContext:
    __slots__=('connection','manager','source','entered','started','guard')
    def __init__(self,connection,guard=None):
        self.connection=connection;self.manager=None;self.source=None;self.entered=False;self.started=False
        # Export only: the read-contract guard, installed after E0 entry and
        # before the first catalog SQL, removed before E0 exit.
        self.guard=guard

    def _teardown_guard(self,code):
        if self.guard is None:return code
        try:self.guard.teardown()
        except Exception:return 'connection_restore_failed'
        return code

    def __enter__(self):
        _need(not self.entered,'snapshot_inactive');self.entered=True
        code=None;body_error=None
        try:
            _need(isinstance(self.connection,Connection),'connection_required')
            self.manager=readonly_snapshot(self.connection)
            token=self.manager.__enter__()
            self.started=True
            if self.guard is not None:
                _need(token.dialect == self.guard.sqla_dialect,'driver_contract_required')
                self.guard.install(token.connection.connection.driver_connection)
            if token.dialect == 'postgresql':
                descriptor=_collect_pg(token.connection)
                profile=require_source_profile(descriptor)
            else:
                descriptor,profile=_collect(token.connection)
            if self.guard is not None:self.guard.check()
            self.source=CatalogSnapshot(descriptor,profile,_key=_KEY)
            connection=token.connection
            _ACTIVE[id(self.source)]=(self.source,token,connection,connection.get_transaction(),connection.connection.driver_connection,os.getpid(),threading.get_ident())
            self.source.assert_active()
            return self.source
        except (CatalogError,SnapshotConnectionError,_PgCatalogError,_read_contract.ReadContractError) as error:code=error.code
        except SnapshotError:code='source_profile_unsupported'
        except Exception as error:code='snapshot_resource_limit' if self.guard is not None and self.guard.timed_out(error) else 'catalog_failed'
        except BaseException as error:body_error=error
        if self.source is not None:_ACTIVE.pop(id(self.source),None)
        try:
            code=self._teardown_guard(code)
        finally:
            try:
                if self.started:self.manager.__exit__(None,None,None)
            except SnapshotConnectionError as error:code=error.code
            except Exception:code='connection_restore_failed'
        if code is not None:_fail(code)
        raise body_error

    def __exit__(self,kind,error,traceback):
        code=None
        if self.source is not None:
            if error is None:
                try:self.source.assert_active()
                except CatalogError as failure:code=failure.code
            _ACTIVE.pop(id(self.source),None)
        try:
            code=self._teardown_guard(code)
        finally:
            self._exit_snapshot(kind,error,traceback,code)
        return False

    def _exit_snapshot(self,kind,error,traceback,code):
        try:
            self.manager.__exit__(kind,error,traceback)
        except SnapshotConnectionError as failure:
            if failure is error:raise
            code=failure.code
        except BaseException as failure:
            if failure is error:raise
            raise
        if code is not None:_fail(code)


def catalog_snapshot(connection):
    """Only public collector entry; caller supplies and owns an idle Connection."""
    return _CatalogContext(connection)


class _ExportCatalogContext:
    """Contract-gated catalog for export: verify before any source SQL; single use."""
    __slots__=('connection','contract','budget','inner')
    def __init__(self,connection,contract,budget):
        self.connection=connection;self.contract=contract;self.budget=budget;self.inner=None

    def __enter__(self):
        _need(self.inner is None,'snapshot_inactive')
        code=None
        try:guard=_read_contract._begin_use(self.contract,self.connection,self.budget)
        except _read_contract.ReadContractError as error:code=error.code
        except Exception:code='driver_contract_required'
        if code is not None:_fail(code)
        self.inner=_CatalogContext(self.connection,guard)
        try:return self.inner.__enter__()
        except BaseException:
            _read_contract._end_use(self.contract)
            raise

    def __exit__(self,kind,error,traceback):
        try:return self.inner.__exit__(kind,error,traceback)
        finally:_read_contract._end_use(self.contract)


def _catalog_for_export(connection,contract,budget):
    """Private export entry; the public catalog_snapshot keeps its behavior."""
    return _ExportCatalogContext(connection,contract,budget)
