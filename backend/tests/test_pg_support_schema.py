"""Support tickets Task 1: t1_0015_support — tickets, payment checks, re-issue ledger (nonce-owned PG)."""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from test_pg_job_repository import case, db  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
TABLES = ('supportticket', 'supportpaymentcheck', 'membershipreissue')
EXPECTED = {'supportticket': {'SELECT', 'INSERT', 'UPDATE'}, 'supportpaymentcheck': {'SELECT', 'INSERT'},
            'membershipreissue': {'SELECT', 'INSERT'}}


def seed(case):
    db(case, "INSERT INTO app.\"user\" (id,email,password_hash,created_at) VALUES ('u1','u1@example.invalid','x',now())")
    db(case, "INSERT INTO app.billingcheckout (id,user_id,price_id,mode,duration_days,origin,created_at,expires_at,state,"
             "fulfilled,reconcile_attempts,revision) VALUES ('co1','u1','price','payment',30,'https://s.invalid',"
             "extract(epoch from now()),0,'open',false,0,0)")


def ticket(case, ticket_id='t1', category='membership_not_credited', checkout='co1', state='open', resolved=False):
    db(case, 'INSERT INTO app.supportticket (id,user_id,category,checkout_id,priority,state,created_at,resolved_at,revision) '
             f"VALUES (:i,'u1',:c,:co,'priority',:s,now(),{'now()' if resolved else 'NULL'},0)",
       i=ticket_id, c=category, co=checkout, s=state)


def test_head_is_t1_0015():
    from alembic.script import ScriptDirectory
    from app import db as app_db
    script = ScriptDirectory.from_config(app_db.migration_config())
    assert script.get_revision('t1_0015').down_revision == 'm1_0014'
    assert script.get_heads() == ['mc_0016']
    assert script.get_revision('mc_0016').down_revision == 't1_0015'


def test_ticket_category_checkout_pairing(case):
    seed(case)
    with pytest.raises(IntegrityError):
        ticket(case, 'a', checkout=None)
    with pytest.raises(IntegrityError):
        ticket(case, 'b', category='other')
    with pytest.raises(IntegrityError):
        ticket(case, 'c', category='wishes', checkout=None)
    ticket(case, 'ok')
    ticket(case, 'other', category='other', checkout=None)


def test_state_matches_resolved_at(case):
    seed(case)
    with pytest.raises(IntegrityError):
        ticket(case, 'a', state='resolved')  # resolved without resolved_at
    with pytest.raises(IntegrityError):
        ticket(case, 'b', resolved=True)  # open with resolved_at


def test_one_open_membership_ticket_per_checkout(case):
    seed(case)
    ticket(case, 't1')
    with pytest.raises(IntegrityError):
        ticket(case, 't2')
    db(case, "UPDATE app.supportticket SET state='rejected', resolution='rejected', resolved_at=now() WHERE id='t1'")
    ticket(case, 't3')  # a closed ticket does not block a new one


def test_reissue_ledger_unique_per_checkout(case):
    seed(case)
    ticket(case)
    row = ("INSERT INTO app.membershipreissue (checkout_id,ticket_id,actor_user_id,payment_intent,granted_days,"
           "expires_before,expires_after,created_at,idempotency_key) VALUES ('co1','t1','u1','pi_1',30,0,2592000,now(),'k1')")
    db(case, row)
    with pytest.raises(IntegrityError):
        db(case, row)


def test_runtime_privileges(case):
    with case.migration.connect() as connection:
        for table, expected in EXPECTED.items():
            granted = {p for p in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
                       if connection.scalar(text("SELECT has_table_privilege('pv_app',:t,:p)"), {'t': 'app.' + table, 'p': p})}
            assert granted == expected, table


def test_sqlite_create_all_includes_support_tables():
    from sqlmodel import SQLModel
    import app.models  # noqa: F401
    assert set(TABLES) <= set(SQLModel.metadata.tables)
