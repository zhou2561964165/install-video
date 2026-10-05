"""Exercise evaluation reservation/failure/ceiling guards with zero network.

Engineering: applicable skills first, UI skills/tokens, narrow interfaces and
configuration; yt-dlp only ytdlp_service, LLM only llm_service; scene read-only.
MIT derivatives retain original attribution and CC BY-NC-SA4.0.
"""
import importlib.util
import json
from pathlib import Path
import tempfile

import httpx

SCRIPT = Path(__file__).with_name("evaluate.py")
spec = importlib.util.spec_from_file_location("grounded_evaluation_runner", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class FakeHTTP:
    def __init__(self, failure=False):
        self.sent = 0
        self.failure = failure

    def post(self, url, *, headers, json):
        ledger = runner.json_module.loads((runner.RESULTS / "request-ledger.json").read_text(encoding="utf-8"))
        assert ledger["requests"][-1]["status"] == "reserved"
        assert len(ledger["requests"]) >= self.sent + 1
        self.sent += 1
        if self.failure:
            raise httpx.ConnectError("Synthetic offline failure")
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                                        "usage": {"total_tokens": 0}}, request=httpx.Request("POST", url))


def main():
    for key, value in runner.CONFIG.items():
        setattr(runner.settings, key, value)
    frozen = runner.snapshot()
    payload = {"model": frozen["model"], "temperature": 0.2, "max_tokens": 4096,
               **frozen["options"], "messages": [{"role": "system", "content": frozen["stage_prompts"]["extract"]},
                                                  {"role": "user", "content": "{}"}]}
    with tempfile.TemporaryDirectory(prefix="grounded-budget-") as directory:
        runner.RESULTS = Path(directory)
        http = FakeHTTP()
        for _ in range(24):
            client = runner.BudgetClient(http, "initial", frozen)
            client.sample = "zh-short"
            client.post("https://offline.invalid/chat/completions", headers={}, json=payload)
        blocked = runner.BudgetClient(http, "initial", frozen); blocked.sample = "zh-short"
        try:
            blocked.post("https://offline.invalid/chat/completions", headers={}, json=payload)
            raise AssertionError("25th POST not blocked")
        except RuntimeError as exc:
            assert "ceiling" in str(exc)
        assert http.sent == 24
    with tempfile.TemporaryDirectory(prefix="grounded-budget-failure-") as directory:
        runner.RESULTS = Path(directory)
        http = FakeHTTP(failure=True)
        client = runner.BudgetClient(http, "initial", frozen); client.sample = "zh-short"
        try:
            client.post("https://offline.invalid/chat/completions", headers={}, json=payload)
        except httpx.ConnectError:
            pass
        ledger = json.loads((runner.RESULTS / "request-ledger.json").read_text(encoding="utf-8"))
        assert len(ledger["requests"]) == http.sent == 1
        assert ledger["requests"][0]["status"] == "ConnectError"
        client.sample_post = 3
        try:
            client.post("https://offline.invalid/chat/completions", headers={}, json=payload)
            raise AssertionError("Hidden retry permitted")
        except RuntimeError as exc:
            assert "Unplanned" in str(exc)
        assert http.sent == 1
        client.sample_post = 0
        changed = dict(payload); changed["max_tokens"] = 1
        try:
            client.post("https://offline.invalid/chat/completions", headers={}, json=changed)
            raise AssertionError("Option change permitted")
        except RuntimeError as exc:
            assert "options" in str(exc)
        assert http.sent == 1
        first = runner.RESULTS / "lock"; first.mkdir()
        try:
            first.mkdir(); raise AssertionError("Second caller acquired lock")
        except FileExistsError:
            pass
    print(json.dumps({"offline": True, "actual_network_posts": 0,
                      "durable_reservation_observed_before_fake_send": True,
                      "failure_consumes_reservation": True, "ceiling_25th_refused": True,
                      "hidden_retry_refused": True, "options_change_refused": True,
                      "second_caller_lock_refused": True}))


if __name__ == "__main__":
    main()
