"""B5 U6 Task 2: B4 submit_download with the guarded direct resolver (isolated PG, synthetic wire only)."""
import os
from pathlib import Path
import sys

os.environ.setdefault('YTDLP_NO_PLUGINS', '1')  # official opt-out before any yt-dlp import
sys.path.insert(0, str(Path(__file__).resolve().parent / 'production'))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.models import DownloadOperation  # noqa: E402
from app.services import direct_resolver  # noqa: E402
from app.services.source_network import SourceNetworkContext  # noqa: E402
from test_outbound_httpx import transport_network  # noqa: E402,F401  (fixture)
from app.services.download_submission import AccessSnapshot, submit_download  # noqa: E402
from test_pg_download_submission import REQUEST, assert_charge, facts, pg, service  # noqa: E402,F401
from test_source_ytdlp_wiring import PAGE, metadata, registry, sends, serve  # noqa: E402,F401
from test_ytdlp_guard_director import context, reply  # noqa: E402

DIRECT = REQUEST.model_copy(update={'url': PAGE, 'format_id': '720', 'force_server': False})
RESOLVER = direct_resolver.guarded_resolver(lambda group: SourceNetworkContext(context().channel, group))


def post(pg, key='same', request=DIRECT, **kwargs):
    # The access snapshot binds the request's own format id (B4 rejects a changed format).
    return submit_download(pg, 'b4-user', request, key, AccessSnapshot(720, 0, request.format_id), **kwargs)


def checkpoint(pg):
    with Session(pg) as session:
        op = session.exec(select(DownloadOperation)).one()
        return op, service.codec.decode_budget(op.budget_version, op.budget_checkpoint_json, resolve_attempts_used=1)


def test_direct_link_is_ready_charged_on_both_roots_and_replayed(pg, registry, transport_network):
    serve(transport_network, metadata())
    response = post(pg, request=DIRECT, trusted_resolver=RESOLVER)
    assert response.mode == 'direct' and response.url == 'http://cdn.example/v720.mp4'
    assert response.headers == {'User-Agent': 'x'}
    op, data = checkpoint(pg)
    assert op.state == 'direct_ready' and op.resolve_owner is None
    with Session(pg) as session:
        receipt = session.exec(select(service.DownloadIdempotency)).one()
        ttl = service.settings.download_idempotency_direct_ttl_seconds
        assert receipt.direct_expires_at is not None
        assert 0 < (receipt.direct_expires_at - op.completed_at.timestamp()) <= ttl + 1
    assert data.download_parent.requests == data.direct_resolve_parent.requests == 1
    assert data.download_parent.raw_bytes == data.direct_resolve_parent.raw_bytes > 0
    assert post(pg, request=DIRECT, trusted_resolver=RESOLVER) == response  # replay: no second GET
    assert sends(transport_network) == 1
    assert_charge(pg, slots=0)


def test_unsupported_stored_format_falls_back_to_a_server_job_without_io(pg, transport_network):
    response = post(pg, request=DIRECT.model_copy(update={'format_id': '137+140'}), trusted_resolver=RESOLVER)
    assert response.mode == 'server' and response.job_id
    assert sends(transport_network) == 0 and facts(pg)['job'] == 1


def test_no_matching_single_file_falls_back_after_the_metadata_charge(pg, registry, transport_network):
    serve(transport_network, metadata())
    response = post(pg, request=DIRECT.model_copy(update={'format_id': '999'}), trusted_resolver=RESOLVER)
    assert response.mode == 'server'
    _, data = checkpoint(pg)
    assert data.download_parent.requests == data.direct_resolve_parent.requests == 1


def test_source_verification_status_never_falls_back(pg, registry, transport_network):
    transport_network.replies.append(reply(b'', b'412 Precondition Failed'))
    with pytest.raises(HTTPException) as error:
        post(pg, request=DIRECT, trusted_resolver=RESOLVER)
    assert error.value.status_code == 422 and error.value.detail['error_type'] == 'verification_required'
    assert facts(pg)['job'] == 0
    assert_charge(pg, slots=0)


def test_policy_blocked_format_never_falls_back(pg, registry, transport_network):
    serve(transport_network, metadata(formats=[dict(url='http://10.0.0.1/v.mp4', format_id='720', ext='mp4')]))
    with pytest.raises(HTTPException) as error:
        post(pg, request=DIRECT, trusted_resolver=RESOLVER)
    assert error.value.detail['error_type'] == 'outbound_blocked' and facts(pg)['job'] == 0


def test_default_factory_fails_resolve_closed_without_io(pg, transport_network):
    with pytest.raises(HTTPException) as error:
        post(pg, request=DIRECT, trusted_resolver=direct_resolver.guarded_resolver())
    assert error.value.detail['error_type'] == 'outbound_unavailable'
    assert sends(transport_network) == 0 and facts(pg)['job'] == 0


def test_no_route_wires_the_resolver():
    # Review M5(c): nothing under app/routes (or main) refers to the guarded resolver before the gate.
    app = Path(__file__).resolve().parents[1] / 'app'
    for path in [*sorted((app / 'routes').glob('*.py')), app / 'main.py']:
        text = path.read_text('utf8')
        assert 'direct_resolver' not in text and 'guarded_resolver' not in text, path.name


# Review I2: an oversized provider expiry value is ignored (never extends TTL, never stalls the operation).
def test_oversized_expiry_parameter_is_ignored(pg, registry, transport_network):
    url = 'http://cdn.example/v720.mp4?expires=' + '9' * 400
    serve(transport_network, metadata(formats=[dict(url=url, format_id='720', ext='mp4')]))
    response = post(pg, request=DIRECT, trusted_resolver=RESOLVER)
    assert response.mode == 'direct'
    op, _ = checkpoint(pg)
    with Session(pg) as session:
        receipt = session.exec(select(service.DownloadIdempotency)).one()
    ttl = service.settings.download_idempotency_direct_ttl_seconds
    assert op.state == 'direct_ready' and (receipt.direct_expires_at - op.completed_at.timestamp()) <= ttl + 1


# Review I3: a transient source failure falls back to a server Job on the same slot (A contract §3).
def test_transient_source_failure_falls_back_to_a_server_job(pg, registry, transport_network):
    transport_network.replies.append(reply(b'', b'503 Service Unavailable'))
    response = post(pg, request=DIRECT, trusted_resolver=RESOLVER)
    assert response.mode == 'server' and response.job_id and facts(pg)['job'] == 1
