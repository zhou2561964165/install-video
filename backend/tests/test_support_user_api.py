"""Support tickets Task 3: user-side API on the business app (SQLite dev database)."""
from collections import defaultdict
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import engine
from app.main import app
from app.models import BillingCheckout, Membership, User
from app.services.auth import create_token

DAY = 86400


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr('app.main._window', defaultdict(list))
    return TestClient(app)


def make_user(vip=False):
    with Session(engine) as session:
        user = User(email=f'{uuid4()}@example.invalid', password_hash='unused')
        session.add(user)
        session.commit()
        session.refresh(user)
        if vip:
            session.add(Membership(user_id=user.id, status='active', expires_at=time.time() + 10 * DAY))
            session.commit()
        return user.id, {'Authorization': 'Bearer ' + create_token(user.id)}


def make_checkout(user_id, *, state='open', fulfilled=False, mode='payment', age_days=1):
    with Session(engine) as session:
        checkout = BillingCheckout(user_id=user_id, price_id='price_test', mode=mode, duration_days=30,
                                   origin='http://localhost', created_at=time.time() - age_days * DAY, state=state,
                                   fulfilled=fulfilled)
        session.add(checkout)
        session.commit()
        return checkout.id


def submit(client, headers, category='other', note=None, checkout_id=None):
    body = {'category': category}
    if note is not None:
        body['note'] = note
    if checkout_id is not None:
        body['checkout_id'] = checkout_id
    return client.post('/api/support/tickets', json=body, headers=headers)


def test_requires_login(client):
    assert client.get('/api/support/meta').status_code == 401
    assert client.post('/api/support/tickets', json={'category': 'other'}).status_code == 401
    assert client.get('/api/support/tickets').status_code == 401


def test_meta_lists_only_own_eligible_checkouts(client):
    user, headers = make_user()
    other, _ = make_user()
    eligible = make_checkout(user)
    expired = make_checkout(user, state='expired')
    make_checkout(user, fulfilled=True)
    make_checkout(user, state='failed')
    make_checkout(user, age_days=91)
    make_checkout(user, mode='subscription')
    make_checkout(other)
    meta = client.get('/api/support/meta', headers=headers).json()
    assert [c['id'] for c in meta['categories']] == ['membership_not_credited', 'download_failing', 'login_problem', 'other']
    assert {c['checkout_id'] for c in meta['checkouts']} == {eligible, expired}
    item = next(c for c in meta['checkouts'] if c['checkout_id'] == eligible)
    assert item['label'] == eligible[-8:] and item['state'] == 'open' and item['created_at'].endswith('Z')


def test_membership_ticket_requires_eligible_checkout(client):
    user, headers = make_user()
    response = submit(client, headers, 'membership_not_credited')
    assert response.status_code == 422 and response.json()['detail']['error_type'] == 'checkout_required'
    fulfilled = make_checkout(user, fulfilled=True)
    response = submit(client, headers, 'membership_not_credited', checkout_id=fulfilled)
    assert response.status_code == 422 and response.json()['detail']['error_type'] == 'checkout_not_eligible'
    assert submit(client, headers, 'other', checkout_id=make_checkout(user)).status_code == 422  # only for that category
    assert submit(client, headers, 'wishes').json()['detail']['error_type'] == 'invalid_category'


def test_empty_checkout_id_is_treated_as_absent(client):
    _, headers = make_user()
    response = submit(client, headers, 'other', checkout_id='')
    assert response.status_code == 200


def test_cannot_submit_for_others_checkout(client):
    _, headers = make_user()
    other, _ = make_user()
    theirs = submit(client, headers, 'membership_not_credited', checkout_id=make_checkout(other))
    missing = submit(client, headers, 'membership_not_credited', checkout_id='no-such-checkout')
    assert theirs.status_code == missing.status_code == 422
    assert theirs.json()['detail'] == missing.json()['detail']


def test_priority_snapshot(client):
    from app.models_support import SupportTicket
    vip, vip_headers = make_user(vip=True)
    plain, plain_headers = make_user()
    ids = [submit(client, vip_headers, 'other').json()['id'],
           submit(client, plain_headers, 'membership_not_credited', checkout_id=make_checkout(plain)).json()['id'],
           submit(client, plain_headers, 'download_failing').json()['id']]
    with Session(engine) as session:
        assert [session.get(SupportTicket, i).priority for i in ids] == ['priority', 'priority', 'normal']


def test_open_limit_and_duplicate_checkout(client):
    user, headers = make_user()
    checkout = make_checkout(user)
    assert submit(client, headers, 'membership_not_credited', checkout_id=checkout).status_code == 200
    duplicate = submit(client, headers, 'membership_not_credited', checkout_id=checkout)
    assert duplicate.status_code == 422 and duplicate.json()['detail']['error_type'] == 'ticket_exists'
    for _ in range(4):
        assert submit(client, headers).status_code == 200
    blocked = submit(client, headers)
    assert blocked.status_code == 422 and blocked.json()['detail']['error_type'] == 'too_many_open'


def test_duplicate_appeal_race_is_ticket_exists(client, monkeypatch):
    user, headers = make_user()
    checkout = make_checkout(user)
    assert submit(client, headers, 'membership_not_credited', checkout_id=checkout).status_code == 200
    # The other request passed the pre-check before this one committed.
    monkeypatch.setattr('app.services.support_tickets._has_open_ticket', lambda session, checkout_id: False)
    raced = submit(client, headers, 'membership_not_credited', checkout_id=checkout)
    assert raced.status_code == 422 and raced.json()['detail']['error_type'] == 'ticket_exists'


def test_submit_rate_limited(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'support_max_open_tickets', 50)
    _, headers = make_user()
    codes = [submit(client, headers).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_note_stored_as_plain_text(client):
    _, headers = make_user()
    note = '<script>alert(1)</script> 付款了但没会员'
    assert submit(client, headers, note=note).status_code == 200
    assert client.get('/api/support/tickets', headers=headers).json()['items'][0]['user_note'] == note


def test_note_length_trimmed_limit(client):
    _, headers = make_user()
    assert submit(client, headers, note='  ' + '字' * 500 + '  ').status_code == 200
    response = submit(client, headers, note='字' * 501)
    assert response.status_code == 422 and response.json()['detail']['error_type'] == 'note_too_long'


def test_list_shows_reply_text_not_internal_fields(client):
    from app.models_support import SupportTicket
    user, headers = make_user()
    ticket_id = submit(client, headers, 'download_failing', note='一直失败').json()['id']
    with Session(engine) as session:
        ticket = session.get(SupportTicket, ticket_id)
        ticket.state, ticket.resolution, ticket.reply_template = 'resolved', 'replied', 'download_help'
        ticket.reply_note, ticket.resolved_by = '换 720p 试试', 'admin-user'
        from datetime import datetime, timezone
        ticket.resolved_at = datetime.now(timezone.utc)
        session.add(ticket)
        session.commit()
    item = client.get('/api/support/tickets', headers=headers).json()['items'][0]
    assert item['reply_text'] == '已收到，请尝试重新解析链接或更换清晰度；若仍失败请再次反馈'
    assert item['reply_note'] == '换 720p 试试' and item['state'] == 'resolved' and item['category_label'] == '下载一直失败'
    assert 'resolved_by' not in item and 'priority' not in item and 'user_id' not in item
