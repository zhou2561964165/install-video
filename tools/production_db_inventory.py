"""Bounded, redacted inventory of an explicitly supplied SQLAlchemy Connection.

No engine creation, environment loading, migration, export, or business row output.
The caller must use a least-privilege role and configure an appropriate timeout.
Only idle connections are accepted; this module owns and rolls back its snapshot.
File SQLite connections must explicitly use URI mode=ro. In-memory is for tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import warnings

from sqlalchemy import (Column, MetaData, Table, and_, exists, func,
                        inspect, not_, or_, select)
from sqlalchemy.engine import Connection
from sqlalchemy.sql import sqltypes

if __package__:
    from tools.production_db_snapshot import SnapshotConnectionError, readonly_snapshot
else:
    from production_db_snapshot import SnapshotConnectionError, readonly_snapshot


LEGACY = {
    'user': 'id email password_hash created_at',
    'quota': 'id user_id date downloads_used limit',
    'job': 'id url title format_id status progress file_path file_size error_type error created_at updated_at expires_at user_id',
    'downloadidempotency': 'id user_id key fingerprint state created_at expires_at direct_expires_at status_code response_json',
    'membership': 'user_id customer_id subscription_id status expires_at cancel_at_period_end active_checkout_id revision entitlement_source',
    'billingcheckout': 'id user_id price_id mode duration_days origin customer_id created_at stripe_id url expires_at state fulfilled',
    'billingevent': 'id processed_at',
    'billingpayment': 'payment_intent user_id source_id revoked',
    'downloadaccess': 'job_id max_height',
}
OPTIONAL_COLUMNS = {
    'downloadidempotency': 'operation_id',
    'billingcheckout': 'provider_account_scope livemode create_payload create_payload_sha256 create_payload_version create_started_at create_completed_at create_result_code reconciliation reconcile_attempts reconciliation_started_at reconciliation_evidence reconciliation_actor reconciliation_reason revision',
    'billingevent': 'provider_account_scope livemode outcome',
}
PROTOCOL = {
    'downloadoperation': 'id user_id canonical_payload fingerprint canonical_format_id max_height membership_revision quota_day state job_id job_id_tombstone accepted_at deadline_at resolve_deadline_at completed_at capacity_reserved resolve_owner resolve_epoch resolve_lease_deadline resolve_attempts_used resolve_attempts_limit resolve_attempt_deadline budget_version budget_checkpoint_json budget_checkpoint_at error_code',
    'quotacharge': 'operation_id user_id quota_day delta charged_at',
    'resourcecounter': 'resource scope used',
    'resourcereservation': 'operation_id resource scope units released reserved_at released_at',
    'billinginbox': 'id provider_account_scope livemode event_id event_type api_version received_at payload_sha256 canonical_sha256 canonical_version canonical_payload business_payload status attempt_count attempt_limit budget_deadline next_run_at lease_owner lease_epoch lease_deadline error_code outcome_reason completed_at payload_purged_at',
    'billingfact': 'id inbox_id user_id checkout_id provider_account_scope livemode event_id payment_intent session_id invoice_id charge_id subscription_id provider_status amount_total amount_refunded currency reconciliation observed_at',
}
RECONCILIATION = {
    'billingreconciliationtask': 'id checkout_id user_id provider_account_scope livemode actor_ref reason_code evidence_ref input_version input_sha256 query_json policy_json initial_checkout_revision expected_checkout_revision membership_revision owner_ref started_at budget_deadline get_attempts get_limit budget_version status outcome_reason completed_at next_audit_seq revision',
    'billingreconciliationaudit': 'id task_id seq event_kind get_ordinal recorded_at actor_ref reason_code evidence_ref projection_version projection_json projection_sha256',
}
FIELDS = {name: frozenset(value.split()) for name, value in (LEGACY | PROTOCOL | RECONCILIATION).items()}
for _name, _cols in OPTIONAL_COLUMNS.items():
    FIELDS[_name] = FIELDS[_name] | frozenset(_cols.split())
FIELDS['alembic_version'] = frozenset({'version_num'})
KNOWN_HEADS = frozenset({'b1_0001', 'b1b_0002', 'b1b_0003', 'b3b_0004'})
UNIQUE = {
    'user': [('id',), ('email',)], 'quota': [('id',), ('user_id', 'date')],
    'job': [('id',)], 'downloadidempotency': [('id',), ('user_id', 'key'), ('operation_id',)],
    'membership': [('user_id',), ('customer_id',), ('subscription_id',)],
    'billingcheckout': [('id',), ('stripe_id',)], 'billingevent': [('id',)],
    'billingpayment': [('payment_intent',)], 'downloadaccess': [('job_id',)],
    'downloadoperation': [('id',), ('job_id',)], 'quotacharge': [('operation_id',)],
    'resourcecounter': [('resource', 'scope')],
    'resourcereservation': [('operation_id', 'resource', 'scope')],
    'billinginbox': [('id',), ('provider_account_scope', 'livemode', 'event_id')],
    'billingfact': [('id',), ('inbox_id',)],
    'billingreconciliationtask': [('id',), ('checkout_id',)],
    'billingreconciliationaudit': [('id',), ('task_id', 'seq'), ('task_id', 'event_kind', 'get_ordinal')],
}
# Frozen logical relationships are audited even when the database lacks its FK.
RELATIONS = {
    'quota': [(('user_id',), 'user', ('id',))],
    'job': [(('user_id',), 'user', ('id',))],
    'downloadidempotency': [(('user_id',), 'user', ('id',)), (('operation_id',), 'downloadoperation', ('id',))],
    'membership': [(('user_id',), 'user', ('id',))],
    'billingcheckout': [(('user_id',), 'user', ('id',))],
    'billingpayment': [(('user_id',), 'user', ('id',))],
    'downloadaccess': [(('job_id',), 'job', ('id',))],
    'downloadoperation': [(('user_id',), 'user', ('id',)), (('job_id',), 'job', ('id',))],
    'quotacharge': [(('operation_id',), 'downloadoperation', ('id',)), (('user_id',), 'user', ('id',))],
    'resourcereservation': [(('operation_id',), 'downloadoperation', ('id',)), (('resource', 'scope'), 'resourcecounter', ('resource', 'scope'))],
    'billingfact': [(('inbox_id',), 'billinginbox', ('id',)), (('user_id',), 'user', ('id',)), (('checkout_id',), 'billingcheckout', ('id',))],
    'billingreconciliationtask': [(('checkout_id',), 'billingcheckout', ('id',)), (('user_id',), 'user', ('id',))],
    'billingreconciliationaudit': [(('task_id',), 'billingreconciliationtask', ('id',))],
}
STATES = {
    ('job', 'status'): ('queued', 'downloading', 'merging', 'done', 'error'),
    ('downloadidempotency', 'state'): ('pending', 'uncertain', 'complete'),
    ('billingcheckout', 'state'): ('pending', 'open', 'paid', 'expired', 'failed', 'uncertain'),
    ('membership', 'status'): ('free', 'active', 'trialing', 'past_due', 'canceled', 'unpaid', 'incomplete', 'incomplete_expired', 'paused'),
    ('downloadoperation', 'state'): ('resolving', 'accepted_server', 'direct_ready', 'succeeded', 'failed', 'needs_review'),
    ('billinginbox', 'status'): ('received', 'processing', 'retry_wait', 'waiting_binding', 'applied', 'ignored', 'needs_review'),
    ('billingfact', 'reconciliation'): ('unknown', 'verified', 'needs_review'),
    ('billingcheckout', 'reconciliation'): ('not_started', 'unknown', 'verified', 'needs_review', 'closed'),
    ('billingreconciliationtask', 'status'): ('running', 'verified', 'needs_review'),
    ('billingreconciliationaudit', 'event_kind'): ('task_started', 'get_reserved', 'get_observed', 'task_finished'),
}
NONNEGATIVE = {
    'quota': 'downloads_used limit', 'job': 'file_size progress',
    'membership': 'expires_at revision', 'billingcheckout': 'duration_days expires_at revision reconcile_attempts',
    'downloadaccess': 'max_height', 'downloadoperation': 'membership_revision resolve_epoch resolve_attempts_used resolve_attempts_limit budget_version max_height',
    'quotacharge': 'delta', 'resourcecounter': 'used', 'resourcereservation': 'units',
    'billinginbox': 'attempt_count attempt_limit lease_epoch canonical_version',
    'billingfact': 'amount_total amount_refunded',
    'billingreconciliationtask': 'input_version initial_checkout_revision expected_checkout_revision membership_revision get_attempts get_limit budget_version next_audit_seq revision',
    'billingreconciliationaudit': 'seq get_ordinal projection_version',
}
EPOCHS = {'downloadidempotency': 'created_at expires_at direct_expires_at', 'billingcheckout': 'created_at expires_at', 'billingevent': 'processed_at', 'membership': 'expires_at'}
TIMES = {
    'user': 'created_at', 'job': 'created_at updated_at expires_at',
    'billingcheckout': 'create_started_at create_completed_at reconciliation_started_at',
    'downloadoperation': 'accepted_at deadline_at resolve_deadline_at completed_at resolve_lease_deadline resolve_attempt_deadline budget_checkpoint_at',
    'quotacharge': 'charged_at', 'resourcereservation': 'reserved_at released_at',
    'billinginbox': 'received_at budget_deadline next_run_at lease_deadline completed_at payload_purged_at',
    'billingfact': 'observed_at', 'quota': 'date',
    'billingreconciliationtask': 'started_at budget_deadline completed_at',
    'billingreconciliationaudit': 'recorded_at',
}
MAX_COLUMNS = 96
MAX_OBJECTS = 96
MAX_QUERIES = 800
MAX_TABLES = 128


class InventoryError(RuntimeError):
    """Fixed error codes only; SQL/parameters/paths/driver errors never escape."""


@dataclass(frozen=True)
class InventoryReport:
    document: dict

    def to_dict(self) -> dict:
        # Return a detached JSON value, not database metadata/rows.
        return json.loads(json.dumps(self.document))


def _type_name(value):
    # Never stringify user-defined types, ENUM labels, or unknown type arguments.
    for kind, label in ((sqltypes.Boolean, 'BOOLEAN'), (sqltypes.BigInteger, 'BIGINT'),
                        (sqltypes.Integer, 'INTEGER'), (sqltypes.DateTime, 'DATETIME'),
                        (sqltypes.Date, 'DATE'), (sqltypes.Float, 'FLOAT'),
                        (sqltypes.Numeric, 'NUMERIC'), (sqltypes.Text, 'TEXT'),
                        (sqltypes.String, 'STRING'), (sqltypes.LargeBinary, 'BINARY')):
        if isinstance(value, kind):
            return label
    return 'OTHER_REDACTED'


def _default_class(value):
    if value is None:
        return 'absent'
    # Do not hash or expose expressions; even numeric defaults may be secrets.
    return 'present_redacted'


def _safe_columns(values, allowed):
    return list(values) if values and all(v in allowed for v in values) else None


def _path_check(output):
    error = None
    try:
        path = Path(output).absolute()
        if path.exists() or path.is_symlink():
            raise InventoryError('output_exists')
        parent = path.parent
        if not parent.is_dir():
            raise InventoryError('output_path_invalid')
        for part in (parent, *parent.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or (getattr(info, 'st_file_attributes', 0) & 0x400):
                raise InventoryError('output_path_unsafe')
        return path
    except InventoryError as exc:
        error = str(exc)
    except Exception:
        error = 'output_path_invalid'
    if error:
        raise InventoryError(error)


def _publish(path, document):
    """Same-directory complete temp + hard link: atomic publish, never replace."""
    temp = None
    error = None
    try:
        _path_check(path)
        fd, name = tempfile.mkstemp(prefix='.inventory-', suffix='.tmp', dir=path.parent)
        temp = Path(name)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(document, stream, ensure_ascii=True, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        _path_check(path)
        os.link(temp, path)  # EEXIST refuses a racing publisher. No rename overwrite.
    except InventoryError as exc:
        error = str(exc)
    except FileExistsError:
        error = 'output_exists'
    except Exception:
        error = 'output_publish_failed'
    finally:
        if temp is not None:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                error = 'output_cleanup_failed'
    if error:
        raise InventoryError(error)


def _reflect(connection, schema):
    inspector = inspect(connection)
    names = set(inspector.get_table_names(schema=schema))
    if len(names) > MAX_TABLES:
        raise InventoryError('schema_limit_exceeded')
    tables, metadata = {}, {}
    for name in sorted(names & FIELDS.keys()):
        columns = inspector.get_columns(name, schema=schema)
        if len(columns) > MAX_COLUMNS:
            raise InventoryError('schema_limit_exceeded')
        allowed = FIELDS[name]
        known = [c for c in columns if c['name'] in allowed]
        actual = {c['name'] for c in known}
        pk = inspector.get_pk_constraint(name, schema=schema)
        unique = inspector.get_unique_constraints(name, schema=schema)
        indexes = inspector.get_indexes(name, schema=schema)
        foreign = inspector.get_foreign_keys(name, schema=schema)
        checks = inspector.get_check_constraints(name, schema=schema)
        if any(len(items) > MAX_OBJECTS for items in (unique, indexes, foreign, checks)):
            raise InventoryError('schema_limit_exceeded')
        uniques = [v for obj in unique if (v := _safe_columns(obj.get('column_names'), allowed))]
        pk_cols = _safe_columns(pk.get('constrained_columns'), allowed) or []
        unique_sets = {frozenset(v) for v in uniques}
        if pk_cols:
            unique_sets.add(frozenset(pk_cols))
        safe_indexes = []
        for obj in indexes:
            cols = _safe_columns(obj.get('column_names'), allowed)
            # Partial/expression indexes are metadata only, never a uniqueness proof.
            partial = any(v is not None for k, v in obj.get('dialect_options', {}).items() if k.endswith('_where'))
            if cols:
                safe_indexes.append({'columns': cols, 'unique': bool(obj.get('unique')), 'partial': partial})
                if obj.get('unique') and not partial and not obj.get('expressions'):
                    unique_sets.add(frozenset(cols))
        safe_foreign = []
        for obj in foreign:
            target = obj.get('referred_table')
            cols = _safe_columns(obj.get('constrained_columns'), allowed)
            remote = _safe_columns(obj.get('referred_columns'), FIELDS.get(target, ()))
            if cols and remote and obj.get('referred_schema') in (None, schema):
                safe_foreign.append({'columns': cols, 'table': target, 'referred_columns': remote})
        missing_fk = []
        for cols, target, remote in RELATIONS.get(name, []):
            if set(cols) <= actual and target in names:
                expected = {'columns': list(cols), 'table': target, 'referred_columns': list(remote)}
                if expected not in safe_foreign:
                    missing_fk.append(expected)
        required = set((LEGACY | PROTOCOL | RECONCILIATION).get(name, '').split())
        metadata[name] = {
            'columns': [{'name': c['name'], 'type': _type_name(c['type']), 'nullable': bool(c['nullable']), 'default': _default_class(c.get('default'))} for c in known],
            'unknown_column_count': len(columns) - len(known),
            'missing_columns': sorted(required - actual), 'primary_key': pk_cols,
            'unique': uniques, 'indexes': safe_indexes, 'foreign_keys': safe_foreign,
            'check_constraint_count': len(checks), 'check_expressions': 'redacted',
            'unrecognized_unique_count': len(unique) - len(uniques),
            'unrecognized_index_count': len(indexes) - len(safe_indexes),
            'unrecognized_foreign_key_count': len(foreign) - len(safe_foreign),
            'missing_unique': [list(v) for v in UNIQUE.get(name, []) if set(v) <= actual and frozenset(v) not in unique_sets],
            'missing_foreign_keys': missing_fk,
        }
        # Build known columns explicitly; no recursive reflection of unknown FKs.
        tables[name] = Table(name, MetaData(), *(Column(c['name'], c['type']) for c in known), schema=schema)
    return tables, metadata, len(names - FIELDS.keys() - {'sqlite_sequence'})


def _count_statement(table, predicate=None):
    stmt = select(func.count()).select_from(table)
    return stmt.where(predicate) if predicate is not None else stmt


def _duplicate_statement(table, columns):
    cols = [table.c[c] for c in columns]
    groups = select(*cols).where(and_(*(c.is_not(None) for c in cols))).group_by(*cols).having(func.count() > 1).subquery()
    return select(func.count()).select_from(groups)


def _orphan_statement(child, parent, columns, remote):
    pairs = [parent.c[r] == child.c[c] for c, r in zip(columns, remote)]
    return _count_statement(child, and_(*(child.c[c].is_not(None) for c in columns), not_(exists(select(1).select_from(parent).where(and_(*pairs))))))


def _aggregates(connection, tables, now):
    calls = 0

    def count(stmt):
        nonlocal calls
        calls += 1
        if calls > MAX_QUERIES:
            raise InventoryError('aggregate_limit_exceeded')
        return int(connection.execute(stmt).scalar_one())

    result = {}
    for name, table in tables.items():
        if name == 'alembic_version':
            continue
        cols = set(table.c.keys())
        item = {'row_count': count(_count_statement(table)), 'duplicate_groups': [], 'orphan_counts': [], 'negative_counts': {}, 'invalid_time_counts': {}}
        for fields in UNIQUE.get(name, []):
            if set(fields) <= cols:
                item['duplicate_groups'].append({'columns': list(fields), 'count': count(_duplicate_statement(table, fields))})
        for fields, target, remote in RELATIONS.get(name, []):
            if set(fields) <= cols and target in tables and set(remote) <= set(tables[target].c.keys()):
                item['orphan_counts'].append({'columns': list(fields), 'table': target, 'count': count(_orphan_statement(table, tables[target], fields, remote))})
        for field in NONNEGATIVE.get(name, '').split():
            if field in cols:
                item['negative_counts'][field] = count(_count_statement(table, table.c[field] < 0))
        for (owner, field), states in STATES.items():
            if owner == name and field in cols:
                column = table.c[field]
                item[field + '_counts'] = {state: count(_count_statement(table, column == state)) for state in states}
                item[field + '_unknown_count'] = count(_count_statement(table, or_(column.is_(None), column.not_in(states))))
        for field in TIMES.get(name, '').split():
            if field not in cols:
                continue
            column = table.c[field]
            # SQLite has no native date validation. PG's native Date/DateTime
            # input already validates syntax; unexpected text is not cast unsafely.
            if connection.dialect.name == 'sqlite':
                invalid = and_(column.is_not(None), func.julianday(column).is_(None))
                item['invalid_time_counts'][field] = count(_count_statement(table, invalid))
            elif isinstance(column.type, (sqltypes.Date, sqltypes.DateTime)):
                item['invalid_time_counts'][field] = 0
            else:
                item['invalid_time_counts'][field] = None
                item.setdefault('unvalidated_time_columns', []).append(field)
        for field in EPOCHS.get(name, '').split():
            if field in cols:
                column = table.c[field]
                if connection.dialect.name == 'sqlite':
                    invalid = and_(column.is_not(None), or_(func.typeof(column).not_in(('real', 'integer')), column < 0, column > 253402300799))
                else:
                    invalid = and_(column.is_not(None), or_(column < 0, column > 253402300799))
                item['invalid_time_counts'][field] = count(_count_statement(table, invalid))
        if name in ('downloadidempotency', 'billingcheckout') and {'state', 'created_at'} <= cols:
            item['pending_older_than_24h_count'] = count(_count_statement(table, and_(table.c.state == 'pending', table.c.created_at < now.timestamp() - 86400)))
        if name == 'job':
            if {'status', 'created_at'} <= cols:
                old = func.julianday(table.c.created_at) < func.julianday(now.isoformat()) - 1 if connection.dialect.name == 'sqlite' else table.c.created_at < now - timedelta(days=1)
                item['queued_older_than_24h_count'] = count(_count_statement(table, and_(table.c.status == 'queued', old)))
            operations = tables.get('downloadoperation')
            if operations is not None and 'job_id' in operations.c and 'id' in table.c:
                item['legacy_job_count'] = count(_count_statement(table, not_(exists(select(1).select_from(operations).where(operations.c.job_id == table.c.id)))))
            else:
                item['legacy_job_count'] = item['row_count']
        result[name] = item
    return result


def inventory_database(connection: Connection, *, schema_only: bool, output: Path) -> InventoryReport:
    """Reflect only known tables and optionally count anomalies; never read rows.

    PostgreSQL uses only app (never search_path). Schema-only does SELECT the
    allowlisted Alembic heads but never business data. PostgreSQL requires a
    synchronous psycopg/psycopg2 driver and an idle SQLAlchemy AND DBAPI connection.
    Execution options and exact DBAPI isolation/autocommit settings are preserved.
    No Connection is closed. On connection_restore_failed the caller must discard
    the connection; no successful report is published.
    """
    path = _path_check(output)
    if not isinstance(connection, Connection) or connection.closed:
        raise InventoryError('connection_required')
    if connection.in_transaction():
        raise InventoryError('active_transaction_refused')
    if type(schema_only) is not bool:
        raise InventoryError('invalid_schema_only')
    error = None
    try:
        with readonly_snapshot(connection) as snapshot:
            dialect = snapshot.dialect
            schema = snapshot.schema_scope
            with warnings.catch_warnings():
                # Reflection warnings may include unknown expression/index names.
                warnings.simplefilter('ignore')
                tables, metadata, extra_count = _reflect(connection, schema)
            heads = []
            unknown_heads = 0
            version = tables.get('alembic_version')
            if version is not None and 'version_num' in version.c:
                # Bounded version rows only; unknown revision strings are redacted.
                values = list(connection.execute(select(version.c.version_num).limit(9)).scalars())
                if len(values) > 8:
                    raise InventoryError('version_limit_exceeded')
                heads = sorted(v for v in values if v in KNOWN_HEADS)
                unknown_heads = sum(v not in KNOWN_HEADS for v in values)
                if unknown_heads:
                    raise InventoryError('unknown_version_head')
            now = datetime.now(timezone.utc)
            document = {'format_version': 1, 'dialect': dialect, 'schema_scope': 'main' if dialect == 'sqlite' else 'app',
                        'schema_only': schema_only, 'snapshot': 'read_only_rollback', 'created_utc': now.isoformat(),
                        'schema': metadata, 'missing_legacy_tables': sorted(LEGACY.keys() - tables.keys()),
                        'missing_protocol_tables': sorted(PROTOCOL.keys() - tables.keys()),
                        'missing_reconciliation_tables': sorted(RECONCILIATION.keys() - tables.keys()),
                        # Observed allowlisted counts, not migration certification.
                        'known_table_count': len(tables),
                        'known_business_table_count': len(tables.keys() - {'alembic_version'}),
                        'known_business_table_counts': {
                            'legacy': len(LEGACY.keys() & tables.keys()),
                            'protocol': len(PROTOCOL.keys() & tables.keys()),
                            'reconciliation': len(RECONCILIATION.keys() & tables.keys())},
                        'unknown_table_count': extra_count, 'version_table_present': version is not None, 'version_heads': heads,
                        'unknown_version_head_count': unknown_heads,
                        'aggregates': {} if schema_only else _aggregates(connection, tables, now)}
            if dialect == 'sqlite':
                document['connection_pragmas'] = {key: connection.exec_driver_sql('PRAGMA ' + key).scalar_one() for key in ('query_only', 'foreign_keys')}
            else:
                document['postgres_server_version'] = list(connection.dialect.server_version_info or ())
            report = InventoryReport(document)
    except SnapshotConnectionError as exc:
        error = 'inventory_failed' if exc.code == 'snapshot_failed' else exc.code
    except InventoryError as exc:
        error = str(exc)
    except Exception:
        error = 'inventory_failed'
    if error:
        raise InventoryError(error)
    _publish(path, report.document)
    return report


def main(argv=None):
    """Connection management intentionally deferred; all CLI input is rejected."""
    # Never let argparse echo arguments that may contain credentials.
    args = sys.argv[1:] if argv is None else argv
    if args == ['--help']:
        sys.stdout.write('API only: inventory_database(connection, *, schema_only, output).\nConnection management and secure stdin CLI are deferred. No DSN arguments accepted.\n')
        return 0
    sys.stderr.write('inventory_cli_connection_not_implemented\n')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
