import httpx
import pytest

from app.services.network_retry import retry_get


def _status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com/resource")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("request failed", request=request, response=response)


@pytest.mark.parametrize(
    "failure",
    [
        lambda: httpx.ConnectError("temporary connect failure", request=httpx.Request("GET", "https://example.com")),
        lambda: httpx.ReadTimeout("temporary read timeout", request=httpx.Request("GET", "https://example.com")),
    ],
)
def test_retry_get_retries_transport_failures_with_exponential_delays(failure):
    attempts = 0
    delays = []

    def get():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise failure()
        return b"caption bytes"

    result = retry_get(get, max_retries=2, backoff_seconds=0.25, sleep=delays.append)

    assert result == b"caption bytes"
    assert attempts == 3
    assert delays == [0.25, 0.5]


def test_retry_get_recovers_from_remote_protocol_eof():
    attempts = 0
    delays = []

    def get():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.RemoteProtocolError(
                "peer closed the connection",
                request=httpx.Request("GET", "https://example.com/resource"),
            )
        return b"caption bytes"

    result = retry_get(get, max_retries=1, backoff_seconds=0.25, sleep=delays.append)

    assert result == b"caption bytes"
    assert attempts == 2
    assert delays == [0.25]


def test_retry_get_retries_transient_status_and_preserves_final_exception():
    attempts = 0
    delays = []
    final_error = _status_error(503)

    def get():
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise _status_error(503)
        raise final_error

    with pytest.raises(httpx.HTTPStatusError) as raised:
        retry_get(get, max_retries=2, backoff_seconds=0.1, sleep=delays.append)

    assert raised.value is final_error
    assert attempts == 3
    assert delays == [0.1, 0.2]


@pytest.mark.parametrize("status_code", [400, 404, 429])
def test_retry_get_does_not_retry_non_transient_status(status_code):
    attempts = 0
    delays = []
    error = _status_error(status_code)

    def get():
        nonlocal attempts
        attempts += 1
        raise error

    with pytest.raises(httpx.HTTPStatusError) as raised:
        retry_get(get, max_retries=3, backoff_seconds=0.5, sleep=delays.append)

    assert raised.value is error
    assert attempts == 1
    assert delays == []


def test_retry_get_does_not_retry_unrelated_exceptions():
    attempts = 0
    delays = []
    error = ValueError("malformed payload")

    def get():
        nonlocal attempts
        attempts += 1
        raise error

    with pytest.raises(ValueError) as raised:
        retry_get(get, max_retries=3, backoff_seconds=0.5, sleep=delays.append)

    assert raised.value is error
    assert attempts == 1
    assert delays == []
