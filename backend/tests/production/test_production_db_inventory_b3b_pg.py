"""B3b inventory in disposable owned databases; Root schedules PG lifecycle.

No old pv_verify fixture, DELETE/TRUNCATE cleanup, credentials, or provider calls.
"""
from datetime import timedelta
import json
import re

import sqlalchemy as sa
from sqlmodel import Session

import pytest

from b3b_pg_helpers import guarded_sockets, pg  # noqa: F401


@pytest.fixture
def schema_pg(guarded_sockets):
    # This suite inventories the B3b-stage schema exactly; later heads (C1+) have their own suites.
    import os
    from b3b_pg_helpers import isolated_database
    if not os.environ.get('B3B_PG_CONTROL'):
        pytest.skip('Explicit B3B_PG_CONTROL opt-in required')
    with isolated_database(target='b3b_0004') as case:
        yield case
from tools import production_db_inventory as inv

SECRET = 'B6_B3B_SYNTHETIC_PRIVATE'


def seed(engine):
    from app.models import BillingCheckout, BillingReconciliationTask, BillingReconciliationAudit, User
    identifiers = []
    with Session(engine) as session:
        now = session.scalar(sa.text('SELECT clock_timestamp()'))
        user_id = SECRET + '_user_id'
        session.add(User(id=user_id, email=SECRET+'@synthetic.invalid', password_hash=SECRET))
        session.flush()
        for index, status in enumerate(('running', 'verified', 'needs_review')):
            checkout_id = SECRET + '_checkout_' + str(index)
            task_id = '00000000-0000-4000-8000-00000000010' + str(index)
            audit_id = '00000000-0000-4000-8000-00000000020' + str(index)
            identifiers.extend((checkout_id, task_id, audit_id))
            session.add(BillingCheckout(id=checkout_id, user_id=user_id, price_id=SECRET, mode='payment',
                duration_days=30, origin=SECRET))
            session.flush()
            session.add(BillingReconciliationTask(id=task_id, checkout_id=checkout_id, user_id=user_id,
                provider_account_scope=SECRET, livemode=False, actor_ref='op:'+SECRET,
                reason_code='unknown_create', evidence_ref='ev:'+SECRET, input_sha256='a'*64,
                query_json=json.dumps({'private': SECRET}), policy_json=json.dumps({'private': SECRET}),
                initial_checkout_revision=0, expected_checkout_revision=0, membership_revision=0,
                owner_ref=SECRET, started_at=now, budget_deadline=now+timedelta(seconds=120),
                status=status, completed_at=None if status == 'running' else now))
            session.flush()
            session.add(BillingReconciliationAudit(id=audit_id, task_id=task_id, seq=1,
                event_kind='task_started', recorded_at=now, actor_ref='op:'+SECRET,
                reason_code='unknown_create', evidence_ref='ev:'+SECRET,
                projection_json=json.dumps({'private': SECRET}), projection_sha256='b'*64))
        session.commit()
    return identifiers


def test_b3b_schema_only_exact_groups_no_business_select(pg, tmp_path):
    statements = []
    with pg.connect() as con:
        sa.event.listen(con, 'before_cursor_execute', lambda c, cur, s, p, ctx, many: statements.append(s))
        report = inv.inventory_database(con, schema_only=True, output=tmp_path/'schema.json').to_dict()
        assert not con.in_transaction() and not con.closed
    assert report['version_heads'] == ['b3b_0004']
    assert report['known_business_table_count'] == 17 and report['known_table_count'] == 18
    assert report['known_business_table_counts'] == {'legacy': 9, 'protocol': 6, 'reconciliation': 2}
    assert report['missing_reconciliation_tables'] == [] and report['unknown_table_count'] == 0
    assert report['aggregates'] == {} and len(report['schema']) == 18
    for table in inv.RECONCILIATION:
        value = report['schema'][table]
        assert not value['missing_columns'] and not value['missing_unique'] and not value['missing_foreign_keys']
        assert value['unknown_column_count'] == 0
        assert value['check_expressions'] == 'redacted'
    reads = [s for s in statements if re.search(r'\b(?:FROM|JOIN)\s+app\.', s, re.I)]
    assert reads and all('app.alembic_version' in s for s in reads)


def test_b3b_synthetic_aggregates_and_redaction(pg, tmp_path):
    identifiers = seed(pg)
    output = tmp_path/'aggregates.json'
    statements = []
    with pg.connect() as con:
        sa.event.listen(con, 'before_cursor_execute', lambda c, cur, s, p, ctx, many: statements.append(s))
        report = inv.inventory_database(con, schema_only=False, output=output).to_dict()
        assert not con.in_transaction()
    text = output.read_text()
    assert SECRET not in text and all(value not in text for value in identifiers)
    assert 'unknown_create' not in text and 'a'*64 not in text and 'b'*64 not in text
    task = report['aggregates']['billingreconciliationtask']
    audit = report['aggregates']['billingreconciliationaudit']
    assert task['row_count'] == audit['row_count'] == 3
    assert task['status_counts'] == {'running': 1, 'verified': 1, 'needs_review': 1}
    assert task['status_unknown_count'] == audit['event_kind_unknown_count'] == 0
    assert audit['event_kind_counts'] == {'task_started': 3, 'get_reserved': 0, 'get_observed': 0, 'task_finished': 0}
    for item in (task, audit):
        assert all(value == 0 for value in item['negative_counts'].values())
        assert all(value == 0 for value in item['invalid_time_counts'].values())
        assert all(value['count'] == 0 for value in item['duplicate_groups'] + item['orphan_counts'])
    aggregate_sql = [s for s in statements if s.startswith('SELECT count(')]
    assert 100 < len(aggregate_sql) <= inv.MAX_QUERIES == 800
    business_reads = [s for s in statements if re.search(r'\b(?:FROM|JOIN)\s+app\.', s, re.I)]
    assert all(s.startswith('SELECT count(') or 'app.alembic_version' in s for s in business_reads)
