"""Pure persistence validation and deadline recovery, without DB/network."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.services import download_budget_codec as codec
from app.services.outbound_budget import BudgetProfile, OutboundBudget
from app.services.outbound_policy import OutboundPurpose


def payload():
    return json.loads(codec.encode_budget(codec.initial_budget()))


def decode(value):
    return codec.decode_budget(1, json.dumps(value))


def test_round_trip_complete_checkpoint():
    download = OutboundBudget(BudgetProfile.download_parent(), purpose=OutboundPurpose.SOURCE)
    direct = OutboundBudget(BudgetProfile.direct_parent())
    child = direct.child(BudgetProfile.resolve())
    for budget in (download, child):
        stream = budget.begin_request()
        stream.consume(raw_bytes=12, decoded_bytes=16)
        stream.close()
    state = codec.BudgetEnvelope(download.checkpoint(), direct.checkpoint())
    text = codec.encode_budget(state, resolve_attempts_used=1)
    assert codec.decode_budget(1, text, resolve_attempts_used=1) == state


@pytest.mark.parametrize('version', [True, 0, 2, '1', None])
def test_unknown_or_non_integer_version_rejected(version):
    with pytest.raises(ValueError, match='Invalid persisted download budget'):
        codec.decode_budget(version, codec.encode_budget(codec.initial_budget()))


@pytest.mark.parametrize('key,value', [('requests', True), ('requests', -1), ('requests', 10**600),
    ('remaining_seconds', float('nan')), ('remaining_seconds', float('inf')),
    ('remaining_seconds', -1), ('remaining_seconds', 1801), ('raw_bytes', 2**63),
    ('blocked', 'secret'), ('purpose', 'url'), ('children', {}), ('redirects', 1)])
def test_invalid_node_fields_fail_closed(key, value):
    data = payload()
    data['download_parent'][key] = value
    with pytest.raises(ValueError, match='Invalid persisted download budget') as error:
        decode(data)
    assert error.value.__context__ is None


@pytest.mark.parametrize('key,value', [('requests', True), ('raw_bytes', 2**63), ('seconds', True),
    ('seconds', float('nan')), ('seconds', 1801), ('children', -1), ('decoded_bytes', 1)])
def test_invalid_limits_rejected(key, value):
    data = payload()
    data['download_parent']['limits'][key] = value
    with pytest.raises(ValueError):
        decode(data)


@pytest.mark.parametrize('text', ['{}', '{', '[]', '{"download_parent":{},"download_parent":{}}',
    ' ' * (codec.MAX_BYTES + 1), '{"download_parent":NaN}', '[' * 1100 + ']' * 1100],
    ids=['empty', 'truncated', 'array', 'duplicate', 'oversize', 'nan', 'deep_json'])
def test_invalid_json_envelopes_have_fixed_safe_error(text):
    with pytest.raises(ValueError, match='Invalid persisted download budget') as error:
        codec.decode_budget(1, text)
    assert error.value.__context__ is None and error.value.__cause__ is None


def test_unknown_secret_fields_and_missing_fields_rejected():
    for change in ('extra', 'missing', 'root'):
        data = payload()
        if change == 'extra':
            data['download_parent']['url'] = 'sensitive'
        elif change == 'missing':
            del data['download_parent']['blocked']
        else:
            data['version'] = 1
        with pytest.raises(ValueError):
            decode(data)


def test_tree_depth_nodes_and_parent_totals_rejected():
    for kind in ('depth', 'nodes', 'counts', 'attempt_count'):
        data = payload()
        if kind == 'depth':
            node = data['download_parent']
            for _ in range(codec.MAX_DEPTH + 1):
                node['limits']['children'] = 1
                node['children'] = [json.loads(json.dumps(data['direct_resolve_parent']))]
                node = node['children'][0]
        elif kind == 'nodes':
            data['download_parent']['limits']['children'] = codec.MAX_NODES + 1
            data['download_parent']['children'] = [data['direct_resolve_parent']] * (codec.MAX_NODES + 1)
        elif kind == 'counts':
            data['direct_resolve_parent']['requests'] = 1
        with pytest.raises(ValueError):
            codec.decode_budget(1, json.dumps(data), resolve_attempts_used=1 if kind == 'attempt_count' else None)


def test_restore_subtracts_downtime_and_distinct_absolute_deadlines():
    now = datetime(2026, 10, 24, 23, 59, 50, tzinfo=timezone.utc)
    # Deterministic checkpoint: a real-clock initial_budget() can legitimately save 1799.999...
    # (elapsed time or float rounding), which would make the exact assertions below flaky.
    fresh_download = OutboundBudget(BudgetProfile.download_parent(), purpose=OutboundPurpose.SOURCE, clock=lambda: 0.)
    fresh_direct = OutboundBudget(BudgetProfile.direct_parent(), clock=lambda: 0.)
    text = codec.encode_budget(codec.BudgetEnvelope(fresh_download.checkpoint(), fresh_direct.checkpoint()))
    download, direct = codec.restore_budget(1, text, checkpoint_at=now, db_now=now + timedelta(seconds=20),
        deadline_at=now + timedelta(seconds=1500), resolve_deadline_at=now + timedelta(seconds=50), clock=lambda: 10.)
    assert download.snapshot().remaining_seconds == 1480
    assert direct.snapshot().remaining_seconds == 30
    download, direct = codec.restore_budget(1, text, checkpoint_at=now, db_now=now + timedelta(seconds=70),
        deadline_at=now + timedelta(seconds=1800), resolve_deadline_at=now + timedelta(seconds=60), clock=lambda: 10.)
    assert download.snapshot().remaining_seconds == 1730
    assert direct.snapshot().remaining_seconds == 0


def test_resolve_attempt_deadline_tightens_only_last_child():
    download = OutboundBudget(BudgetProfile.download_parent(), purpose=OutboundPurpose.SOURCE, clock=lambda: 0.)
    direct = OutboundBudget(BudgetProfile.direct_parent(), clock=lambda: 0.)
    direct.child(BudgetProfile.resolve())
    text = codec.encode_budget(codec.BudgetEnvelope(download.checkpoint(), direct.checkpoint()))
    now = datetime.now(timezone.utc)
    restored_download, restored_direct = codec.restore_budget(1, text, checkpoint_at=now, db_now=now + timedelta(seconds=5),
        deadline_at=now + timedelta(seconds=1800), resolve_deadline_at=now + timedelta(seconds=60),
        resolve_attempt_deadline=now + timedelta(seconds=10), resolve_attempts_used=1, clock=lambda: 0.)
    assert restored_download.snapshot().remaining_seconds == 1795
    assert restored_direct.resume_child(0).snapshot().remaining_seconds == 5


@pytest.mark.parametrize('kind', ['naive', 'backward', 'resolve_after_download', 'unknown_elapsed'])
def test_bad_authoritative_times_rejected(kind):
    now = datetime.now(timezone.utc)
    args = dict(checkpoint_at=now, db_now=now, deadline_at=now + timedelta(seconds=1800),
                resolve_deadline_at=now + timedelta(seconds=60))
    args[{'naive': 'db_now', 'backward': 'db_now', 'resolve_after_download': 'resolve_deadline_at',
          'unknown_elapsed': 'checkpoint_at'}[kind]] = {'naive': now.replace(tzinfo=None),
        'backward': now - timedelta(seconds=1), 'resolve_after_download': now + timedelta(seconds=1801),
        'unknown_elapsed': None}[kind]
    with pytest.raises(ValueError):
        codec.restore_budget(1, codec.encode_budget(codec.initial_budget()), **args)


def test_trusted_dto_encoding_still_requires_full_schema_and_safe_exception():
    from dataclasses import replace
    envelope = codec.initial_budget()
    with pytest.raises(ValueError, match='Invalid persisted download budget') as error:
        codec.encode_budget(replace(envelope, download_parent='synthetic-secret'))
    assert error.value.__context__ is None and error.value.__cause__ is None


@pytest.mark.parametrize('counter', ['requests', 'redirects', 'raw_bytes', 'decoded_bytes'])
def test_direct_plus_download_attempt_totals_cannot_exceed_shared_parent(counter):
    data = payload()
    server_child = json.loads(json.dumps(data['download_parent']))
    server_child['limits'] = {key: getattr(BudgetProfile.download_attempt(), key) for key in codec._LIMITS}
    server_child['remaining_seconds'] = 10
    server_child['requests'] = server_child[counter] = 2
    data['download_parent']['requests'] = data['download_parent'][counter] = 2
    data['direct_resolve_parent']['requests'] = data['direct_resolve_parent'][counter] = 2
    data['download_parent']['children'] = [server_child]
    # Either group individually fits2, but the disjoint groups total4.
    with pytest.raises(ValueError, match='Invalid persisted download budget'):
        decode(data)


@pytest.mark.parametrize('tree,purpose', [('download_parent', 'metadata'), ('direct_resolve_parent', 'source')])
def test_child_purposes_are_bound_to_their_tree(tree, purpose):
    data = payload()
    child = json.loads(json.dumps(data[tree]))
    profile = BudgetProfile.download_attempt() if tree == 'download_parent' else BudgetProfile.resolve()
    child['limits'] = {key: getattr(profile, key) for key in codec._LIMITS}
    child['remaining_seconds'] = 1
    child['purpose'] = purpose
    data[tree]['children'] = [child]
    with pytest.raises(ValueError):
        decode(data)
