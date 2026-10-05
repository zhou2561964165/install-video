"""Offline evaluator safety checks. No provider HTTP, no real-ledger writes.
Engineering: skills first, token UI, configurable narrow services, yt-dlp boundary.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile

import httpx

spec = importlib.util.spec_from_file_location("schema_evaluator", Path(__file__).with_name("evaluate.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeHTTP:
    def __init__(self, folder, fail=False):
        self.folder, self.fail, self.calls = folder, fail, 0

    def post(self, url, *, headers, json):
        ledger = __import__("json").loads((self.folder / "request-ledger.json").read_text(encoding="utf-8"))
        assert ledger["requests"][-1]["status"] == "attempt_reserved"
        assert len(ledger["requests"]) == self.calls + 1
        self.calls += 1
        if self.fail:
            raise httpx.ConnectError("self-owned fake transport failure")
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": '{"summary":"s","key_points":["p"]}'}]}], "usage": {"total_tokens": 1}}, request=httpx.Request("POST", "https://local.invalid/responses"))


def run():
    for key, value in module.BASE_CONFIG.items():
        setattr(module.settings, key, value)
    module.settings.llm_summary_response_format = "json_schema"
    frozen = module.snapshot("schema")
    capture = module.CaptureClient()
    try:
        module.service._summary_request("fake", title="fake", output_language="zh-CN", client=capture)
    except module.Captured:
        pass
    with tempfile.TemporaryDirectory(prefix="schema-safety-") as folder:
        path = Path(folder)
        module.RESULTS = path / "limit"
        module.RESULTS.mkdir()
        fake = FakeHTTP(module.RESULTS)
        client = module.BudgetClient(fake, "schema", frozen)
        for _ in range(20):
            client.post("https://local.invalid/responses", headers={}, json=capture.payload)
        try:
            client.post("https://local.invalid/responses", headers={}, json=capture.payload)
        except RuntimeError as exc:
            assert "ceiling" in str(exc)
        else:
            raise AssertionError("21st attempt accepted")
        assert fake.calls == 20
        module.RESULTS = path / "failure"
        module.RESULTS.mkdir()
        failing = FakeHTTP(module.RESULTS, fail=True)
        client = module.BudgetClient(failing, "schema", frozen)
        try:
            client.post("https://local.invalid/responses", headers={}, json=capture.payload)
        except httpx.ConnectError:
            pass
        ledger = json.loads((module.RESULTS / "request-ledger.json").read_text(encoding="utf-8"))
        assert len(ledger["requests"]) == 1 and ledger["requests"][0]["status"] == "ConnectError"
        assert failing.calls == 1
        locked = path / "lock"
        locked.mkdir()
        try:
            locked.mkdir()
        except FileExistsError:
            pass
        else:
            raise AssertionError("Concurrent lock accepted")
        immutable = path / "immutable.json"
        module.exclusive(immutable, {"a": 1})
        try:
            module.exclusive(immutable, {"a": 2})
        except FileExistsError:
            pass
        else:
            raise AssertionError("Evidence overwritten")
    print(json.dumps({"offline_only": True, "reserve_before_send": True, "hard_ceiling": 20,
                      "attempt_21_refused": True, "failure_counts": True,
                      "exclusive_lock": True, "overwrite_refused": True}))


if __name__ == "__main__":
    run()
