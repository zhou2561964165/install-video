"""Strict v1 persistence boundary for complete source accounting trees.

No URLs, credentials, DB or I/O. Restore requires authoritative aware DB times;
fencing and crash-safe accounting remain the caller/executor's responsibility.
"""
from dataclasses import dataclass, replace
from datetime import datetime
import json
import math
import time

from .outbound_budget import BudgetCheckpoint, BudgetLimits, BudgetProfile, BudgetReason, OutboundBudget
from .outbound_policy import OutboundPurpose

VERSION = 1
MAX_BYTES = 65536
MAX_DEPTH = 8
MAX_NODES = 64
MAX_INT = 2**63 - 1
_COUNTS = ('requests', 'redirects', 'raw_bytes', 'decoded_bytes')
_LIMITS = ('seconds', *_COUNTS, 'response_raw_bytes', 'response_decoded_bytes', 'children')
_NODE = {'limits', 'purpose', 'remaining_seconds', *_COUNTS, 'blocked', 'children'}


@dataclass(frozen=True)
class BudgetEnvelope:
    download_parent: BudgetCheckpoint
    direct_resolve_parent: BudgetCheckpoint


def _bad():
    return ValueError('Invalid persisted download budget')


def _number(value, low, high, *, integer=False):
    if (type(value) not in ((int,) if integer else (int, float)) or
            not low <= value <= high or (type(value) is float and not math.isfinite(value))):
        raise _bad()
    return value


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise _bad()
        value[key] = item
    return value


def _read_node(value, depth, nodes):
    nodes[0] += 1
    if depth > MAX_DEPTH or nodes[0] > MAX_NODES or type(value) is not dict or set(value) != _NODE:
        raise _bad()
    limits = value['limits']
    if type(limits) is not dict or set(limits) != set(_LIMITS):
        raise _bad()
    checked = {'seconds': _number(limits['seconds'], 0.000001, BudgetProfile.download_parent().seconds)}
    for key in _LIMITS[1:]:
        checked[key] = _number(limits[key], 0 if key in ('redirects', 'children') else 1, MAX_INT, integer=True)
    cap = BudgetLimits(**checked)
    # A response cannot permit more than the node's entire byte allowance.
    if cap.response_raw_bytes > cap.raw_bytes or cap.response_decoded_bytes > cap.decoded_bytes:
        raise _bad()
    remaining = _number(value['remaining_seconds'], 0, cap.seconds)
    counts = {key: _number(value[key], 0, getattr(cap, key), integer=True) for key in _COUNTS}
    if counts['redirects'] > counts['requests']:
        raise _bad()
    if type(value['purpose']) is not str or type(value['children']) is not list or len(value['children']) > cap.children:
        raise _bad()
    if value['blocked'] is not None and type(value['blocked']) is not str:
        raise _bad()
    try:
        purpose = OutboundPurpose(value['purpose'])
        blocked = BudgetReason(value['blocked']) if value['blocked'] is not None else None
    except ValueError:
        raise _bad() from None
    children = tuple(_read_node(child, depth + 1, nodes) for child in value['children'])
    if any(sum(getattr(child, key) for child in children) > counts[key] for key in _COUNTS):
        raise _bad()
    if any(child.remaining_seconds > remaining or any(getattr(child.limits, key) > getattr(cap, key)
           for key in _COUNTS) for child in children):
        raise _bad()
    return BudgetCheckpoint(cap, purpose, remaining, **counts, blocked=blocked, children=children)


def _write_node(node):
    return {'limits': {key: getattr(node.limits, key) for key in _LIMITS},
            'purpose': node.purpose.value, 'remaining_seconds': node.remaining_seconds,
            **{key: getattr(node, key) for key in _COUNTS},
            'blocked': node.blocked.value if node.blocked is not None else None,
            'children': [_write_node(child) for child in node.children]}


def _profile(node, profile):
    if any(getattr(node.limits, key) > getattr(profile, key) for key in _LIMITS):
        raise _bad()


