"""One isolated metadata operation; private stdin snapshot, bounded safe stdout."""
import json
from dataclasses import asdict
import os
import signal
import sys
import threading

from .services.bilibili_session import cookie_snapshot_scope, SessionError
from .services.outbound_budget import BudgetProfile, OutboundBudget
from .services.outbound_policy import OutboundError
from .services.source_broker import (MAX_REQUEST, MAX_RESPONSE, MAX_SUBTITLE_RESPONSE, SourceBrokerError, _decode,
                                     _encode, _prctl, error_response, validate_request)
from .services.source_network import make_runtime_source_network, source_network_scope
from .services.ytdlp_service import parse_video as source_parse_video
from .services.ytdlp_service import safe_bilibili_error_category
from .services.subtitle_service import fetch_subtitle_document as source_fetch_subtitle_document, SubtitleServiceError
from .services.outbound_httpx import ControlledHttpError


def execute(payload):
    try:
        if type(payload) is not dict or 'bili_cookie_snapshot' not in payload:
            raise SourceBrokerError()
        request = validate_request({key: value for key, value in payload.items() if key != 'bili_cookie_snapshot'})
        if request['op'] not in {'parse', 'subtitle'}:
            raise SourceBrokerError()
        budget = OutboundBudget(BudgetProfile.subtitle() if request['op'] == 'subtitle' else BudgetProfile.resolve())
        network = make_runtime_source_network(budget)
        with cookie_snapshot_scope(payload['bili_cookie_snapshot']), source_network_scope(network):
            if request['op'] == 'subtitle':
                document = source_fetch_subtitle_document(request['url'], request['language'], network=network)
                result = {'version': 1, 'ok': True, 'document': asdict(document)}
            else:
                meta, options = source_parse_video(request['url'])
                result = {'version': 1, 'ok': True, 'meta': meta, 'options': options}
        _encode(result, MAX_SUBTITLE_RESPONSE if request['op'] == 'subtitle' else MAX_RESPONSE)
        return result
    except OutboundError as error:
        return error_response(error.code)
    except ControlledHttpError as error:
        return error_response(error.code)
    except SubtitleServiceError as error:
        return error_response(error.error_type)
    except SessionError:
        return error_response('verification_required')
    except Exception as error:
        category = safe_bilibili_error_category(error)
        if category is not None:
            return error_response(category)
        return error_response()


def _watch_parent():
    while sys.stdin.buffer.read(1024):
        pass
    os.killpg(0, signal.SIGKILL)


def main():
    try:
        if os.name != 'posix':
            raise SourceBrokerError()
        _prctl(1, signal.SIGKILL)
        if os.getppid() != int(os.environ.get('SOURCE_BROKER_PARENT_PID', '0')):
            raise SourceBrokerError()
        raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST or not raw.endswith(b'\n'):
            raise SourceBrokerError()
        threading.Thread(target=_watch_parent, daemon=True).start()
        result = execute(_decode(raw))
    except Exception:
        result = error_response()
    maximum = MAX_SUBTITLE_RESPONSE if 'document' in result else MAX_RESPONSE
    sys.stdout.buffer.write(_encode(result, maximum))
    sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    # Do not finalize CPython while the liveness thread is blocked on buffered stdin.
    os._exit(main())
