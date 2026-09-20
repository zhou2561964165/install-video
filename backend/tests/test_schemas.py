import pytest
from pydantic import ValidationError

from app.models import JobStatus
from app.schemas import (
    DownloadRequest,
    FormatOption,
    ParseRequest,
    ParseResponse,
)


def test_parse_request_requires_url():
    ParseRequest(url="https://example.com/v")
    with pytest.raises(ValidationError):
        ParseRequest(url="")


def test_parse_response_shape():
    r = ParseResponse(
        title="t",
        thumbnail=None,
        duration=12.5,
        formats=[FormatOption(format_id="18", label="360p", direct=True)],
    )
    assert r.formats[0].direct is True


def test_download_request_force_server_default_false():
    d = DownloadRequest(url="https://example.com/v", format_id="18")
    assert d.force_server is False
