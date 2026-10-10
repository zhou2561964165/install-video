"""The bounded follow-up freezes/replays marker normalization without networking."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-08-grounded-summary-marker/scripts/evaluate.py"


@pytest.fixture(params=["marker", "clause"])
def completed(tmp_path, monkeypatch, request):
    script = SCRIPT if request.param == "marker" else ROOT / "docs/acceptance-reports/2026-10-08-grounded-summary-clause/scripts/evaluate.py"
    prior_posts = 8 if request.param == "marker" else 12
    spec = importlib.util.spec_from_file_location("marker_fixture", script)
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    entry = wrapper.core
    for name, value in {"PROJECT": tmp_path, "RESULTS": tmp_path, "LEDGER": tmp_path / "ledger.json",
        "GROUP": tmp_path / "group.json", "CALLER_LOCK": tmp_path / "caller.lock"}.items():
        monkeypatch.setattr(entry, name, value)
    monkeypatch.setattr(entry.base, "PROJECT", tmp_path)
    previous = tmp_path / "previous.json"
    entry.base.exclusive(previous, {"phase": "normalized-retries", "ceiling": 19, "requests": [{}] * prior_posts})
    entry.base.exclusive(entry.GROUP, {"work_id": entry.WORK_ID, "hard_ceiling": 26,
        "initial_phase_ceiling": 19, "status": "closed", "phases": [{"phase": "normalized-retries",
        "ledger": str(previous), "ceiling": 19}]})
    from app.config import settings
    from app.services import llm_service
    from app.services.summary_facts import FactLimits
    for name, value in {**entry.CONFIG, "llm_model": "offline-model", "llm_provider": "compatible",
        "llm_base_url": "https://offline.invalid/v1", "llm_api_key": "", "llm_timeout_seconds": 20}.items():
        monkeypatch.setattr(settings, name, value)
    def runtime():
        entry.base.settings, entry.base.service, entry.base.FactLimits = settings, llm_service, FactLimits
        entry.base.REPORT, entry.base.RESULTS = entry.REPORT, entry.RESULTS
        entry.base.CONFIG, entry.base.MODULES = entry.CONFIG, entry.MODULES
    monkeypatch.setattr(entry, "load_runtime", runtime)
    wrapper.main(["--freeze"])
    original_client = httpx.Client
    facts = []
    def respond(request):
        row = entry.read(entry.LEDGER)["requests"][-1]
        assert row["status"] == "reserved"
        user = entry.read_user(json.loads(request.content))
        if row["stage"] == "extract":
            if user["source"]["id"] == "part1":
                facts.clear()
            claim = user["source"]["text"].splitlines()[0].split("] ", 1)[1]
            facts.append({"topic": "Source context", "claim": claim, "evidence": [1],
                "attribution": "source", "importance": "core"})
            output = {"type": "json_object", "fact_1": facts[-1]}
        else:
            candidate = {"summary": [{"text": f["claim"]} for f in facts],
                "key_points": [{"topic": f["topic"], "text": f["claim"]} for f in facts]}
            output = candidate if row["stage"] == "compose" else {"additional_facts": [], "output": candidate,
                "checks": [{"item_id": prefix + str(n), "supported": True, "qualifiers_preserved": True,
                    "attribution_preserved": True, "scope_preserved": True}
                    for prefix in ("S", "P") for n in range(1, len(facts) + 1)]}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(output)}}]})
    monkeypatch.setattr(entry.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(respond)))
    wrapper.main(["--run"])
    spec = importlib.util.spec_from_file_location("marker_checker_fixture", script.with_name("check_evidence.py"))
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(checker, "entry", entry)
    monkeypatch.setattr(checker.checker, "entry", entry)
    frozen_runtime = checker.checker.frozen_runtime
    def offline_frozen_runtime(frozen):
        runtime, added = frozen_runtime(frozen)
        runtime.settings.llm_base_url = "https://offline.invalid/v1"
        return runtime, added
    monkeypatch.setattr(checker.checker, "frozen_runtime", offline_frozen_runtime)
    return wrapper, checker


def test_marker_followup_has_zero_repair_posts_and_binds_prior_work_budget(completed):
    wrapper, checker = completed
    result = checker.checker.check_phase()
    expected_ceiling = 16 if wrapper.PHASE == "normalized-marker" else 13
    expected_count = 21 if wrapper.PHASE == "normalized-marker" else 25
    assert result["posts"] == 13 and result["ceiling"] == expected_ceiling
    assert all(row["status"] == "completed" for row in result["samples"])
    assert all(row["retry_budget"]["used"] == 0 for row in result["samples"])
    group, count = wrapper.validate_group()
    assert count == expected_count and [p["ceiling"] for p in group["phases"]] == [19, expected_ceiling]
    with pytest.raises(RuntimeError):
        wrapper.main(["--run"])


def test_followup_ceiling_cannot_be_relabelled_to_initial_ceiling(completed):
    wrapper, checker = completed
    entry = wrapper.core
    path = entry.RESULTS / f"{entry.PHASE}-provenance.json"
    frozen = entry.read(path)
    frozen["ceiling"] = 19
    entry.base.durable(path, frozen)
    with pytest.raises(RuntimeError, match="identity"):
        checker.checker.check_phase()


def test_followup_rejects_ledger_outside_temporary_project(completed):
    wrapper, _ = completed
    entry = wrapper.core
    assert entry.PROJECT == entry.base.PROJECT
    group = entry.read(entry.GROUP)
    group["phases"][0]["ledger"] = str(entry.PROJECT.parent / "escaped-ledger.json")
    entry.base.durable(entry.GROUP, group)
    with pytest.raises(RuntimeError, match="ledger path"):
        wrapper.validate_group()
