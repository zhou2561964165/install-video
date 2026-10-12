"""Local repair acceptance reuses isolated guards and a synthetic HTTP transport.

Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only through ytdlp_service; scene remains read-only. No provider or dotenv.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-11-summary-content-local-repair/scripts/evaluate.py"
PRIOR_TEST = ROOT / "backend/tests/test_summary_resume_evaluation.py"
spec = importlib.util.spec_from_file_location("repair_resume_fixture", PRIOR_TEST)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
source = prior.source


@pytest.fixture
def entry(tmp_path, monkeypatch):
    assert SCRIPT.exists(), "Local repair acceptance entry is missing"
    monkeypatch.setattr(prior, "SCRIPT", SCRIPT)
    module = prior.entry.__wrapped__(tmp_path, monkeypatch)
    norm = tmp_path / "backend/app/services/summary_json.py"
    norm.write_bytes((ROOT / "backend/app/services/summary_json.py").read_bytes())
    original = module.asset_paths
    monkeypatch.setattr(module, "asset_paths", lambda: original() + [norm])
    module.test_norm = norm
    return module


# Exercise the same existing preallocation, crash recovery, drift, raw/source
# and closed phase checks against the second private adapter.
for name in dir(source):
    if name.startswith("test_"):
        function = getattr(source, name)
        function.__module__ = __name__
        globals()[name] = function


def malformed_response(n, *, incomplete=False):
    value = {"summary": f" Complete overview {n} ",
        "key_points": [f" Complete condition {n}. ", "Preserved final point."]}
    content = json.dumps(value, ensure_ascii=False)
    content = content[:-2] + "}" if not incomplete else content[:-4]
    return httpx.Response(200, request=httpx.Request("POST", "https://offline.invalid"),
        json={"model": "offline-model", "usage": {"total_tokens": 3},
            "choices": [{"finish_reason": "stop", "message": {"content": content,
                "reasoning_content": "DO-NOT-SAVE"}}]})


def test_complete_malformed_final_preserves_every_value_and_posts(entry):
    source.ready(entry)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        return malformed_response(len(calls))
    index = entry.run(transport=SimpleNamespace(post=post))
    assert calls == [1] * 5 and not index["stopped_on_error"]
    final = entry.read(entry.RESULTS / "en-long.json")["result"]
    assert final["summary"] == "Complete overview 5"
    assert final["key_points"] == ["Complete condition 5.", "Preserved final point."]
    merged = entry.read(entry.RESULTS / "payload-05.json")["messages"][1]["content"]
    assert "Complete condition 3." in merged and "Complete condition 4." in merged
    assert merged.count("Preserved final point.") == 2
    assert entry.verify_results()["posts"] == 5


def test_incomplete_raw_string_stops_with_one_reserved_attempt(entry):
    source.ready(entry)
    calls = []
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **kw:
        calls.append(1) or malformed_response(1, incomplete=True)))
    assert calls == [1] and index["stopped_on_error"] and index["posts"] == 1
    assert entry.read(entry.TRACKER)["status"] == "closed"
    assert entry.verify_results()["posts"] == 1


def test_frozen_normalizer_live_drift_blocks_before_http(entry):
    source.ready(entry)
    entry.test_norm.write_text("raise RuntimeError('mutable normalizer')")
    calls = []
    with pytest.raises(RuntimeError, match="Live asset"):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: calls.append(1)))
    assert calls == [] and entry.read(entry.TRACKER)["status"] == "closed"


def test_verify_uses_frozen_normalizer_without_runtime_after_live_change(entry, monkeypatch):
    source.ready(entry)
    calls = []
    entry.run(transport=SimpleNamespace(post=lambda *a, **kw:
        calls.append(1) or malformed_response(len(calls))))
    entry.test_norm.write_text("raise RuntimeError('mutable normalizer')")
    monkeypatch.setattr(entry, "runtime", lambda: pytest.fail("Verify read dotenv"))
    assert entry.verify_results()["posts"] == 5


def test_same_group_preserves_closed_phase_one_and_reaches_ten(entry):
    closed = {"phase": "summary-thinking-single-1", "status": "closed", "reserved_posts": 5}
    group = entry.read(entry.GROUP)
    group.update(reserved_posts=5, phases=[closed])
    entry.io.durable(entry.GROUP, group)
    original_closed = json.dumps(closed, sort_keys=True)
    source.ready(entry)
    assert entry.read(entry.RESULTS / "provenance.json")["parent_posts"] == 5
    calls = []
    index = entry.run(transport=SimpleNamespace(post=lambda *a, **kw:
        calls.append(1) or malformed_response(len(calls))))
    group = entry.read(entry.GROUP)
    assert len(calls) == index["posts"] == 5 and group["reserved_posts"] == 10
    assert group["status"] == "closed"
    assert json.dumps(group["phases"][0], sort_keys=True) == original_closed
    assert entry.verify_results()["work_posts"] == 10
    with pytest.raises(RuntimeError, match="never reopen"):
        entry.run(transport=SimpleNamespace(post=lambda *a, **kw: pytest.fail("Reopened")))


def test_repair_paths_config_and_inventory_preserve_phase_one():
    spec = importlib.util.spec_from_file_location("repair_path_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.GROUP == ROOT / ".planning/2026-10-11-summary-content-resume/budget-group.json"
    assert module.TRACKER == module.GROUP.with_name("phase-2.json")
    assert module.WORK_ID == "summary-content-resume-20261011"
    assert module.PHASE == "summary-thinking-local-json-2"
    assert module.SHARED_LOCK == ROOT / "docs/acceptance-reports/2026-10-05-grounded-summary/results/.http-session-lock"
    assert module.CONFIG == module.prior.CONFIG
    assets = module.inventory_paths()
    assert SCRIPT in assets and PRIOR_TEST in assets
    assert ROOT / "backend/app/services/summary_json.py" in assets
    assert Path(__file__) in assets
    parent_report = ROOT / "docs/acceptance-reports/2026-10-11-summary-content-resume"
    assert {parent_report / "results" / name for name in
        ("closed-receipt.json", "request-ledger.json", "result-index.json", "provenance.json")} <= set(assets)
    assert module.GROUP.with_name("phase-1.json") in assets
