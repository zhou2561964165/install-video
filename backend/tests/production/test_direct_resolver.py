"""B5 U6 Task 1: guarded direct resolver over B4's borrowed budgets (synthetic wire only).

Run via run_b5_ytdlp_u4_offline.py (DNS/connect denied, YTDLP_NO_PLUGINS=1).
"""
import pytest

from app.schemas import DownloadRequest
from app.services import direct_resolver, ytdlp_service as service
from app.services.download_submission import DirectResult, ResolveAccounting, _validate_direct
from app.services.outbound_budget import BudgetLimits, OutboundBudget
from app.services.outbound_httpx import ControlledHttpStatusError
from app.services.outbound_policy import OutboundError, OutboundUnavailableError
from app.services.source_network import SourceNetworkContext
from test_outbound_httpx import transport_network  # noqa: F401  (fixture)
from test_source_ytdlp_wiring import PAGE, metadata, registry, sends, serve  # noqa: F401  (fixture/helpers)
from test_ytdlp_guard_director import context, reply, safe


def accounting():
    download = OutboundBudget(BudgetLimits(seconds=100, requests=8))
    direct = OutboundBudget(BudgetLimits(seconds=100, requests=8, children=2))
    return ResolveAccounting(download, direct, direct.child(BudgetLimits(seconds=50, requests=4)))


def offline(group):
    return SourceNetworkContext(context().channel, group)


def resolve(format_id='720', *, url=PAGE, books=None, factory=offline):
    books = books or accounting()
    request = DownloadRequest(url=url, format_id=format_id)
    return direct_resolver.guarded_resolver(factory)(request, books), books


def test_direct_link_charges_both_trees_once_without_media_io(registry, transport_network):
    serve(transport_network, metadata())
    result, books = resolve()
    assert type(result) is DirectResult and result.response.mode == 'direct'
    assert result.response.url == 'http://cdn.example/v720.mp4' and result.response.job_id is None
    assert result.response.headers == {'User-Agent': 'x'}  # Cookie stripped, only plain headers
    _validate_direct(result.response)  # what complete_direct will check
    assert sends(transport_network) == 1  # metadata only: the browser fetches the media
    for node in (books.download, books.direct, books.child):
        assert node.snapshot().requests == 1
    assert books.download.snapshot().children == 0 and books.direct.snapshot().children == 1  # nothing new


@pytest.mark.parametrize('format_id', ['137+140', 'bestvideo+bestaudio'])
def test_unsupported_stored_format_has_no_direct_link_without_io(transport_network, format_id):
    result, books = resolve(format_id)
    assert result == DirectResult() and sends(transport_network) == 0
    assert books.download.snapshot().requests == 0


def test_no_matching_single_file_has_no_direct_link(registry, transport_network):
    serve(transport_network, metadata())
    result, _ = resolve('999')
    assert result == DirectResult() and sends(transport_network) == 1


def test_safety_errors_are_raised_never_turned_into_no_direct_link(registry, transport_network):
    serve(transport_network, metadata(formats=[dict(url='http://10.0.0.1/v.mp4', format_id='720', ext='mp4')]))
    with pytest.raises(OutboundError) as error:
        resolve()
    safe(error.value)


def test_extraction_status_is_raised_with_its_class(registry, transport_network):
    transport_network.replies.append(reply(b'', b'412 Precondition Failed'))
    with pytest.raises(ControlledHttpStatusError) as error:
        resolve()
    assert error.value.source_status == 412  # submit_download maps 401/403/412 to verification_required


def test_bilibili_target_is_raised_not_no_direct_link(registry, transport_network):
    serve(transport_network, metadata(formats=[dict(url='http://www.bilibili.com/v.mp4', format_id='720', ext='mp4')]))
    with pytest.raises(OutboundUnavailableError):
        resolve()


def test_bilibili_page_is_refused_before_io(transport_network):
    with pytest.raises(OutboundUnavailableError):
        resolve(url='https://www.bilibili.com/video/BV1xx411c7mD')
    assert sends(transport_network) == 0


def test_default_factory_is_the_closed_runtime_network(transport_network):
    request = DownloadRequest(url=PAGE, format_id='720')
    with pytest.raises(OutboundUnavailableError):
        direct_resolver.guarded_resolver()(request, accounting())
    assert sends(transport_network) == 0


def test_resolve_direct_service_result_shape(registry, transport_network):
    serve(transport_network, metadata())
    found = service.resolve_direct(PAGE, '720', network=context())
    assert found == ('http://cdn.example/v720.mp4', {'User-Agent': 'x'})



# Review I1: a Bilibili target is refused whatever its container, never "no direct link".
@pytest.mark.parametrize('extra', [dict(ext='m4s'), dict()])
def test_bilibili_leaf_with_any_container_is_refused(registry, transport_network, extra):
    leaf = dict(url='http://www.bilibili.com/v.m4s', format_id='720', **extra)
    serve(transport_network, metadata(formats=[leaf]))
    with pytest.raises(OutboundUnavailableError):
        resolve()


# Review I3 (A contract §3): transient failures and an exhausted budget fall back; refusals do not.
@pytest.mark.parametrize('status', [b'503 Service Unavailable', b'429 Too Many Requests', b'408 Request Timeout'])
def test_transient_source_status_falls_back(registry, transport_network, status):
    transport_network.replies.append(reply(b'', status))
    result, _ = resolve()
    assert result == DirectResult()


def test_transient_classification():
    from app.services.outbound_httpx import ControlledHttpBusyError
    transient = direct_resolver._transient
    assert transient(OutboundError('source_budget_exhausted', 'requests')) and transient(OutboundError('source_timeout', 'deadline'))
    assert transient(ControlledHttpBusyError()) and transient(ControlledHttpStatusError(502))
    assert not transient(OutboundError('outbound_blocked', 'address')) and not transient(OutboundUnavailableError())
    assert not any(transient(ControlledHttpStatusError(code)) for code in (401, 403, 404, 410, 412))


@pytest.mark.parametrize('status', [b'401 Unauthorized', b'403 Forbidden', b'404 Not Found'])
def test_refusing_source_status_is_raised(registry, transport_network, status):
    transport_network.replies.append(reply(b'', status))
    with pytest.raises(ControlledHttpStatusError):
        resolve()


# Review M3: the browser fetches the link, so private-only names are refused.
@pytest.mark.parametrize('url', ['http://media.local/v.mp4', 'http://router/v.mp4', 'http://box.internal/v.mp4'])
def test_private_only_host_names_are_refused(registry, transport_network, url):
    serve(transport_network, metadata(formats=[dict(url=url, format_id='720', ext='mp4')]))
    with pytest.raises(OutboundError):
        resolve()


# Review M2: one value per header name, the leaf's own value winning.
def test_headers_merge_case_insensitively_with_the_leaf_winning(registry, transport_network):
    leaf = dict(url='http://cdn.example/v.mp4', format_id='720', ext='mp4', http_headers={'referer': 'http://leaf.example/'})
    serve(transport_network, metadata(formats=[leaf], http_headers={'Referer': 'http://root.example/'}))
    result, _ = resolve()
    assert result.response.headers == {'referer': 'http://leaf.example/'}
