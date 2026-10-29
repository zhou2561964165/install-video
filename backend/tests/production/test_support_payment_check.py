"""Support tickets Task 5: verifying a paid Checkout with the payment provider (offline, fake Stripe payloads)."""
import inspect

import pytest

from app.services import support_payment_check as check

PRICE, USER = 'price_test', 'u1'


def paid_session(**overrides):
    session = {
        'id': 'cs_1', 'status': 'complete', 'payment_status': 'paid', 'client_reference_id': USER, 'mode': 'payment',
        'livemode': False, 'line_items': {'data': [{'price': {'id': PRICE}, 'quantity': 1}]},
        'payment_intent': {'id': 'pi_1', 'status': 'succeeded',
                           'latest_charge': {'id': 'ch_1', 'paid': True, 'status': 'succeeded', 'amount_refunded': 0, 'refunded': False,
                                             'disputed': False}},
    }
    for key, value in overrides.items():
        session[key] = value
    return session


def evaluate(session, livemode=False):
    return check.evaluate(session, checkout_price_id=PRICE, user_id=USER, livemode=livemode)


def test_verified_paid_session():
    assert evaluate(paid_session()) == ('verified', 'pi_1')


def test_price_may_be_a_plain_id():
    assert evaluate(paid_session(line_items={'data': [{'price': PRICE, 'quantity': 1}]}))[0] == 'verified'


@pytest.mark.parametrize('overrides,code', [
    ({'status': 'open'}, 'session_incomplete'),
    ({'payment_status': 'unpaid'}, 'not_paid'),
    ({'client_reference_id': 'someone-else'}, 'user_mismatch'),
    ({'mode': 'subscription'}, 'mode_mismatch'),
    ({'livemode': True}, 'livemode_mismatch'),
    ({'line_items': {'data': [{'price': {'id': 'price_other'}, 'quantity': 1}]}}, 'price_mismatch'),
    ({'line_items': {'data': [{'price': {'id': PRICE}, 'quantity': 2}]}}, 'price_mismatch'),
    ({'line_items': {'data': []}}, 'price_mismatch'),
    ({'payment_intent': {'id': 'pi_1', 'status': 'processing', 'latest_charge': None}}, 'payment_not_succeeded'),
    ({'payment_intent': None}, 'payment_not_succeeded'),
])
def test_each_rule_has_its_code(overrides, code):
    assert evaluate(paid_session(**overrides))[0] == code


def test_refunded_or_disputed_payment_not_verified():
    refunded = paid_session(payment_intent={'id': 'pi_1', 'status': 'succeeded',
                                            'latest_charge': {'paid': True, 'status': 'succeeded', 'amount_refunded': 990, 'refunded': True, 'disputed': False}})
    disputed = paid_session(payment_intent={'id': 'pi_1', 'status': 'succeeded',
                                            'latest_charge': {'paid': True, 'status': 'succeeded', 'amount_refunded': 0, 'refunded': False,
                                                              'disputed': True}})
    assert evaluate(refunded)[0] == 'refunded' and evaluate(disputed)[0] == 'disputed'


def test_partial_refund_is_not_verified():
    partial = paid_session(payment_intent={'id': 'pi_1', 'status': 'succeeded',
                                           'latest_charge': {'paid': True, 'status': 'succeeded', 'amount_refunded': 100,
                                                             'refunded': False, 'disputed': False}})
    assert evaluate(partial)[0] == 'refunded'


def test_unknown_deployment_livemode_is_never_verified():
    assert evaluate(paid_session(), livemode=None)[0] == 'livemode_mismatch'


def test_reader_never_uses_main_secret():
    source = inspect.getsource(check)
    assert 'stripe_secret_key' not in source and 'STRIPE_SECRET_KEY' not in source
    with pytest.raises(ValueError):
        check.StripeSessionReader('', timeout=5)


def test_reader_failure_is_reader_unavailable(monkeypatch):
    reader = check.StripeSessionReader('rk_test_synthetic', timeout=5)

    class Broken:
        def retrieve(self, *args, **kwargs):
            raise RuntimeError('network down')
    monkeypatch.setattr(reader, '_sessions', Broken())
    with pytest.raises(check.ReaderUnavailable):
        reader.read('cs_1')


def test_admin_settings_read_key_and_freshness(monkeypatch):
    from app.admin.config import AdminSettings
    monkeypatch.setenv('ADMIN_STRIPE_READ_KEY', 'rk_test_synthetic')
    monkeypatch.setenv('STRIPE_LIVEMODE', 'false')
    loaded = AdminSettings.from_env()
    assert loaded.stripe_read_key == 'rk_test_synthetic' and loaded.stripe_livemode is False
    assert (loaded.verify_fresh_seconds, loaded.verify_max_attempts) == (900, 5)


@pytest.mark.parametrize('charge', [None, 'ch_unexpanded', {}, {'paid': False, 'status': 'failed'}])
def test_unexpanded_or_unpaid_charge_fails_closed(charge):
    session = paid_session(payment_intent={'id': 'pi_1', 'status': 'succeeded', 'latest_charge': charge})
    assert evaluate(session)[0] == 'payment_not_succeeded'


@pytest.mark.parametrize('key,livemode', [('sk_test_main', 'false'), ('pk_test_x', 'false'), ('rk_live_x', 'false'),
                                          ('rk_test_x', 'true'), ('rk_test_x', None)])
def test_read_key_must_be_restricted_and_match_mode(monkeypatch, key, livemode):
    from app.admin.config import AdminSettings
    monkeypatch.setenv('ADMIN_STRIPE_READ_KEY', key)
    if livemode is None:
        monkeypatch.delenv('STRIPE_LIVEMODE', raising=False)
    else:
        monkeypatch.setenv('STRIPE_LIVEMODE', livemode)
    with pytest.raises(ValueError) as raised:
        AdminSettings.from_env()
    assert key not in str(raised.value)  # never echo the key
