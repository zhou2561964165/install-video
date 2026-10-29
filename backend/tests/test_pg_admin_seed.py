"""Admin M1 Task 12: synthetic seed for local integration (never real data) on nonce-owned PG."""
import os

import pytest
from sqlalchemy import text

from admin_pg_helpers import make_user
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


def test_seed_refuses_non_empty_db(case):
    from app.admin import seed_synthetic
    make_user(case, 'real@example.invalid', grant=False)
    with pytest.raises(seed_synthetic.SeedRefused):
        seed_synthetic.seed(case.migration)


def test_seed_refuses_a_database_not_owned_by_the_test_runner(case, monkeypatch):
    from app.admin import seed_synthetic
    monkeypatch.setattr(seed_synthetic, '_database_name', lambda connection: 'install_video')
    with pytest.raises(seed_synthetic.SeedRefused):
        seed_synthetic.seed(case.migration)


def test_seed_emails_all_example_invalid_and_admin_can_log_in(case):
    from app.admin import seed_synthetic
    from app.services.auth import verify_password
    counts = seed_synthetic.seed(case.migration)
    assert counts['users'] >= 6 and counts['jobs'] >= 6
    with case.migration.connect() as connection:
        emails = connection.execute(text('SELECT email FROM app."user"')).scalars().all()
        stored = connection.scalar(text('SELECT password_hash FROM app."user" WHERE email=:e'),
                                   {'e': seed_synthetic.ADMIN_EMAIL})
        grant = connection.scalar(text("SELECT role FROM app.admingrant WHERE active AND user_id='syn-admin'"))
    assert emails and all(email.endswith('@example.invalid') for email in emails)
    assert verify_password(seed_synthetic.ADMIN_PASSWORD, stored) and grant == 'admin'


def test_seed_covers_paid_unfulfilled_and_ambiguous_payment(case):
    from app.admin import seed_synthetic
    from app.services import admin_queries
    seed_synthetic.seed(case.migration)
    with admin_queries.read_snapshot(case.application) as (connection, as_of):
        paid_unfulfilled = connection.scalar(text(
            "SELECT count(*) FROM app.billingcheckout WHERE state='paid' AND NOT fulfilled"))
        states = {pi: admin_queries.payment_facts(connection, pi, user)[0] for pi, user in connection.execute(
            text('SELECT payment_intent, user_id FROM app.billingpayment')).all()}
        internal = set(connection.execute(text('SELECT DISTINCT internal_state FROM app.job')).scalars())
    assert paid_unfulfilled >= 1
    assert {'available', 'ambiguous', 'none'} <= set(states.values())
    assert None in internal and {'queued', 'failed', 'succeeded', 'legacy_hold'} <= internal


def test_seed_covers_support_tickets_and_a_viewer(case):
    from app.admin import seed_synthetic
    from app.services import admin_queries, admin_support
    from app.admin.config import AdminSettings
    seed_synthetic.seed(case.migration)
    query = admin_queries.parse_list_query(admin_queries.RESOURCES['adminListSupportTickets'], {}, AdminSettings())
    with admin_queries.read_snapshot(case.application) as (connection, as_of):
        items, total = admin_support.list_tickets(connection, as_of, query)
        stripe_id = connection.scalar(text("SELECT stripe_id FROM app.billingcheckout WHERE id='co-paid-unfulfilled'"))
        viewer = connection.scalar(text("SELECT role FROM app.admingrant WHERE active AND user_id='syn-viewer'"))
    assert total >= 4 and [item['priority'] for item in items] == ['priority', 'priority', 'normal', 'normal']
    paid = next(item for item in items if item['checkout_id'] == 'co-paid-unfulfilled')
    assert paid['id'] == seed_synthetic.REISSUE_TICKET and paid['state'] == 'open' and stripe_id == seed_synthetic.REISSUE_SESSION
    assert {item['state'] for item in items} >= {'open', 'resolved'} and viewer == 'viewer'
