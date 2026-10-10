"""Offline evaluator contracts; skills first, configurable limits, narrow interfaces.

Engineering: UI ui-ux-pro-max/design-system and three-layer tokens; yt-dlp only
ytdlp_service, LLM only llm_service, read-only scene; no competing plan files.
"""
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import socket
import os
import sys
from types import ModuleType
from types import SimpleNamespace

import dotenv
import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "docs/acceptance-reports/2026-10-05-grounded-summary-evidence/scripts/evaluate.py"
WRAPPER_PATH = ROOT / "docs/acceptance-reports/2026-10-07-grounded-summary-organization/scripts/evaluate.py"
URL = "https://offline.invalid/v1/chat/completions"


def load(path, name):
    assert path.exists(), "organization entrypoint must exist"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("tests must never read .env or access the network")
    monkeypatch.setattr(dotenv, "load_dotenv", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@dataclass
class Limits:
    max_facts_per_chunk: int = 12
    max_evidence_sentences: int = 128
    max_point_chars: int = 240
    max_summary_chars: int = 4000


def isolate(base, tmp_path, monkeypatch, config):
    report = tmp_path / "evidence"
    report.mkdir()
    (report / "rubric.json").write_text(json.dumps({"baseline": {"sample_results": []}}))
    corpus = tmp_path / "source/corpus"
    corpus.mkdir(parents=True)
    samples = []
    for name, text in [("short", "a"), ("medium", "b"), ("long", "c|d|e|f|g")]:
        (corpus / f"{name}.txt").write_text(text)
        samples.append({"id": name, "file": f"{name}.txt", "sha256": base.digest(text), "title": name})
    (corpus / "manifest.json").write_text(json.dumps({"samples": samples}))
    modules = {}
    for name in ("service", "facts", "config"):
        modules[name] = tmp_path / f"{name}.py"
        modules[name].write_text('VALUE = "frozen fixture"\n')
    settings = SimpleNamespace(**config, llm_provider="offline", llm_model="offline-model")
    service = SimpleNamespace(
        _summary_input=lambda text: text,
        _summary_chunks=lambda text, size: text.split("|"),
        _summary_options=lambda: {},
        _grounded_system=lambda stage, limits: f"{stage}: summary <= {limits.max_summary_chars}",
        _grounded_max_tokens=lambda stage: (
            getattr(settings, f"llm_summary_facts_{stage}_max_output_tokens", 0)
            or settings.llm_summary_max_output_tokens),
    )
    for key, value in {"CONFIG": config, "REPORT": report, "RESULTS": report / "results", "OLD": corpus.parent,
                       "BASE": tmp_path / "baseline", "PRIOR": tmp_path / "prior",
                       "SHARED_LEDGER": tmp_path / "prior/results/request-ledger.json",
                       "MODULES": modules, "settings": settings, "service": service,
                       "FactLimits": Limits}.items():
        monkeypatch.setattr(base, key, value)
    return base


@pytest.fixture
def base(tmp_path, monkeypatch):
    return isolate(load(BASE_PATH, "base_organization_test"), tmp_path, monkeypatch, {
        **load(BASE_PATH, "base_config_test").CONFIG,
        "llm_summary_facts_max_summary_chars": 800,
        "llm_summary_facts_compose_max_output_tokens": 8192,
        "llm_summary_facts_audit_max_output_tokens": 0,
    })


@pytest.fixture
def wrapper(tmp_path, monkeypatch):
    wrapper = load(WRAPPER_PATH, "organization_test")
    isolate(wrapper.base, tmp_path, monkeypatch, wrapper.CONFIG)
    monkeypatch.setattr(wrapper, "REPORT", tmp_path / "organization")
    monkeypatch.setattr(wrapper, "RESULTS", tmp_path / "organization/results")
    monkeypatch.setattr(wrapper, "LEDGER", tmp_path / "organization/results/request-ledger.json")
    monkeypatch.setattr(wrapper, "CALLER_LOCK", tmp_path / "prior/results/.http-session-lock")
    monkeypatch.setattr(wrapper, "load_runtime", lambda: None)
    wrapper.REPORT.mkdir()
    (wrapper.REPORT / "rubric.json").write_bytes((wrapper.base.REPORT / "rubric.json").read_bytes())
    return wrapper


def payload(frozen, stage, tokens):
    return {"model": "offline-model", "temperature": 0.2, "max_tokens": tokens,
            "messages": [{"role": "system", "content": frozen["stage_prompts"][stage]}]}


def test_base_snapshot_freezes_summary_limit_and_resolved_stage_budgets(base, monkeypatch):
    monkeypatch.setattr(base, "CONFIG", {**base.CONFIG,
        "llm_summary_facts_max_summary_chars": 800,
        "llm_summary_facts_compose_max_output_tokens": 8192,
        "llm_summary_facts_audit_max_output_tokens": 0})
    frozen = base.snapshot()
    assert frozen["fact_limits"]["max_summary_chars"] == 800
    assert frozen["stage_prompts"]["compose"] == "compose: summary <= 800"
    assert frozen["stage_max_output_tokens"] == {"extract": 4096, "compose": 8192, "audit": 4096}
    assert frozen["config"]["llm_summary_facts_audit_max_output_tokens"] == 0


@pytest.mark.parametrize("stage, position, tokens", [("extract", 0, 4096), ("compose", 1, 8192), ("audit", 2, 8192)])
def test_base_checks_tokens_for_actual_stage_before_reservation(base, stage, position, tokens):
    frozen = {"module_sha256": {k: base.digest(p.read_bytes()) for k, p in base.MODULES.items()},
              "rubric_sha256": base.digest((base.REPORT / "rubric.json").read_bytes()),
              "samples": [{"id": "short", "sections": 1, "expected_posts": 3}],
              "model": "offline-model", "options": {},
              "stage_prompts": {s: s for s in ("extract", "compose", "audit")},
              "stage_max_output_tokens": {"extract": 4096, "compose": 8192, "audit": 8192}}
    sent = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200, json={}))) as http:
        client = base.BudgetClient(http, "test", frozen)
        client.sample, client.sample_post = "short", position
        with pytest.raises(RuntimeError, match="options"):
            client.post(URL, headers={}, json=payload(frozen, stage, tokens + 1))
        assert not base.SHARED_LEDGER.exists()
        assert client.post(URL, headers={}, json=payload(frozen, stage, tokens)).is_success
    assert len(sent) == 1
    assert json.loads(base.SHARED_LEDGER.read_text())["requests"][0]["stage"] == stage


