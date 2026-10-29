"""Six immutable expected schema declarations; no source is authenticated here.

Transcribed from the reviewed B6 static DDL attachment (2026-10-25).
Do not infer a profile from ID, head alone, table counts or unioned ORM fields.
Actual complete catalog/driver/ACL verification remains a separate E2 gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from tools.production_db_snapshot_format import _raise_safe
from tools.production_db_snapshot_schema import (
    PhysicalType, ColumnDescriptor, UniqueDescriptor, ForeignKeyDescriptor,
    IndexDescriptor, TriggerDescriptor, TableDescriptor, SchemaDescriptor,
    _boundary, _require, _argument, _schema_bytes,
)


def _table(name, columns, pk, uniques=(), foreign_keys=(), indexes=(), checks=(), triggers=()):
    dialect = columns[0][1].split('_', 1)[0]
    return TableDescriptor(name,
        tuple(ColumnDescriptor(n, PhysicalType(k, a), nullable, 'absent', 'absent', 'absent',
            'dialect_default') for n, k, a, nullable in columns), pk,
        tuple(UniqueDescriptor(c, True, False, False, True) for c in uniques),
        tuple(ForeignKeyDescriptor(c, ns, target, tc, 'NO_ACTION', delete, 'SIMPLE', False,
            False, True) for c, ns, target, tc, delete in foreign_keys),
        tuple(IndexDescriptor(c, unique, 'btree', ('asc',) * len(c),
            ('dialect_default',) * len(c), pred, (), True) for c, unique, pred in indexes),
        tuple(sorted(checks)),
        tuple(TriggerDescriptor(rule, fn, 'BEFORE', events, level, 'origin_enabled_v1')
            for rule, fn, events, level in sorted(triggers)),
        'sqlite_ordinary_rowid_v1' if dialect == 'sqlite' else 'pg_ordinary_heap_v1',
        'nondeferrable_validated_v1')


_S9_BILLINGCHECKOUT = _table('billingcheckout', (
    ('id', 'sqlite_varchar', (), False),
    ('user_id', 'sqlite_varchar', (), False),
    ('price_id', 'sqlite_varchar', (), False),
    ('mode', 'sqlite_varchar', (), False),
    ('duration_days', 'sqlite_integer', (), False),
    ('origin', 'sqlite_varchar', (), False),
    ('customer_id', 'sqlite_varchar', (), True),
    ('created_at', 'sqlite_float', (), False),
    ('stripe_id', 'sqlite_varchar', (), True),
    ('url', 'sqlite_varchar', (), True),
    ('expires_at', 'sqlite_float', (), False),
    ('state', 'sqlite_varchar', (), False),
    ('fulfilled', 'sqlite_boolean', (), False),
), ('id',),
    (('stripe_id',),),
    ((('user_id',), 'main', 'user', ('id',), 'NO_ACTION'),),
    ((('user_id',), False, 'absent'),),
    (),
    ())

_S9_BILLINGEVENT = _table('billingevent', (
    ('id', 'sqlite_varchar', (), False),
    ('processed_at', 'sqlite_float', (), False),
), ('id',),
    (),
    (),
    (),
    (),
    ())

_S9_BILLINGPAYMENT = _table('billingpayment', (
    ('payment_intent', 'sqlite_varchar', (), False),
    ('user_id', 'sqlite_varchar', (), True),
    ('source_id', 'sqlite_varchar', (), True),
    ('revoked', 'sqlite_boolean', (), False),
), ('payment_intent',),
    (),
    ((('user_id',), 'main', 'user', ('id',), 'NO_ACTION'),),
    ((('user_id',), False, 'absent'),),
    (),
    ())

_S9_DOWNLOADACCESS = _table('downloadaccess', (
    ('job_id', 'sqlite_varchar', (), False),
    ('max_height', 'sqlite_integer', (), True),
), ('job_id',),
    (),
    ((('job_id',), 'main', 'job', ('id',), 'NO_ACTION'),),
    (),
    (),
    ())

_S9_DOWNLOADIDEMPOTENCY = _table('downloadidempotency', (
    ('id', 'sqlite_varchar', (), False),
    ('user_id', 'sqlite_varchar', (), False),
    ('key', 'sqlite_varchar', (128,), False),
    ('fingerprint', 'sqlite_varchar', (), False),
    ('state', 'sqlite_varchar', (), False),
    ('created_at', 'sqlite_float', (), False),
    ('expires_at', 'sqlite_float', (), True),
    ('direct_expires_at', 'sqlite_float', (), True),
    ('status_code', 'sqlite_integer', (), True),
    ('response_json', 'sqlite_varchar', (), True),
), ('id',),
    (('user_id', 'key'),),
    ((('user_id',), 'main', 'user', ('id',), 'NO_ACTION'),),
    ((('expires_at',), False, 'absent'), (('user_id',), False, 'absent')),
    (),
    ())

_S9_JOB = _table('job', (
    ('id', 'sqlite_varchar', (), False),
    ('url', 'sqlite_varchar', (), False),
    ('title', 'sqlite_varchar', (), True),
    ('format_id', 'sqlite_varchar', (), True),
    ('status', 'sqlite_varchar', (11,), False),
    ('progress', 'sqlite_float', (), False),
    ('file_path', 'sqlite_varchar', (), True),
    ('file_size', 'sqlite_integer', (), True),
    ('error_type', 'sqlite_varchar', (), True),
    ('error', 'sqlite_varchar', (), True),
    ('created_at', 'sqlite_datetime', (), False),
    ('updated_at', 'sqlite_datetime', (), False),
    ('expires_at', 'sqlite_datetime', (), True),
    ('user_id', 'sqlite_varchar', (), True),
), ('id',),
    (),
    ((('user_id',), 'main', 'user', ('id',), 'NO_ACTION'),),
    (),
    (),
    ())

_S9_MEMBERSHIP = _table('membership', (
    ('user_id', 'sqlite_varchar', (), False),
    ('customer_id', 'sqlite_varchar', (), True),
    ('subscription_id', 'sqlite_varchar', (), True),
    ('status', 'sqlite_varchar', (), False),
    ('expires_at', 'sqlite_float', (), False),
    ('cancel_at_period_end', 'sqlite_boolean', (), False),
    ('active_checkout_id', 'sqlite_varchar', (), True),
    ('revision', 'sqlite_integer', (), False),
    ('entitlement_source', 'sqlite_varchar', (), True),
), ('user_id',),
    (('customer_id',), ('subscription_id',)),
    ((('user_id',), 'main', 'user', ('id',), 'NO_ACTION'),),
    (),
    (),
    ())

_S9_QUOTA = _table('quota', (
    ('id', 'sqlite_varchar', (), False),
    ('user_id', 'sqlite_varchar', (), False),
    ('date', 'sqlite_varchar', (), False),
    ('downloads_used', 'sqlite_integer', (), False),
    ('limit', 'sqlite_integer', (), False),
), ('id',),
    (('user_id', 'date'),),
    ((('user_id',), 'main', 'user', ('id',), 'NO_ACTION'),),
    ((('user_id',), False, 'absent'),),
    (),
    ())

_S9_USER = _table('user', (
    ('id', 'sqlite_varchar', (), False),
    ('email', 'sqlite_varchar', (), False),
    ('password_hash', 'sqlite_varchar', (), False),
    ('created_at', 'sqlite_datetime', (), False),
), ('id',),
    (),
    (),
    ((('email',), True, 'absent'),),
    (),
    ())

_S17_BILLINGCHECKOUT = _table('billingcheckout', (
    ('id', 'sqlite_varchar', (), False),
    ('user_id', 'sqlite_varchar', (), False),
    ('price_id', 'sqlite_varchar', (), False),
    ('mode', 'sqlite_varchar', (), False),
    ('duration_days', 'sqlite_integer', (), False),
    ('origin', 'sqlite_varchar', (), False),
    ('customer_id', 'sqlite_varchar', (), True),
    ('created_at', 'sqlite_float', (), False),
    ('stripe_id', 'sqlite_varchar', (), True),
    ('url', 'sqlite_varchar', (), True),
    ('expires_at', 'sqlite_float', (), False),
    ('state', 'sqlite_varchar', (), False),
    ('fulfilled', 'sqlite_boolean', (), False),
    ('provider_account_scope', 'sqlite_varchar', (), True),
    ('livemode', 'sqlite_boolean', (), True),
    ('create_payload', 'sqlite_text', (), True),
    ('create_payload_sha256', 'sqlite_varchar', (64,), True),
    ('create_payload_version', 'sqlite_integer', (), True),
    ('create_started_at', 'sqlite_datetime', (), True),
    ('create_completed_at', 'sqlite_datetime', (), True),
    ('create_result_code', 'sqlite_varchar', (), True),
    ('reconciliation', 'sqlite_varchar', (), True),
    ('reconcile_attempts', 'sqlite_integer', (), False),
    ('reconciliation_started_at', 'sqlite_datetime', (), True),
    ('reconciliation_evidence', 'sqlite_varchar', (), True),
    ('reconciliation_actor', 'sqlite_varchar', (), True),
    ('reconciliation_reason', 'sqlite_varchar', (), True),
    ('revision', 'sqlite_bigint', (), False),
), ('id',),
    (('stripe_id',),),
    ((('user_id',), 'main', 'user', ('id',), 'NO_ACTION'),),
    ((('user_id',), False, 'absent'),),
    ('billingcheckout.reconcile_attempts.v1', 'billingcheckout.reconciliation.v1'),
    ())

_S17_BILLINGEVENT = _table('billingevent', (
    ('id', 'sqlite_varchar', (), False),
    ('processed_at', 'sqlite_float', (), False),
    ('provider_account_scope', 'sqlite_varchar', (), False),
    ('livemode', 'sqlite_boolean', (), True),
    ('outcome', 'sqlite_varchar', (), True),
), ('id',),
    (),
    (),
    (),
    ('billingevent.scope_mode.v1',),
    ())

_S17_BILLINGFACT = _table('billingfact', (
    ('id', 'sqlite_varchar', (), False),
    ('inbox_id', 'sqlite_varchar', (), True),
    ('user_id', 'sqlite_varchar', (), True),
    ('checkout_id', 'sqlite_varchar', (), True),
    ('provider_account_scope', 'sqlite_varchar', (), False),
    ('livemode', 'sqlite_boolean', (), True),
    ('event_id', 'sqlite_varchar', (), True),
    ('payment_intent', 'sqlite_varchar', (), True),
    ('session_id', 'sqlite_varchar', (), True),
    ('invoice_id', 'sqlite_varchar', (), True),
    ('charge_id', 'sqlite_varchar', (), True),
    ('subscription_id', 'sqlite_varchar', (), True),
    ('provider_status', 'sqlite_varchar', (), True),
    ('amount_total', 'sqlite_bigint', (), True),
    ('amount_refunded', 'sqlite_bigint', (), True),
    ('currency', 'sqlite_varchar', (3,), True),
    ('reconciliation', 'sqlite_varchar', (), False),
    ('observed_at', 'sqlite_datetime', (), False),
), ('id',),
    (('inbox_id',),),
    ((('checkout_id',), 'main', 'billingcheckout', ('id',), 'RESTRICT'), (('inbox_id',), 'main', 'billinginbox', ('id',), 'RESTRICT'), (('user_id',), 'main', 'user', ('id',), 'RESTRICT')),
    ((('checkout_id',), False, 'absent'), (('provider_account_scope', 'livemode', 'payment_intent'), False, 'absent')),
    ('billingfact.amount_refunded.v1', 'billingfact.amount_total.v1', 'billingfact.reconciliation.v1', 'billingfact.scope_mode.v1'),
    ())

_S17_BILLINGINBOX = _table('billinginbox', (
    ('id', 'sqlite_varchar', (), False),
    ('provider_account_scope', 'sqlite_varchar', (), False),
    ('livemode', 'sqlite_boolean', (), False),
    ('event_id', 'sqlite_varchar', (), False),
    ('event_type', 'sqlite_varchar', (), False),
    ('api_version', 'sqlite_varchar', (), True),
    ('received_at', 'sqlite_datetime', (), False),
    ('payload_sha256', 'sqlite_varchar', (64,), False),
    ('canonical_sha256', 'sqlite_varchar', (64,), False),
    ('canonical_version', 'sqlite_integer', (), False),
    ('canonical_payload', 'sqlite_text', (), False),
    ('business_payload', 'sqlite_text', (), True),
    ('status', 'sqlite_varchar', (), False),
    ('attempt_count', 'sqlite_bigint', (), False),
    ('attempt_limit', 'sqlite_bigint', (), False),
    ('budget_deadline', 'sqlite_datetime', (), False),
    ('next_run_at', 'sqlite_datetime', (), False),
    ('lease_owner', 'sqlite_varchar', (), True),
    ('lease_epoch', 'sqlite_bigint', (), False),
    ('lease_deadline', 'sqlite_datetime', (), True),
    ('error_code', 'sqlite_varchar', (), True),
    ('outcome_reason', 'sqlite_varchar', (), True),
    ('completed_at', 'sqlite_datetime', (), True),
    ('payload_purged_at', 'sqlite_datetime', (), True),
), ('id',),
    (('provider_account_scope', 'livemode', 'event_id'),),
    (),
    ((('status', 'lease_deadline'), False, 'absent'), (('status', 'next_run_at'), False, 'absent')),
    ('billinginbox.budget.v1', 'billinginbox.budget_deadline.v1', 'billinginbox.canonical_version.v1', 'billinginbox.lease_pair.v1', 'billinginbox.processing_lease.v1', 'billinginbox.status.v1'),
    ())

_S17_BILLINGRECONCILIATIONAUDIT = _table('billingreconciliationaudit', (
    ('id', 'sqlite_varchar', (36,), False),
    ('task_id', 'sqlite_varchar', (), False),
    ('seq', 'sqlite_bigint', (), False),
    ('event_kind', 'sqlite_varchar', (16,), False),
    ('get_ordinal', 'sqlite_integer', (), True),
    ('recorded_at', 'sqlite_datetime', (), False),
    ('actor_ref', 'sqlite_varchar', (63,), False),
    ('reason_code', 'sqlite_varchar', (32,), False),
    ('evidence_ref', 'sqlite_varchar', (123,), False),
    ('projection_version', 'sqlite_integer', (), False),
    ('projection_json', 'sqlite_text', (), False),
    ('projection_sha256', 'sqlite_varchar', (64,), False),
), ('id',),
    (('task_id', 'event_kind', 'get_ordinal'), ('task_id', 'seq')),
    ((('task_id',), 'main', 'billingreconciliationtask', ('id',), 'RESTRICT'),),
    ((('task_id', 'event_kind'), True, 'get_ordinal_is_null_v1'),),
    ('billingreconciliationaudit.event_ordinal.v1', 'billingreconciliationaudit.reason.v1', 'billingreconciliationaudit.sequence_version.v1'),
    ())

_S17_BILLINGRECONCILIATIONTASK = _table('billingreconciliationtask', (
    ('id', 'sqlite_varchar', (36,), False),
    ('checkout_id', 'sqlite_varchar', (), False),
    ('user_id', 'sqlite_varchar', (), False),
    ('provider_account_scope', 'sqlite_varchar', (128,), False),
    ('livemode', 'sqlite_boolean', (), False),
    ('actor_ref', 'sqlite_varchar', (63,), False),
    ('reason_code', 'sqlite_varchar', (32,), False),
    ('evidence_ref', 'sqlite_varchar', (123,), False),
    ('input_version', 'sqlite_integer', (), False),
    ('input_sha256', 'sqlite_varchar', (64,), False),
    ('query_json', 'sqlite_text', (), False),
    ('policy_json', 'sqlite_text', (), False),
    ('initial_checkout_revision', 'sqlite_bigint', (), False),
    ('expected_checkout_revision', 'sqlite_bigint', (), False),
    ('membership_revision', 'sqlite_bigint', (), False),
    ('owner_ref', 'sqlite_varchar', (128,), False),
    ('started_at', 'sqlite_datetime', (), False),
    ('budget_deadline', 'sqlite_datetime', (), False),
    ('get_attempts', 'sqlite_bigint', (), False),
    ('get_limit', 'sqlite_integer', (), False),
    ('budget_version', 'sqlite_integer', (), False),
    ('status', 'sqlite_varchar', (16,), False),
    ('outcome_reason', 'sqlite_varchar', (64,), True),
    ('completed_at', 'sqlite_datetime', (), True),
    ('next_audit_seq', 'sqlite_bigint', (), False),
    ('revision', 'sqlite_bigint', (), False),
), ('id',),
    (('checkout_id',),),
    ((('checkout_id',), 'main', 'billingcheckout', ('id',), 'RESTRICT'), (('user_id',), 'main', 'user', ('id',), 'RESTRICT')),
    ((('status', 'budget_deadline'), False, 'absent'), (('user_id',), False, 'absent')),
    ('billingreconciliationtask.deadline.v1', 'billingreconciliationtask.get_budget.v1', 'billingreconciliationtask.reason.v1', 'billingreconciliationtask.revisions.v1', 'billingreconciliationtask.scope.v1', 'billingreconciliationtask.terminal.v1', 'billingreconciliationtask.versions_limits.v1'),
    ())

_S17_DOWNLOADIDEMPOTENCY = _table('downloadidempotency', (
    ('id', 'sqlite_varchar', (), False),
    ('user_id', 'sqlite_varchar', (), False),
    ('key', 'sqlite_varchar', (128,), False),
    ('fingerprint', 'sqlite_varchar', (), False),
    ('state', 'sqlite_varchar', (), False),
    ('created_at', 'sqlite_float', (), False),
    ('expires_at', 'sqlite_float', (), True),
    ('direct_expires_at', 'sqlite_float', (), True),
    ('status_code', 'sqlite_integer', (), True),
    ('response_json', 'sqlite_varchar', (), True),
    ('operation_id', 'sqlite_varchar', (), True),
), ('id',),
    (('operation_id',), ('user_id', 'key')),
    ((('operation_id',), 'main', 'downloadoperation', ('id',), 'RESTRICT'), (('user_id',), 'main', 'user', ('id',), 'NO_ACTION')),
    ((('expires_at',), False, 'absent'), (('user_id',), False, 'absent')),
    (),
    ())

_S17_DOWNLOADOPERATION = _table('downloadoperation', (
    ('id', 'sqlite_varchar', (), False),
    ('user_id', 'sqlite_varchar', (), False),
    ('canonical_payload', 'sqlite_text', (), False),
    ('fingerprint', 'sqlite_varchar', (64,), False),
    ('canonical_format_id', 'sqlite_varchar', (), False),
    ('max_height', 'sqlite_integer', (), True),
    ('membership_revision', 'sqlite_bigint', (), False),
    ('quota_day', 'sqlite_date', (), False),
    ('state', 'sqlite_varchar', (), False),
    ('job_id', 'sqlite_varchar', (), True),
    ('job_id_tombstone', 'sqlite_varchar', (), True),
    ('accepted_at', 'sqlite_datetime', (), False),
    ('deadline_at', 'sqlite_datetime', (), False),
    ('resolve_deadline_at', 'sqlite_datetime', (), False),
    ('completed_at', 'sqlite_datetime', (), True),
    ('capacity_reserved', 'sqlite_boolean', (), False),
    ('resolve_owner', 'sqlite_varchar', (), True),
    ('resolve_epoch', 'sqlite_bigint', (), False),
    ('resolve_lease_deadline', 'sqlite_datetime', (), True),
    ('resolve_attempts_used', 'sqlite_bigint', (), False),
    ('resolve_attempts_limit', 'sqlite_bigint', (), False),
    ('resolve_attempt_deadline', 'sqlite_datetime', (), True),
    ('budget_version', 'sqlite_integer', (), False),
    ('budget_checkpoint_json', 'sqlite_text', (), False),
    ('budget_checkpoint_at', 'sqlite_datetime', (), False),
    ('error_code', 'sqlite_varchar', (), True),
), ('id',),
    (('job_id',),),
    ((('job_id',), 'main', 'job', ('id',), 'RESTRICT'), (('user_id',), 'main', 'user', ('id',), 'RESTRICT')),
    ((('state', 'resolve_lease_deadline'), False, 'absent'), (('user_id', 'accepted_at'), False, 'absent')),
    ('downloadoperation.access_snapshot.v1', 'downloadoperation.budget_checkpoint.v1', 'downloadoperation.checkpoint_time.v1', 'downloadoperation.deadline.v1', 'downloadoperation.resolve_budget.v1', 'downloadoperation.resolve_deadline.v1', 'downloadoperation.resolve_lease_pair.v1', 'downloadoperation.state.v1'),
    ())

_S17_JOB = _table('job', (
    ('id', 'sqlite_varchar', (), False),
    ('url', 'sqlite_varchar', (), False),
    ('title', 'sqlite_varchar', (), True),
    ('format_id', 'sqlite_varchar', (), True),
    ('status', 'sqlite_varchar', (11,), False),
    ('progress', 'sqlite_float', (), False),
    ('file_path', 'sqlite_varchar', (), True),
    ('file_size', 'sqlite_bigint', (), True),
    ('error_type', 'sqlite_varchar', (), True),
    ('error', 'sqlite_varchar', (), True),
    ('created_at', 'sqlite_datetime', (), False),
    ('updated_at', 'sqlite_datetime', (), False),
    ('expires_at', 'sqlite_datetime', (), True),
    ('user_id', 'sqlite_varchar', (), True),
), ('id',),
    (),
    ((('user_id',), 'main', 'user', ('id',), 'NO_ACTION'),),
    (),
    ('job.status.v1',),
    ())

_S17_QUOTACHARGE = _table('quotacharge', (
    ('operation_id', 'sqlite_varchar', (), False),
    ('user_id', 'sqlite_varchar', (), False),
    ('quota_day', 'sqlite_date', (), False),
    ('delta', 'sqlite_bigint', (), False),
    ('charged_at', 'sqlite_datetime', (), False),
), ('operation_id',),
    (),
    ((('operation_id',), 'main', 'downloadoperation', ('id',), 'RESTRICT'), (('user_id',), 'main', 'user', ('id',), 'RESTRICT')),
    ((('user_id', 'quota_day'), False, 'absent'),),
    ('quotacharge.delta_one.v1',),
    ())

_S17_RESOURCECOUNTER = _table('resourcecounter', (
    ('resource', 'sqlite_varchar', (), False),
    ('scope', 'sqlite_varchar', (), False),
    ('used', 'sqlite_bigint', (), False),
), ('resource', 'scope'),
    (),
    (),
    (),
    ('resourcecounter.used_nonnegative.v1',),
    ())

_S17_RESOURCERESERVATION = _table('resourcereservation', (
    ('operation_id', 'sqlite_varchar', (), False),
    ('resource', 'sqlite_varchar', (), False),
    ('scope', 'sqlite_varchar', (), False),
    ('units', 'sqlite_bigint', (), False),
    ('released', 'sqlite_boolean', (), False),
    ('reserved_at', 'sqlite_datetime', (), False),
    ('released_at', 'sqlite_datetime', (), True),
), ('operation_id', 'resource', 'scope'),
    (),
    ((('operation_id',), 'main', 'downloadoperation', ('id',), 'RESTRICT'), (('resource', 'scope'), 'main', 'resourcecounter', ('resource', 'scope'), 'RESTRICT')),
    ((('resource', 'scope', 'released'), False, 'absent'),),
    ('resourcereservation.release_state.v1', 'resourcereservation.units_positive.v1'),
    ())

_P1_ALEMBIC_VERSION = _table('alembic_version', (
    ('version_num', 'pg_varchar', (32,), False),
), ('version_num',),
    (),
    (),
    (),
    (),
    ())

_P1_BILLINGCHECKOUT = _table('billingcheckout', (
    ('id', 'pg_varchar', (), False),
    ('user_id', 'pg_varchar', (), False),
    ('price_id', 'pg_varchar', (), False),
    ('mode', 'pg_varchar', (), False),
    ('duration_days', 'pg_int4', (), False),
    ('origin', 'pg_varchar', (), False),
    ('customer_id', 'pg_varchar', (), True),
    ('created_at', 'pg_float8', (), False),
    ('stripe_id', 'pg_varchar', (), True),
    ('url', 'pg_varchar', (), True),
    ('expires_at', 'pg_float8', (), False),
    ('state', 'pg_varchar', (), False),
    ('fulfilled', 'pg_bool', (), False),
), ('id',),
    (('stripe_id',),),
    ((('user_id',), 'app', 'user', ('id',), 'NO_ACTION'),),
    ((('user_id',), False, 'absent'),),
    (),
    ())

_P1_BILLINGEVENT = _table('billingevent', (
    ('id', 'pg_varchar', (), False),
    ('processed_at', 'pg_float8', (), False),
), ('id',),
    (),
    (),
    (),
    (),
    ())

_P1_BILLINGPAYMENT = _table('billingpayment', (
    ('payment_intent', 'pg_varchar', (), False),
    ('user_id', 'pg_varchar', (), True),
    ('source_id', 'pg_varchar', (), True),
    ('revoked', 'pg_bool', (), False),
), ('payment_intent',),
    (),
    ((('user_id',), 'app', 'user', ('id',), 'NO_ACTION'),),
    ((('user_id',), False, 'absent'),),
    (),
    ())

_P1_DOWNLOADACCESS = _table('downloadaccess', (
    ('job_id', 'pg_varchar', (), False),
    ('max_height', 'pg_int4', (), True),
), ('job_id',),
    (),
    ((('job_id',), 'app', 'job', ('id',), 'NO_ACTION'),),
    (),
    (),
    ())

_P1_DOWNLOADIDEMPOTENCY = _table('downloadidempotency', (
    ('id', 'pg_varchar', (), False),
    ('user_id', 'pg_varchar', (), False),
    ('key', 'pg_varchar', (128,), False),
    ('fingerprint', 'pg_varchar', (), False),
    ('state', 'pg_varchar', (), False),
    ('created_at', 'pg_float8', (), False),
    ('expires_at', 'pg_float8', (), True),
    ('direct_expires_at', 'pg_float8', (), True),
    ('status_code', 'pg_int4', (), True),
    ('response_json', 'pg_varchar', (), True),
), ('id',),
    (('user_id', 'key'),),
    ((('user_id',), 'app', 'user', ('id',), 'NO_ACTION'),),
    ((('expires_at',), False, 'absent'), (('user_id',), False, 'absent')),
    (),
    ())

_P1_JOB = _table('job', (
    ('id', 'pg_varchar', (), False),
    ('url', 'pg_varchar', (), False),
    ('title', 'pg_varchar', (), True),
    ('format_id', 'pg_varchar', (), True),
    ('status', 'pg_varchar', (11,), False),
    ('progress', 'pg_float8', (), False),
    ('file_path', 'pg_varchar', (), True),
    ('file_size', 'pg_int8', (), True),
    ('error_type', 'pg_varchar', (), True),
    ('error', 'pg_varchar', (), True),
    ('created_at', 'pg_timestamptz', (), False),
    ('updated_at', 'pg_timestamptz', (), False),
    ('expires_at', 'pg_timestamptz', (), True),
    ('user_id', 'pg_varchar', (), True),
), ('id',),
    (),
    ((('user_id',), 'app', 'user', ('id',), 'NO_ACTION'),),
    (),
    ('job.status.v1',),
    ())

_P1_MEMBERSHIP = _table('membership', (
    ('user_id', 'pg_varchar', (), False),
    ('customer_id', 'pg_varchar', (), True),
    ('subscription_id', 'pg_varchar', (), True),
    ('status', 'pg_varchar', (), False),
    ('expires_at', 'pg_float8', (), False),
    ('cancel_at_period_end', 'pg_bool', (), False),
    ('active_checkout_id', 'pg_varchar', (), True),
    ('revision', 'pg_int4', (), False),
    ('entitlement_source', 'pg_varchar', (), True),
), ('user_id',),
    (('customer_id',), ('subscription_id',)),
    ((('user_id',), 'app', 'user', ('id',), 'NO_ACTION'),),
    (),
    (),
    ())

_P1_QUOTA = _table('quota', (
    ('id', 'pg_varchar', (), False),
    ('user_id', 'pg_varchar', (), False),
    ('date', 'pg_varchar', (), False),
    ('downloads_used', 'pg_int4', (), False),
    ('limit', 'pg_int4', (), False),
), ('id',),
    (('user_id', 'date'),),
    ((('user_id',), 'app', 'user', ('id',), 'NO_ACTION'),),
    ((('user_id',), False, 'absent'),),
    (),
    ())

_P1_USER = _table('user', (
    ('id', 'pg_varchar', (), False),
    ('email', 'pg_varchar', (), False),
    ('password_hash', 'pg_varchar', (), False),
    ('created_at', 'pg_timestamptz', (), False),
), ('id',),
    (),
    (),
    ((('email',), True, 'absent'),),
    (),
    ())

_P2_DOWNLOADIDEMPOTENCY = _table('downloadidempotency', (
    ('id', 'pg_varchar', (), False),
    ('user_id', 'pg_varchar', (), False),
    ('key', 'pg_varchar', (128,), False),
    ('fingerprint', 'pg_varchar', (), False),
    ('state', 'pg_varchar', (), False),
    ('created_at', 'pg_float8', (), False),
    ('expires_at', 'pg_float8', (), True),
    ('direct_expires_at', 'pg_float8', (), True),
    ('status_code', 'pg_int4', (), True),
    ('response_json', 'pg_varchar', (), True),
    ('operation_id', 'pg_varchar', (), True),
), ('id',),
    (('operation_id',), ('user_id', 'key')),
    ((('operation_id',), 'app', 'downloadoperation', ('id',), 'RESTRICT'), (('user_id',), 'app', 'user', ('id',), 'NO_ACTION')),
    ((('expires_at',), False, 'absent'), (('user_id',), False, 'absent')),
    (),
    ())

_P2_DOWNLOADOPERATION = _table('downloadoperation', (
    ('id', 'pg_varchar', (), False),
    ('user_id', 'pg_varchar', (), False),
    ('canonical_payload', 'pg_text', (), False),
    ('fingerprint', 'pg_varchar', (64,), False),
    ('canonical_format_id', 'pg_varchar', (), False),
    ('max_height', 'pg_int4', (), True),
    ('membership_revision', 'pg_int8', (), False),
    ('quota_day', 'pg_date', (), False),
    ('state', 'pg_varchar', (), False),
    ('job_id', 'pg_varchar', (), True),
    ('job_id_tombstone', 'pg_varchar', (), True),
    ('accepted_at', 'pg_timestamptz', (), False),
    ('deadline_at', 'pg_timestamptz', (), False),
    ('resolve_deadline_at', 'pg_timestamptz', (), False),
    ('completed_at', 'pg_timestamptz', (), True),
    ('capacity_reserved', 'pg_bool', (), False),
    ('resolve_owner', 'pg_varchar', (), True),
    ('resolve_epoch', 'pg_int8', (), False),
    ('resolve_lease_deadline', 'pg_timestamptz', (), True),
    ('resolve_attempts_used', 'pg_int8', (), False),
    ('resolve_attempts_limit', 'pg_int8', (), False),
    ('resolve_attempt_deadline', 'pg_timestamptz', (), True),
    ('budget_version', 'pg_int4', (), False),
    ('budget_checkpoint_json', 'pg_text', (), False),
    ('budget_checkpoint_at', 'pg_timestamptz', (), False),
    ('error_code', 'pg_varchar', (), True),
), ('id',),
    (('job_id',),),
    ((('job_id',), 'app', 'job', ('id',), 'RESTRICT'), (('user_id',), 'app', 'user', ('id',), 'RESTRICT')),
    ((('state', 'resolve_lease_deadline'), False, 'absent'), (('user_id', 'accepted_at'), False, 'absent')),
    ('downloadoperation.access_snapshot.v1', 'downloadoperation.budget_checkpoint.v1', 'downloadoperation.checkpoint_time.v1', 'downloadoperation.deadline.v1', 'downloadoperation.resolve_budget.v1', 'downloadoperation.resolve_deadline.v1', 'downloadoperation.resolve_lease_pair.v1', 'downloadoperation.state.v1'),
    ())

_P2_QUOTACHARGE = _table('quotacharge', (
    ('operation_id', 'pg_varchar', (), False),
    ('user_id', 'pg_varchar', (), False),
    ('quota_day', 'pg_date', (), False),
    ('delta', 'pg_int8', (), False),
    ('charged_at', 'pg_timestamptz', (), False),
), ('operation_id',),
    (),
    ((('operation_id',), 'app', 'downloadoperation', ('id',), 'RESTRICT'), (('user_id',), 'app', 'user', ('id',), 'RESTRICT')),
    ((('user_id', 'quota_day'), False, 'absent'),),
    ('quotacharge.delta_one.v1',),
    ())

_P2_RESOURCECOUNTER = _table('resourcecounter', (
    ('resource', 'pg_varchar', (), False),
    ('scope', 'pg_varchar', (), False),
    ('used', 'pg_int8', (), False),
), ('resource', 'scope'),
    (),
    (),
    (),
    ('resourcecounter.used_nonnegative.v1',),
    ())

_P2_RESOURCERESERVATION = _table('resourcereservation', (
    ('operation_id', 'pg_varchar', (), False),
    ('resource', 'pg_varchar', (), False),
    ('scope', 'pg_varchar', (), False),
    ('units', 'pg_int8', (), False),
    ('released', 'pg_bool', (), False),
    ('reserved_at', 'pg_timestamptz', (), False),
    ('released_at', 'pg_timestamptz', (), True),
), ('operation_id', 'resource', 'scope'),
    (),
    ((('operation_id',), 'app', 'downloadoperation', ('id',), 'RESTRICT'), (('resource', 'scope'), 'app', 'resourcecounter', ('resource', 'scope'), 'RESTRICT')),
    ((('resource', 'scope', 'released'), False, 'absent'),),
    ('resourcereservation.release_state.v1', 'resourcereservation.units_positive.v1'),
    ())

_P3_BILLINGCHECKOUT = _table('billingcheckout', (
    ('id', 'pg_varchar', (), False),
    ('user_id', 'pg_varchar', (), False),
    ('price_id', 'pg_varchar', (), False),
    ('mode', 'pg_varchar', (), False),
    ('duration_days', 'pg_int4', (), False),
    ('origin', 'pg_varchar', (), False),
    ('customer_id', 'pg_varchar', (), True),
    ('created_at', 'pg_float8', (), False),
    ('stripe_id', 'pg_varchar', (), True),
    ('url', 'pg_varchar', (), True),
    ('expires_at', 'pg_float8', (), False),
    ('state', 'pg_varchar', (), False),
    ('fulfilled', 'pg_bool', (), False),
    ('provider_account_scope', 'pg_varchar', (), True),
    ('livemode', 'pg_bool', (), True),
    ('create_payload', 'pg_text', (), True),
    ('create_payload_sha256', 'pg_varchar', (64,), True),
    ('create_payload_version', 'pg_int4', (), True),
    ('create_started_at', 'pg_timestamptz', (), True),
    ('create_completed_at', 'pg_timestamptz', (), True),
    ('create_result_code', 'pg_varchar', (), True),
    ('reconciliation', 'pg_varchar', (), True),
    ('reconcile_attempts', 'pg_int4', (), False),
    ('reconciliation_started_at', 'pg_timestamptz', (), True),
    ('reconciliation_evidence', 'pg_varchar', (), True),
    ('reconciliation_actor', 'pg_varchar', (), True),
    ('reconciliation_reason', 'pg_varchar', (), True),
    ('revision', 'pg_int8', (), False),
), ('id',),
    (('stripe_id',),),
    ((('user_id',), 'app', 'user', ('id',), 'NO_ACTION'),),
    ((('user_id',), False, 'absent'),),
    ('billingcheckout.reconcile_attempts.v1', 'billingcheckout.reconciliation.v1'),
    ())

_P3_BILLINGEVENT = _table('billingevent', (
    ('id', 'pg_varchar', (), False),
    ('processed_at', 'pg_float8', (), False),
    ('provider_account_scope', 'pg_varchar', (), False),
    ('livemode', 'pg_bool', (), True),
    ('outcome', 'pg_varchar', (), True),
), ('id',),
    (),
    (),
    (),
    ('billingevent.scope_mode.v1',),
    ())

_P3_BILLINGFACT = _table('billingfact', (
    ('id', 'pg_varchar', (), False),
    ('inbox_id', 'pg_varchar', (), True),
    ('user_id', 'pg_varchar', (), True),
    ('checkout_id', 'pg_varchar', (), True),
    ('provider_account_scope', 'pg_varchar', (), False),
    ('livemode', 'pg_bool', (), True),
    ('event_id', 'pg_varchar', (), True),
    ('payment_intent', 'pg_varchar', (), True),
    ('session_id', 'pg_varchar', (), True),
    ('invoice_id', 'pg_varchar', (), True),
    ('charge_id', 'pg_varchar', (), True),
    ('subscription_id', 'pg_varchar', (), True),
    ('provider_status', 'pg_varchar', (), True),
    ('amount_total', 'pg_int8', (), True),
    ('amount_refunded', 'pg_int8', (), True),
    ('currency', 'pg_varchar', (3,), True),
    ('reconciliation', 'pg_varchar', (), False),
    ('observed_at', 'pg_timestamptz', (), False),
), ('id',),
    (('inbox_id',),),
    ((('checkout_id',), 'app', 'billingcheckout', ('id',), 'RESTRICT'), (('inbox_id',), 'app', 'billinginbox', ('id',), 'RESTRICT'), (('user_id',), 'app', 'user', ('id',), 'RESTRICT')),
    ((('checkout_id',), False, 'absent'), (('provider_account_scope', 'livemode', 'payment_intent'), False, 'absent')),
    ('billingfact.amount_refunded.v1', 'billingfact.amount_total.v1', 'billingfact.reconciliation.v1', 'billingfact.scope_mode.v1'),
    ())

_P3_BILLINGINBOX = _table('billinginbox', (
    ('id', 'pg_varchar', (), False),
    ('provider_account_scope', 'pg_varchar', (), False),
    ('livemode', 'pg_bool', (), False),
    ('event_id', 'pg_varchar', (), False),
    ('event_type', 'pg_varchar', (), False),
    ('api_version', 'pg_varchar', (), True),
    ('received_at', 'pg_timestamptz', (), False),
    ('payload_sha256', 'pg_varchar', (64,), False),
    ('canonical_sha256', 'pg_varchar', (64,), False),
    ('canonical_version', 'pg_int4', (), False),
    ('canonical_payload', 'pg_text', (), False),
    ('business_payload', 'pg_text', (), True),
    ('status', 'pg_varchar', (), False),
    ('attempt_count', 'pg_int8', (), False),
    ('attempt_limit', 'pg_int8', (), False),
    ('budget_deadline', 'pg_timestamptz', (), False),
    ('next_run_at', 'pg_timestamptz', (), False),
    ('lease_owner', 'pg_varchar', (), True),
    ('lease_epoch', 'pg_int8', (), False),
    ('lease_deadline', 'pg_timestamptz', (), True),
    ('error_code', 'pg_varchar', (), True),
    ('outcome_reason', 'pg_varchar', (), True),
    ('completed_at', 'pg_timestamptz', (), True),
    ('payload_purged_at', 'pg_timestamptz', (), True),
), ('id',),
    (('provider_account_scope', 'livemode', 'event_id'),),
    (),
    ((('status', 'lease_deadline'), False, 'absent'), (('status', 'next_run_at'), False, 'absent')),
    ('billinginbox.budget.v1', 'billinginbox.budget_deadline.v1', 'billinginbox.canonical_version.v1', 'billinginbox.lease_pair.v1', 'billinginbox.processing_lease.v1', 'billinginbox.status.v1'),
    ())

_P4_BILLINGRECONCILIATIONAUDIT = _table('billingreconciliationaudit', (
    ('id', 'pg_varchar', (36,), False),
    ('task_id', 'pg_varchar', (), False),
    ('seq', 'pg_int8', (), False),
    ('event_kind', 'pg_varchar', (16,), False),
    ('get_ordinal', 'pg_int4', (), True),
    ('recorded_at', 'pg_timestamptz', (), False),
    ('actor_ref', 'pg_varchar', (63,), False),
    ('reason_code', 'pg_varchar', (32,), False),
    ('evidence_ref', 'pg_varchar', (123,), False),
    ('projection_version', 'pg_int4', (), False),
    ('projection_json', 'pg_text', (), False),
    ('projection_sha256', 'pg_varchar', (64,), False),
), ('id',),
    (('task_id', 'event_kind', 'get_ordinal'), ('task_id', 'seq')),
    ((('task_id',), 'app', 'billingreconciliationtask', ('id',), 'RESTRICT'),),
    ((('task_id', 'event_kind'), True, 'get_ordinal_is_null_v1'),),
    ('billingreconciliationaudit.audit_context.v1', 'billingreconciliationaudit.event_ordinal.v1', 'billingreconciliationaudit.projection_json.v1', 'billingreconciliationaudit.projection_sha256.v1', 'billingreconciliationaudit.reason.v1', 'billingreconciliationaudit.sequence_version.v1'),
    (('trg_b3b_audit_row.v1', 'b3b_reject_mutation.v1', ('UPDATE', 'DELETE'), 'ROW'), ('trg_b3b_audit_truncate.v1', 'b3b_reject_mutation.v1', ('TRUNCATE',), 'STATEMENT')))

_P4_BILLINGRECONCILIATIONTASK = _table('billingreconciliationtask', (
    ('id', 'pg_varchar', (36,), False),
    ('checkout_id', 'pg_varchar', (), False),
    ('user_id', 'pg_varchar', (), False),
    ('provider_account_scope', 'pg_varchar', (128,), False),
    ('livemode', 'pg_bool', (), False),
    ('actor_ref', 'pg_varchar', (63,), False),
    ('reason_code', 'pg_varchar', (32,), False),
    ('evidence_ref', 'pg_varchar', (123,), False),
    ('input_version', 'pg_int4', (), False),
    ('input_sha256', 'pg_varchar', (64,), False),
    ('query_json', 'pg_text', (), False),
    ('policy_json', 'pg_text', (), False),
    ('initial_checkout_revision', 'pg_int8', (), False),
    ('expected_checkout_revision', 'pg_int8', (), False),
    ('membership_revision', 'pg_int8', (), False),
    ('owner_ref', 'pg_varchar', (128,), False),
    ('started_at', 'pg_timestamptz', (), False),
    ('budget_deadline', 'pg_timestamptz', (), False),
    ('get_attempts', 'pg_int8', (), False),
    ('get_limit', 'pg_int4', (), False),
    ('budget_version', 'pg_int4', (), False),
    ('status', 'pg_varchar', (16,), False),
    ('outcome_reason', 'pg_varchar', (64,), True),
    ('completed_at', 'pg_timestamptz', (), True),
    ('next_audit_seq', 'pg_int8', (), False),
    ('revision', 'pg_int8', (), False),
), ('id',),
    (('checkout_id',),),
    ((('checkout_id',), 'app', 'billingcheckout', ('id',), 'RESTRICT'), (('user_id',), 'app', 'user', ('id',), 'RESTRICT')),
    ((('status', 'budget_deadline'), False, 'absent'), (('user_id',), False, 'absent')),
    ('billingreconciliationtask.audit_context.v1', 'billingreconciliationtask.deadline.v1', 'billingreconciliationtask.get_budget.v1', 'billingreconciliationtask.input_sha256.v1', 'billingreconciliationtask.policy_json.v1', 'billingreconciliationtask.query_json.v1', 'billingreconciliationtask.reason.v1', 'billingreconciliationtask.revisions.v1', 'billingreconciliationtask.scope.v1', 'billingreconciliationtask.terminal.v1', 'billingreconciliationtask.versions_limits.v1'),
    (('trg_b3b_task_delete.v1', 'b3b_reject_mutation.v1', ('DELETE',), 'ROW'), ('trg_b3b_task_truncate.v1', 'b3b_reject_mutation.v1', ('TRUNCATE',), 'STATEMENT'), ('trg_b3b_task_update.v1', 'b3b_task_update_guard.v1', ('UPDATE',), 'ROW')))

@dataclass(frozen=True, slots=True, init=False, repr=False)
class SchemaProfile:
    """Expected match only; not a source/export/driver/ACL capability."""
    profile_id: str
    descriptor: SchemaDescriptor
    allowed_tags: tuple[tuple[frozenset[str], ...], ...]
    policy_ids: tuple[str, ...]

    @_boundary
    def __init__(self, *args, **kwargs):
        names = ('profile_id', 'descriptor', 'allowed_tags', 'policy_ids')
        _require(type(self) is SchemaProfile and len(args) <= 4 and len(args) + len(kwargs) == 4)
        _require(all(type(k) is str and k in names[len(args):] for k in kwargs))
        values = tuple(args[i] if i < len(args) else kwargs[name] for i, name in enumerate(names))
        profile_id, descriptor, allowed_tags, policy_ids = values
        _require(type(profile_id) is str and profile_id in KNOWN_PROFILE_IDS)
        _schema_bytes(descriptor)
        _require(type(allowed_tags) is tuple and len(allowed_tags) == len(descriptor.tables))
        for table, tags in zip(descriptor.tables, allowed_tags):
            _require(type(tags) is tuple and len(tags) == len(table.columns))
            for column, tagset in zip(table.columns, tags):
                _require(type(tagset) is frozenset and len(tagset) <= 5)
                _require(all(type(t) is str for t in tagset))
                _require(tagset == _tags(column, descriptor.dialect))
        _require(type(policy_ids) is tuple and len(policy_ids) <= 4)
        _require(all(type(p) is str for p in policy_ids))
        _require(policy_ids == _policies(descriptor.dialect))
        for name, value in zip(names, values):
            object.__setattr__(self, name, value)


KNOWN_PROFILE_IDS = frozenset({
    'legacy_sqlite9_v1', 'sqlite_models17_v1', 'pg_b1_0001_v1',
    'pg_b1b_0002_v1', 'pg_b1b_0003_v1', 'pg_b3b_0004_v1',
})
_PG_TAGS = MappingProxyType({'pg_varchar': 's', 'pg_text': 's', 'pg_int4': 'i',
    'pg_int8': 'i', 'pg_float8': 'f', 'pg_bool': 'b', 'pg_date': 'date', 'pg_timestamptz': 'dt'})


def _tags(column, dialect):
    tags = frozenset({'s', 'i', 'f', 'x'}) if dialect == 'sqlite' else frozenset({_PG_TAGS[column.physical_type.kind]})
    return tags | frozenset({'n'}) if column.nullable else tags


def _policies(dialect):
    if dialect == 'sqlite':
        return ('acl_not_assessed_v1', 'legacy_naive_utc_requires_import_policy_v1',
                'sqlite_temporal_text_uninterpreted_v1', 'sqlite_asc_nulls_first_v1')
    return ('acl_not_assessed_v1', 'pg_builtin_utc_decode_requires_e2_v1', 'pg_asc_nulls_last_v1')


def _profile(profile_id, descriptor):
    return SchemaProfile(profile_id, descriptor,
        tuple(tuple(_tags(c, descriptor.dialect) for c in t.columns) for t in descriptor.tables),
        _policies(descriptor.dialect))


SOURCE_PROFILES: Mapping[str, SchemaProfile] = MappingProxyType({
    'legacy_sqlite9_v1': _profile('legacy_sqlite9_v1', SchemaDescriptor(1, 'sqlite', 'main', (), (
        _S9_BILLINGCHECKOUT,
        _S9_BILLINGEVENT,
        _S9_BILLINGPAYMENT,
        _S9_DOWNLOADACCESS,
        _S9_DOWNLOADIDEMPOTENCY,
        _S9_JOB,
        _S9_MEMBERSHIP,
        _S9_QUOTA,
        _S9_USER,
    ), (), (), ())),
    'sqlite_models17_v1': _profile('sqlite_models17_v1', SchemaDescriptor(1, 'sqlite', 'main', (), (
        _S17_BILLINGCHECKOUT,
        _S17_BILLINGEVENT,
        _S17_BILLINGFACT,
        _S17_BILLINGINBOX,
        _S9_BILLINGPAYMENT,
        _S17_BILLINGRECONCILIATIONAUDIT,
        _S17_BILLINGRECONCILIATIONTASK,
        _S9_DOWNLOADACCESS,
        _S17_DOWNLOADIDEMPOTENCY,
        _S17_DOWNLOADOPERATION,
        _S17_JOB,
        _S9_MEMBERSHIP,
        _S9_QUOTA,
        _S17_QUOTACHARGE,
        _S17_RESOURCECOUNTER,
        _S17_RESOURCERESERVATION,
        _S9_USER,
    ), (), (), ())),
    'pg_b1_0001_v1': _profile('pg_b1_0001_v1', SchemaDescriptor(1, 'pg', 'app', ('b1_0001',), (
        _P1_BILLINGCHECKOUT,
        _P1_BILLINGEVENT,
        _P1_BILLINGPAYMENT,
        _P1_DOWNLOADACCESS,
        _P1_DOWNLOADIDEMPOTENCY,
        _P1_JOB,
        _P1_MEMBERSHIP,
        _P1_QUOTA,
        _P1_USER,
    ), (_P1_ALEMBIC_VERSION,), (), ())),
    'pg_b1b_0002_v1': _profile('pg_b1b_0002_v1', SchemaDescriptor(1, 'pg', 'app', ('b1b_0002',), (
        _P1_BILLINGCHECKOUT,
        _P1_BILLINGEVENT,
        _P1_BILLINGPAYMENT,
        _P1_DOWNLOADACCESS,
        _P2_DOWNLOADIDEMPOTENCY,
        _P2_DOWNLOADOPERATION,
        _P1_JOB,
        _P1_MEMBERSHIP,
        _P1_QUOTA,
        _P2_QUOTACHARGE,
        _P2_RESOURCECOUNTER,
        _P2_RESOURCERESERVATION,
        _P1_USER,
    ), (_P1_ALEMBIC_VERSION,), (), ())),
    'pg_b1b_0003_v1': _profile('pg_b1b_0003_v1', SchemaDescriptor(1, 'pg', 'app', ('b1b_0003',), (
        _P3_BILLINGCHECKOUT,
        _P3_BILLINGEVENT,
        _P3_BILLINGFACT,
        _P3_BILLINGINBOX,
        _P1_BILLINGPAYMENT,
        _P1_DOWNLOADACCESS,
        _P2_DOWNLOADIDEMPOTENCY,
        _P2_DOWNLOADOPERATION,
        _P1_JOB,
        _P1_MEMBERSHIP,
        _P1_QUOTA,
        _P2_QUOTACHARGE,
        _P2_RESOURCECOUNTER,
        _P2_RESOURCERESERVATION,
        _P1_USER,
    ), (_P1_ALEMBIC_VERSION,), (), ())),
    'pg_b3b_0004_v1': _profile('pg_b3b_0004_v1', SchemaDescriptor(1, 'pg', 'app', ('b3b_0004',), (
        _P3_BILLINGCHECKOUT,
        _P3_BILLINGEVENT,
        _P3_BILLINGFACT,
        _P3_BILLINGINBOX,
        _P1_BILLINGPAYMENT,
        _P4_BILLINGRECONCILIATIONAUDIT,
        _P4_BILLINGRECONCILIATIONTASK,
        _P1_DOWNLOADACCESS,
        _P2_DOWNLOADIDEMPOTENCY,
        _P2_DOWNLOADOPERATION,
        _P1_JOB,
        _P1_MEMBERSHIP,
        _P1_QUOTA,
        _P2_QUOTACHARGE,
        _P2_RESOURCECOUNTER,
        _P2_RESOURCERESERVATION,
        _P1_USER,
    ), (_P1_ALEMBIC_VERSION,), ('b3b_reject_mutation.v1', 'b3b_task_update_guard.v1'), ())),
})


_DECLARATIONS = tuple((_schema_bytes(p.descriptor), p) for p in SOURCE_PROFILES.values())


@_boundary
def require_source_profile(*args, **kwargs) -> SchemaProfile:
    """Match exactly one complete declaration. Never authenticates a DB source."""
    descriptor = _argument(args, kwargs)
    candidate = _schema_bytes(descriptor)
    matches = tuple(profile for expected, profile in _DECLARATIONS if expected == candidate)
    if len(matches) == 1:
        return matches[0]
    _raise_safe('source_profile_unsupported')
