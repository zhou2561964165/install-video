"""T0: safe source-terminal errors must cross ASR audio acquisition unchanged."""

from pathlib import Path

import pytest

from app.services import ytdlp_service as service
from app.services.asr_errors import ASRError
from app.services.bilibili_session import SessionError
from app.services.outbound_httpx import ControlledHttpStatusError
from app.services.outbound_policy import OutboundPolicyError


URL = "https://example.org/video"


class _RaiseOnEnter:
    def __init__(self, error):
        self.error = error

    def __enter__(self):
        raise self.error

    def __exit__(self, *args):
        return False


def _install_source_failure(monkeypatch, error):
    calls = []

    def source_youtube_dl(url, options):
        calls.append((url, options))
        return _RaiseOnEnter(error)

    monkeypatch.setattr(service, "_source_youtube_dl", source_youtube_dl)
    return calls


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (OutboundPolicyError(), "outbound_blocked"),
        (ControlledHttpStatusError(412), "source_http_error"),
    ],
)
def test_safe_source_terminal_error_is_rethrown_unchanged(monkeypatch, tmp_path, error, expected_code):
    calls = _install_source_failure(monkeypatch, error)

    with pytest.raises(type(error)) as raised:
        service.fetch_transcription_audio(URL, tmp_path)

    assert raised.value is error
    assert raised.value.code == expected_code
    assert not isinstance(raised.value, ASRError)
    assert len(calls) == 1 and calls[0][0] == URL
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("error_factory", "expected_type", "preserve_identity"),
    [
        (lambda: ASRError("transcription_duration", "bounded ASR error"), "transcription_duration", True),
        (lambda: SessionError("fixed session error"), service.ERROR_VERIFICATION, False),
        (lambda: service._BilibiliSourceError(service.ERROR_LOGIN), service.ERROR_LOGIN, False),
        (lambda: RuntimeError("synthetic private failure"), "transcription_fetch_failed", False),
    ],
)
def test_existing_asr_platform_and_generic_wrapping_is_preserved(
    monkeypatch, tmp_path, error_factory, expected_type, preserve_identity
):
    source_error = error_factory()
    calls = _install_source_failure(monkeypatch, source_error)

    with pytest.raises(ASRError) as raised:
        service.fetch_transcription_audio(URL, tmp_path)

    if preserve_identity:
        assert raised.value is source_error
    else:
        assert raised.value is not source_error
    assert raised.value.error_type == expected_type
    assert len(calls) == 1 and calls[0][0] == URL
    assert list(tmp_path.iterdir()) == []