def test_base_main_accepts_explicit_phase_choices_without_loading_runtime(base):
    # --help exits before imports or dotenv, so this exercises parser construction.
    with pytest.raises(SystemExit) as exc:
        base.main(["--help"], phase_choices=["organization-slots"])
    assert exc.value.code == 0


def test_default_plan_never_initializes_runtime_or_writes_results(wrapper, monkeypatch, capsys):
    monkeypatch.setattr(wrapper, "load_runtime", lambda: pytest.fail("plan loaded runtime"))
    wrapper.main([])
    plan = json.loads(capsys.readouterr().out)
    assert plan["phase"] == "organization-slots"
    assert plan["ceiling"] == 13
    assert plan["config"]["llm_max_input_chars"] == 100000
    assert plan["config"]["llm_summary_facts_max_summary_chars"] == 800
    assert plan["stage_max_output_tokens"] == {"extract": 4096, "compose": 8192, "audit": 8192}
    assert not wrapper.RESULTS.exists()


def test_explicit_runtime_loads_environment_before_resolving_model(monkeypatch, tmp_path):
    entry = load(WRAPPER_PATH, "organization_runtime_order_test")
    monkeypatch.setattr(entry.base, "PROJECT", tmp_path)
    monkeypatch.setenv("LLM_MODEL", "")
    events = []
    def fake_dotenv(path, override):
        assert path == tmp_path / "backend/.env"
        assert override is False
        events.append("dotenv")
        monkeypatch.setenv("LLM_MODEL", "profile-env-model")
    monkeypatch.setattr(entry.base, "load_dotenv", fake_dotenv)
    class Config(ModuleType):
        def __getattr__(self, name):
            if name != "settings":
                raise AttributeError(name)
            events.append("settings")
            return SimpleNamespace(**entry.CONFIG, llm_model=os.environ.get("LLM_MODEL"))
    monkeypatch.setitem(sys.modules, "app.config", Config("app.config"))
    entry.load_runtime()
    assert entry.base.settings.llm_model == "profile-env-model"
    assert events[0] == "dotenv"


@pytest.mark.parametrize("flags", [["--freeze", "--run"], ["--check-only", "--run"], ["--freeze", "--check-only"]])
def test_modes_are_mutually_exclusive_before_runtime(wrapper, flags):
    with pytest.raises(SystemExit) as exc:
        wrapper.main(flags)
    assert exc.value.code == 2
    assert not wrapper.RESULTS.exists()