def decode_budget(version: int, payload: str, *, resolve_attempts_used: int | None = None) -> BudgetEnvelope:
    if type(version) is not int or version != VERSION or type(payload) is not str:
        raise _bad()
    try:
        if len(payload.encode('utf8')) > MAX_BYTES:
            raise _bad()
        data = json.loads(payload, object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(_bad()))
        if type(data) is not dict or set(data) != {'download_parent', 'direct_resolve_parent'}:
            raise _bad()
        nodes = [0]
        download = _read_node(data['download_parent'], 0, nodes)
        direct = _read_node(data['direct_resolve_parent'], 0, nodes)
        _profile(download, BudgetProfile.download_parent())
        _profile(direct, BudgetProfile.direct_parent())
        for child in download.children:
            _profile(child, BudgetProfile.download_attempt())
            if child.purpose is not OutboundPurpose.SOURCE:
                raise _bad()
        for child in direct.children:
            _profile(child, BudgetProfile.resolve())
            if child.purpose is not OutboundPurpose.METADATA:
                raise _bad()
        if download.purpose is not OutboundPurpose.SOURCE or direct.purpose is not OutboundPurpose.METADATA:
            raise _bad()
        if any(getattr(direct, key) + sum(getattr(child, key) for child in download.children) >
               getattr(download, key) for key in _COUNTS):
            raise _bad()
        if resolve_attempts_used is not None and (type(resolve_attempts_used) is not int or
                resolve_attempts_used != len(direct.children)):
            raise _bad()
        return BudgetEnvelope(download, direct)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        pass
    raise _bad() from None


def encode_budget(envelope: BudgetEnvelope, *, resolve_attempts_used: int | None = None) -> str:
    if type(envelope) is not BudgetEnvelope:
        raise _bad()
    payload = None
    try:
        payload = json.dumps({'download_parent': _write_node(envelope.download_parent),
                              'direct_resolve_parent': _write_node(envelope.direct_resolve_parent)},
                             ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, AttributeError, RecursionError):
        pass
    if payload is None:
        raise _bad() from None
    decode_budget(VERSION, payload, resolve_attempts_used=resolve_attempts_used)
    return payload


def initial_budget() -> BudgetEnvelope:
    return BudgetEnvelope(OutboundBudget(BudgetProfile.download_parent(), purpose=OutboundPurpose.SOURCE).checkpoint(),
                          OutboundBudget(BudgetProfile.direct_parent()).checkpoint())


def _aware(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _bad()


def restore_budget(version, payload, *, checkpoint_at, db_now, deadline_at,
                   resolve_deadline_at, resolve_attempt_deadline=None,
                   resolve_attempts_used=None, clock=time.monotonic):
    """Return two local counters, capped by downtime and each distinct deadline."""
    envelope = decode_budget(version, payload, resolve_attempts_used=resolve_attempts_used)
    for value in (checkpoint_at, db_now, deadline_at, resolve_deadline_at):
        _aware(value)
    if db_now < checkpoint_at or resolve_deadline_at > deadline_at:
        raise _bad()
    elapsed = (db_now - checkpoint_at).total_seconds()
    def clip(node, deadline):
        remaining = max(0., min(node.remaining_seconds - elapsed, (deadline - db_now).total_seconds()))
        return replace(node, remaining_seconds=remaining,
                       children=tuple(clip(child, deadline) for child in node.children))
    download = clip(envelope.download_parent, deadline_at)
    direct = clip(envelope.direct_resolve_parent, resolve_deadline_at)
    if resolve_attempt_deadline is not None:
        _aware(resolve_attempt_deadline)
        if resolve_attempt_deadline > resolve_deadline_at or not direct.children:
            raise _bad()
        children = list(direct.children)
        child = children[-1]
        children[-1] = replace(child, remaining_seconds=max(0., min(child.remaining_seconds,
                                     (resolve_attempt_deadline - db_now).total_seconds())))
        direct = replace(direct, children=tuple(children))
    return (OutboundBudget.restore(download, elapsed_seconds=0, clock=clock),
            OutboundBudget.restore(direct, elapsed_seconds=0, clock=clock))
