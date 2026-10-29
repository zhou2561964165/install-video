"""Isolated PG helpers; no real account, Stripe transport, .env or business DB."""
from types import SimpleNamespace
import copy
import socket
from threading import local

import pytest
from sqlalchemy import delete
from sqlmodel import Session

from b2_pg_helpers import engine
from app.models import BillingInbox, BillingFact, BillingEvent, BillingPayment, BillingCheckout, Membership, User
from app.services.billing_pg import BillingConfiguration
from app.services.billing_projection import encode

CFG = BillingConfiguration('b3-operator', False, 10)


def clear(instance):
    with Session(instance) as session:
        for model, column in ((BillingFact, BillingFact.event_id), (BillingInbox, BillingInbox.event_id),
            (BillingEvent, BillingEvent.id), (BillingPayment, BillingPayment.payment_intent),
            (BillingCheckout, BillingCheckout.user_id), (Membership, Membership.user_id), (User, User.id)):
            session.execute(delete(model).where(column.startswith('b3-')))
        session.commit()


@pytest.fixture
def pg(monkeypatch):
    original = socket.socket.connect
    original_pair = socket.socketpair
    context = local()
    def internal_pair(*args, **kwargs):
        # Only the stdlib's own socketpair implementation may connect its
        # temporary loopback pair; arbitrary local service ports remain blocked.
        context.socketpair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            context.socketpair = False
    def guard(sock, address):
        if (isinstance(address, tuple) and address[0] in {'127.0.0.1','::1'}
                and (address[1] == 62328 or getattr(context,'socketpair',False))):
            return original(sock, address)
        raise AssertionError('B3 external socket denied')
    monkeypatch.setattr(socket, 'socketpair', internal_pair)
    monkeypatch.setattr(socket.socket, 'connect', guard)
    instance = engine()
    try:
        yield instance
    finally:
        clear(instance)
        instance.dispose()


def seed(instance, *, mode='payment', fulfilled=False):
    with Session(instance, expire_on_commit=False) as session:
        session.add(User(id='b3-user', email='b3-user@synthetic.invalid', password_hash='no-login'))
        session.flush()
        session.add(Membership(user_id='b3-user', active_checkout_id='b3-checkout'))
        row = BillingCheckout(id='b3-checkout', user_id='b3-user', price_id='b3-price', mode=mode,
            duration_days=30, origin='https://synthetic.invalid', provider_account_scope=CFG.scope,
            livemode=False, stripe_id='b3-session', fulfilled=fulfilled)
        session.add(row)
        session.commit()
        return row


def event(row=None, *, eid='b3-event', kind='checkout.session.completed', **changes):
    obj = {'id': 'b3-session', 'metadata': {'checkout_id': 'b3-checkout'}, 'mode': 'payment',
        'status': 'complete', 'payment_status': 'paid', 'customer': 'b3-customer',
        'client_reference_id': 'b3-user', 'payment_intent': 'b3-payment', 'subscription': None,
        'amount_total': 990, 'currency': 'cny'}
    if row:
        obj.update(id=row.stripe_id, mode=row.mode, metadata={'checkout_id':row.id})
    obj.update(changes)
    return {'id': eid, 'type': kind, 'livemode': False, 'api_version': '2026-01-28', 'data': {'object': obj}}


class Provider:
    def __init__(self, event_value):
        self.calls, self.callback = [], None
        self.obj = copy.deepcopy(event_value['data']['object'])
        self.obj.update(livemode=False, line_items={'data': [{'price': {'id':'b3-price'}, 'quantity':1}]})
        self.sub = None
        self.charge = {'id':'b3-charge','livemode':False,'payment_intent':'b3-payment'}
        self.v1 = SimpleNamespace(checkout=SimpleNamespace(sessions=SimpleNamespace(retrieve=self.session_get,
            create=self.session_create)), subscriptions=SimpleNamespace(retrieve=self.subscription_get),
            charges=SimpleNamespace(retrieve=self.charge_get))
    def __call__(self):
        return self
    def session_get(self, identity, params=None):
        self.calls.append(('session',identity,params))
        if self.callback:
            self.callback()
        return copy.deepcopy(self.obj)
    def session_create(self, params, options):
        self.calls.append(('create',copy.deepcopy(params),copy.deepcopy(options)))
        return dict(self.obj, id='b3-created', client_reference_id=params['client_reference_id'],
            metadata=params['metadata'], mode=params['mode'], status='open',
            url='https://checkout.stripe.com/synthetic', expires_at=9999999999)
    def subscription_get(self, identity, params=None):
        self.calls.append(('subscription',identity,params))
        return copy.deepcopy(self.sub)
    def charge_get(self, identity, params=None):
        self.calls.append(('charge',identity,params))
        return copy.deepcopy(self.charge)


def receipt(instance, value, cfg=CFG):
    from app.services.billing_inbox import receive
    return receive(instance, value, encode(value).encode(), cfg)