def test_freeze_and_check_use_independent_results_without_live_main(wrapper, monkeypatch, capsys):
    monkeypatch.setattr(wrapper.base, "main", lambda *a, **k: pytest.fail("offline mode called live main"))
    wrapper.main(["--freeze"])
    frozen_path = wrapper.RESULTS / "organization-slots-provenance.json"
    frozen = json.loads(frozen_path.read_text())
    assert frozen["expected_posts"] == 13
    assert [s["expected_posts"] for s in frozen["samples"]] == [3, 3, 7]
    assert frozen["ceiling"] == 13
    assert frozen["entrypoint_sha256"] == wrapper.base.digest(WRAPPER_PATH.read_bytes())
    assert frozen["runner_sha256"] == wrapper.base.digest(BASE_PATH.read_bytes())
    assert frozen["fact_limits"]["max_summary_chars"] == 800
    assert not wrapper.LEDGER.exists()
    assert not (wrapper.base.PRIOR / "results/request-ledger.json").exists()
    wrapper.main(["--check-only"])
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["match"] is True
    original = frozen_path.read_bytes()
    with pytest.raises(FileExistsError):
        wrapper.main(["--freeze"])
    assert frozen_path.read_bytes() == original


@pytest.mark.parametrize("drift", ["source", "manifest", "config", "prompt", "codec", "budget", "entrypoint", "runner", "rubric"])
def test_post_rechecks_complete_freeze_before_any_reservation(wrapper, monkeypatch, drift):
    frozen = wrapper.snapshot()
    if drift == "source":
        (wrapper.base.OLD / "corpus/short.txt").write_text("changed")
    elif drift == "manifest":
        path = wrapper.base.OLD / "corpus/manifest.json"
        path.write_text(path.read_text() + "\n")
    elif drift == "config":
        wrapper.base.settings.llm_max_input_chars = 60000
    elif drift == "prompt":
        wrapper.base.service._grounded_system = lambda *a: "changed"
    elif drift == "codec":
        wrapper.base.MODULES["facts"].write_text('VALUE = "changed"\n')
    elif drift == "budget":
        wrapper.base.service._grounded_max_tokens = lambda stage: 1
    elif drift == "rubric":
        (wrapper.REPORT / "rubric.json").write_text('{"baseline": {"sample_results": []}, "changed": true}')
    else:
        frozen["entrypoint_sha256" if drift == "entrypoint" else "runner_sha256"] = "changed"
    sent = []
    with wrapper.configured_base():
        with httpx.Client(transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200, json={}))) as http:
            client = wrapper.base.BudgetClient(http, wrapper.PHASE, frozen)
            client.sample = "short"
            with pytest.raises(RuntimeError):
                client.post(URL, headers={}, json=payload(frozen, "extract", 4096))
    assert sent == []
    assert not wrapper.LEDGER.exists()


def test_shared_caller_lock_excludes_new_entrypoint_but_ledger_lock_is_independent(wrapper):
    wrapper.CALLER_LOCK.mkdir(parents=True)
    frozen = wrapper.snapshot()
    with wrapper.configured_base():
        with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("locked send"))) as http:
            client = wrapper.base.BudgetClient(http, wrapper.PHASE, frozen)
            client.sample = "short"
            with pytest.raises(FileExistsError):
                client.post(URL, headers={}, json=payload(frozen, "extract", 4096))
        with wrapper.base.ledger_guard():
            assert (wrapper.RESULTS / "ledger.lock").exists()
            assert not (wrapper.CALLER_LOCK.parent / "ledger.lock").exists()
    assert wrapper.CALLER_LOCK.is_dir()
    assert not wrapper.LEDGER.exists()


@pytest.mark.parametrize("used, ceiling", [(1, 13), (13, 13), (0, 49)])
def test_run_refuses_insufficient_or_wrong_ledger_before_live_main(wrapper, monkeypatch, used, ceiling):
    wrapper.main(["--freeze"])
    wrapper.base.exclusive(wrapper.LEDGER, {"ceiling": ceiling, "requests": [{} for _ in range(used)]})
    before = wrapper.LEDGER.read_bytes()
    monkeypatch.setattr(wrapper.base, "main", lambda *a, **k: pytest.fail("insufficient budget delegated live main"))
    with pytest.raises(RuntimeError, match="budget|ceiling"):
        wrapper.main(["--run"])
    assert wrapper.LEDGER.read_bytes() == before
    assert not (wrapper.RESULTS / "organization-slots-started.json").exists()


def test_run_with_full_budget_delegates_only_explicit_new_phase(wrapper, monkeypatch):
    wrapper.main(["--freeze"])
    delegated = []
    def simulate_live(argv=None, *, phase_choices):
        delegated.append((argv, phase_choices, wrapper.base.RESULTS, wrapper.base.SHARED_LEDGER, wrapper.base.CEILING))
        return "simulated"
    monkeypatch.setattr(wrapper.base, "main", simulate_live)
    assert wrapper.main(["--run"]) == "simulated"
    assert delegated == [(["--phase", "organization-slots"], ["organization-slots"], wrapper.RESULTS, wrapper.LEDGER, 13)]
    assert not wrapper.LEDGER.exists()


