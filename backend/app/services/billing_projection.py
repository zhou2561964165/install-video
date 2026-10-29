"""Versioned allowlist projection. Never persist a full provider object."""
import hashlib
import json
from collections.abc import Mapping

VERSION = 1
CHECKOUT = frozenset({'checkout.session.completed', 'checkout.session.async_payment_succeeded',
                      'checkout.session.async_payment_failed', 'checkout.session.expired'})
SUBSCRIPTION = frozenset({'customer.subscription.updated', 'customer.subscription.deleted'})
INVOICE = frozenset({'invoice.paid', 'invoice.payment_failed'})
REVERSALS = frozenset({'charge.refunded', 'charge.dispute.created',
                       'charge.dispute.funds_withdrawn', 'charge.dispute.closed'})


class InvalidPayload(ValueError):
    pass


def mapping(value):
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise InvalidPayload('invalid_mapping')
    return value


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode('utf8')).hexdigest()


def reference(value):
    if isinstance(value, Mapping):
        value = value.get('id')
    if value is None:
        return None
    if type(value) is not str or not value or len(value) > 255:
        raise InvalidPayload('invalid_reference')
    return value


def scalar(value, kind):
    if value is None:
        return None
    if type(value) is not kind:
        raise InvalidPayload('invalid_scalar')
    if kind is int and not 0 <= value <= 9223372036854775807:
        raise InvalidPayload('invalid_amount')
    if kind is str and len(value) > 255:
        raise InvalidPayload('invalid_text')
    return value


def project_object(kind, obj):
    if not isinstance(obj, Mapping):
        raise InvalidPayload('invalid_object')
    result = {'id': reference(obj.get('id'))}
    if not result['id']:
        raise InvalidPayload('missing_object')
    if kind in CHECKOUT:
        fields = {'mode': str, 'status': str, 'payment_status': str, 'amount_total': int, 'currency': str}
        refs = ('client_reference_id', 'customer', 'payment_intent', 'subscription')
        metadata = mapping(obj.get('metadata'))
        result['metadata'] = {'checkout_id': reference(metadata.get('checkout_id'))}
        result['line_items'] = {'data': project_items(obj.get('line_items'), invoice=False)}
    elif kind in REVERSALS:
        fields = {'status': str, 'amount': int, 'amount_refunded': int, 'refunded': bool, 'currency': str}
        refs = ('customer', 'payment_intent', 'charge')
    elif kind in SUBSCRIPTION:
        fields = {'status': str, 'cancel_at_period_end': bool, 'current_period_end': int}
        refs = ('customer',)
        result['latest_invoice'] = (project_object('invoice.paid', obj['latest_invoice'])
            if isinstance(obj.get('latest_invoice'), Mapping) else reference(obj.get('latest_invoice')))
        result['items'] = {'data': project_items(obj.get('items'), invoice=False)}
    elif kind in INVOICE:
        fields = {'status': str, 'amount_paid': int, 'amount_due': int, 'currency': str}
        refs = ('customer', 'payment_intent', 'subscription')
        result['lines'] = {'data': project_items(obj.get('lines'), invoice=True)}
        parent = mapping(obj.get('parent'))
        details = mapping(parent.get('subscription_details'))
        result['parent'] = {'subscription_details': {'subscription': reference(details.get('subscription'))}}
        payment_container = mapping(obj.get('payments'))
        if payment_container.get('has_more') is True:
            raise InvalidPayload('unsupported_pagination')
        payments = payment_container.get('data', [])
        if not isinstance(payments, list) or len(payments) > 100:
            raise InvalidPayload('invalid_payments')
        result['payments'] = {'data': [{'status': scalar(mapping(p).get('status'), str), 'payment': {
            'payment_intent': reference(mapping(mapping(p).get('payment')).get('payment_intent'))}} for p in payments]}
    else:
        # Unsupported types still have a durable identity and ignored reason.
        fields, refs = {}, ()
    for name, typ in fields.items():
        result[name] = scalar(obj.get(name), typ)
    for name in refs:
        result[name] = reference(obj.get(name))
    if result.get('currency') is not None:
        currency = result['currency']
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha() or currency != currency.lower():
            raise InvalidPayload('invalid_currency')
    return result


def project_items(container, *, invoice):
    if container is None:
        return []
    if not isinstance(container, Mapping) or container.get('has_more') is True:
        raise InvalidPayload('unsupported_pagination')
    data = container.get('data', [])
    if not isinstance(data, list) or len(data) > 100:
        raise InvalidPayload('invalid_lines')
    result = []
    for item in data:
        if not isinstance(item, Mapping):
            raise InvalidPayload('invalid_line')
        price = reference(item.get('price'))
        if invoice:
            price = price or reference(mapping(mapping(item.get('pricing')).get('price_details')).get('price'))
            result.append({'price': price, 'period': {'end': scalar(mapping(item.get('period')).get('end'), int)}})
        else:
            result.append({'price': price, 'current_period_end': scalar(item.get('current_period_end'), int),
                           'quantity': scalar(item.get('quantity'), int)})
    return result


def canonical(event, scope, livemode):
    if not isinstance(event, Mapping) or type(event.get('livemode')) is not bool or event['livemode'] != livemode:
        raise InvalidPayload('mode_mismatch')
    event_id, kind = reference(event.get('id')), reference(event.get('type'))
    if not event_id or not kind:
        raise InvalidPayload('missing_identity')
    obj = project_object(kind, mapping(event.get('data')).get('object'))
    value = {'version': VERSION, 'scope': scope, 'livemode': livemode, 'id': event_id,
             'type': kind, 'api_version': scalar(event.get('api_version'), str), 'data': {'object': obj}}
    return encode(value)
