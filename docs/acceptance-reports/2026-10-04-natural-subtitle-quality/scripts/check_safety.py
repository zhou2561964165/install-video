"""Offline-only checks of evaluation reservations, hard ceiling and immutability.

Uses a temporary ledger and local HTTP double; makes zero provider requests.
Engineering: skills outrank plans; UI skills and three-layer tokens; configurable
abilities; narrow services; yt-dlp only in ytdlp_service.py; visuals read-only.
"""
import importlib.util
import json
from pathlib import Path
import tempfile

import httpx

spec = importlib.util.spec_from_file_location("natural_evaluate", Path(__file__).with_name("evaluate.py"))
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


class LocalHTTP:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def post(self, url, **kwargs):
        self.calls += 1
        ledger = json.loads((evaluate.RESULTS / "request-ledger.json").read_text())
        assert len(ledger["requests"]) == self.calls
        assert ledger["requests"][-1]["status"] == "attempt_reserved"
        if self.fail:
            raise httpx.ConnectError("offline failure")
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '{"summary":"Source fact","key_points":["Source fact"]}'}}],
            "usage": {"total_tokens": 1}}, request=httpx.Request("POST", url))


def main():
    frozen = {"service_sha256": evaluate.digest(evaluate.SERVICE.read_bytes()),
              "system_prompt_sha256": evaluate.digest(evaluate.system_prompt())}
    payload = {"messages": [{"content": evaluate.system_prompt()}, {"content": "Transcript:\nSource fact"}]}
    with tempfile.TemporaryDirectory() as directory:
        evaluate.RESULTS = Path(directory)
        local = LocalHTTP()
        client = evaluate.BudgetClient(local, "before", frozen)
        for _ in range(24):
            client.post("https://offline.invalid", headers={}, json=payload)
        try:
            client.post("https://offline.invalid", headers={}, json=payload)
        except RuntimeError:
            pass
        else:
            raise AssertionError("25th call reached local HTTP")
        assert local.calls == 24
        assert len(list((evaluate.RESULTS / "responses").glob("*.json"))) == 24
        try:
            evaluate.exclusive_json(evaluate.RESULTS / "responses/01.json", {})
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing output was overwritten")
    with tempfile.TemporaryDirectory() as directory:
        evaluate.RESULTS = Path(directory)
        local = LocalHTTP(fail=True)
        client = evaluate.BudgetClient(local, "before", frozen)
        try:
            client.post("https://offline.invalid", headers={}, json=payload)
        except httpx.ConnectError:
            pass
        else:
            raise AssertionError("Expected local failure")
        ledger = json.loads((evaluate.RESULTS / "request-ledger.json").read_text())
        assert local.calls == 1 and len(ledger["requests"]) == 1
        assert ledger["requests"][0]["status"] == "ConnectError"
    print(json.dumps({"provider_http_posts": 0, "reservation_precedes_local_http": True,
                      "twenty_fifth_blocked": True, "failure_consumes_reservation": True,
                      "result_overwrite_blocked": True}))


if __name__ == "__main__":
    main()