def test_failed_send_consumes_new_budget_once_and_never_touches_prior_ledger(wrapper):
    frozen = wrapper.snapshot()
    prior = wrapper.base.PRIOR / "results/request-ledger.json"
    wrapper.base.exclusive(prior, {"ceiling": 49, "requests": [{"status": "original"}]})
    original = prior.read_bytes()
    attempts = []
    def fail(request):
        attempts.append(request)
        assert json.loads(wrapper.LEDGER.read_text())["requests"][-1]["status"] == "reserved"
        raise httpx.ConnectError("private-error", request=request)
    with wrapper.configured_base():
        with httpx.Client(transport=httpx.MockTransport(fail)) as http:
            client = wrapper.base.BudgetClient(http, wrapper.PHASE, frozen)
            client.sample = "short"
            with pytest.raises(httpx.ConnectError):
                client.post(URL, headers={"Authorization": "secret"}, json=payload(frozen, "extract", 4096))
            # A hidden extract retry now has the compose ordinal and is refused.
            with pytest.raises(RuntimeError):
                client.post(URL, headers={}, json=payload(frozen, "extract", 4096))
    ledger = json.loads(wrapper.LEDGER.read_text())
    assert ledger["ceiling"] == 13
    assert len(ledger["requests"]) == len(attempts) == 1
    assert ledger["requests"][0]["status"] == "ConnectError"
    assert "private-error" not in wrapper.LEDGER.read_text()
    assert prior.read_bytes() == original


@pytest.mark.parametrize("failure", ["transport", "http", "invalid_json"])
def test_failure_in_long_extract_stops_further_sends_even_with_extract_slots_left(wrapper, failure):
    frozen = wrapper.snapshot()
    attempts = []
    def fail(request):
        attempts.append(request)
        if failure == "transport":
            raise httpx.ConnectError("private", request=request)
        if failure == "http":
            return httpx.Response(429, json={"error": {"type": "rate_limit_error"}})
        return httpx.Response(200, content=b"invalid-private-json")
    with wrapper.configured_base():
        with httpx.Client(transport=httpx.MockTransport(fail)) as http:
            client = wrapper.base.BudgetClient(http, wrapper.PHASE, frozen)
            client.sample = "long"
            if failure == "http":
                assert client.post(URL, headers={}, json=payload(frozen, "extract", 4096)).status_code == 429
            else:
                with pytest.raises((httpx.ConnectError, json.JSONDecodeError)):
                    client.post(URL, headers={}, json=payload(frozen, "extract", 4096))
            with pytest.raises(RuntimeError, match="stopped|failed"):
                client.post(URL, headers={}, json=payload(frozen, "extract", 4096))
    assert len(attempts) == 1
    assert len(json.loads(wrapper.LEDGER.read_text())["requests"]) == 1


def test_new_ceiling_refuses_fourteenth_send_and_counts_stages_in_own_ledger(wrapper):
    frozen = wrapper.snapshot()
    sent = []
    with wrapper.configured_base():
        with httpx.Client(transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200, json={}))) as http:
            client = wrapper.base.BudgetClient(http, wrapper.PHASE, frozen)
            for name, stages in [("short", ["extract", "compose", "audit"]),
                                 ("medium", ["extract", "compose", "audit"]),
                                 ("long", ["extract"] * 5 + ["compose", "audit"])]:
                client.sample, client.sample_post = name, 0
                for stage in stages:
                    assert client.post(URL, headers={}, json=payload(
                        frozen, stage, 4096 if stage == "extract" else 8192)).is_success
            next_client = wrapper.base.BudgetClient(http, wrapper.PHASE, frozen)
            next_client.sample = "short"
            with pytest.raises(RuntimeError, match="ceiling"):
                next_client.post(URL, headers={}, json=payload(frozen, "extract", 4096))
    rows = json.loads(wrapper.LEDGER.read_text())["requests"]
    assert len(rows) == len(sent) == 13
    assert [r["ordinal"] for r in rows] == list(range(1, 14))
    assert [r["stage"] for r in rows] == ["extract", "compose", "audit", "extract", "compose", "audit",
                                          "extract", "extract", "extract", "extract", "extract", "compose", "audit"]
    assert not (wrapper.base.PRIOR / "results/request-ledger.json").exists()


def test_standalone_new_budget_client_always_uses_new_ledger_without_binding_caller(wrapper):
    frozen = wrapper.snapshot()
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))) as http:
        client = wrapper.BudgetClient(http, wrapper.PHASE, frozen)
        client.sample = "short"
        assert client.post(URL, headers={}, json=payload(frozen, "extract", 4096)).is_success
    rows = json.loads(wrapper.LEDGER.read_text())["requests"]
    assert len(rows) == 1
    assert rows[0]["phase"] == "organization-slots"
    assert not (wrapper.base.PRIOR / "results/request-ledger.json").exists()
