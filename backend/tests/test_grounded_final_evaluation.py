"""Hermetic final acceptance guards; all artifacts belong to temporary fixtures.

Engineering: skills first; UI uses ui-ux-pro-max/design-system and three-layer
tokens; configurable narrow interfaces; LLM only llm_service, yt-dlp only
ytdlp_service, visual scene read-only. No production or historical writes.
"""
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
from types import ModuleType, SimpleNamespace

import dotenv
import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "docs/acceptance-reports"
ENTRY = REPORTS / "2026-10-07-grounded-summary-final/scripts/evaluate.py"
CHECKER = ENTRY.with_name("check_evidence.py")
ORGANIZATION = REPORTS / "2026-10-07-grounded-summary-organization/scripts/evaluate.py"
RUNNER = REPORTS / "2026-10-05-grounded-summary-evidence/scripts/evaluate.py"
CHECKER_RUNNER = RUNNER.with_name("check_evidence.py")
PHASE = "organization-final"
URL = "https://offline.invalid/v1/chat/completions"


def load(path, name):
    assert path.is_file(), "final acceptance entrypoint must exist"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("final tests must never read .env or access the network")
    monkeypatch.setattr(dotenv, "load_dotenv", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@dataclass
class Limits:
    max_facts_per_chunk: int = 12
    max_evidence_sentences: int = 128
    max_point_chars: int = 240
    max_summary_chars: int = 800


@pytest.fixture
def entry(tmp_path, monkeypatch, request):
    entry = load(ENTRY, "final_test_entry")
    base = entry.base
    report = tmp_path / "final"
    write(report / "rubric.json", {"baseline": {"sample_results": []}})
    corpus = tmp_path / "source/corpus"
    corpus.mkdir(parents=True)
    samples = []
    for name, text in [("short", "a"), ("medium", "b"), ("long", "c|d|e|f|g")]:
        (corpus / f"{name}.txt").write_text(text, encoding="utf-8")
        samples.append({"id": name, "file": f"{name}.txt", "sha256": sha(text), "title": name})
    write(corpus / "manifest.json", {"samples": samples})
    modules = {}
    for name in ("service", "facts", "config"):
        modules[name] = tmp_path / f"{name}.py"
        modules[name].write_text('VALUE = "frozen fixture"\n', encoding="utf-8")
    modules["service"].write_text(
        'def _summary_input(text):\n    return re.sub(r"\\s+", " ", text).strip()\n', encoding="utf-8")
    modules["facts"].write_text(
        'from dataclasses import dataclass\n@dataclass\nclass FactLimits:\n'
        '    max_facts_per_chunk: int = 12\n    max_evidence_sentences: int = 128\n'
        '    max_point_chars: int = 240\n    max_summary_chars: int = 800\n', encoding="utf-8")
    settings = SimpleNamespace(**entry.CONFIG, llm_provider="offline", llm_model="offline-model")
    service = SimpleNamespace(
        _summary_input=lambda text: text,
        _summary_chunks=lambda text, size: text.split("|"),
        _summary_options=lambda: {},
        _grounded_system=lambda stage, limits: f"{stage}: summary <= {limits.max_summary_chars}",
        _grounded_max_tokens=lambda stage: 4096 if stage == "extract" else 8192,
    )
    for key, value in {"REPORT": tmp_path / "base", "RESULTS": tmp_path / "base/results",
                       "OLD": corpus.parent, "BASE": tmp_path / "baseline", "PRIOR": tmp_path / "prior",
                       "SHARED_LEDGER": tmp_path / "prior/results/request-ledger.json",
                       "MODULES": modules, "settings": settings, "service": service,
                       "FactLimits": Limits}.items():
        monkeypatch.setattr(base, key, value)
    for key, value in {"REPORT": report, "RESULTS": report / "results",
                       "LEDGER": report / "results/request-ledger.json",
                       "CALLER_LOCK": tmp_path / "prior/results/.http-session-lock"}.items():
        monkeypatch.setattr(entry, key, value)
    for key, value in {"REPORT": tmp_path / "organization", "RESULTS": tmp_path / "organization/results",
                       "LEDGER": tmp_path / "organization/results/request-ledger.json"}.items():
        monkeypatch.setattr(entry.organization, key, value)
    write(entry.organization.REPORT / "rubric.json", {"baseline": {"sample_results": []}})
    if getattr(request, "param", None) != "runtime":
        monkeypatch.setattr(entry.organization, "load_runtime", lambda: None)
    return entry


def payload(frozen, stage="extract", tokens=4096):
    return {"model": "offline-model", "temperature": 0.2, "max_tokens": tokens,
            "messages": [{"role": "system", "content": frozen["stage_prompts"][stage]}]}


def test_default_plan_is_independent_and_never_loads_runtime(entry, monkeypatch, capsys):
    monkeypatch.setattr(entry.organization, "load_runtime", lambda: pytest.fail("default loaded runtime"))
    entry.main([])
    plan = json.loads(capsys.readouterr().out)
    assert plan["phase"] == PHASE
    assert plan["ledger"] == str(entry.LEDGER)
    assert plan["ceiling"] == plan["expected_posts"] == 13
    assert plan["network"] is False
    assert plan["config"]["llm_max_input_chars"] == 100000
    assert plan["config"]["llm_summary_facts_max_summary_chars"] == 800
    assert plan["stage_max_output_tokens"] == {"extract": 4096, "compose": 8192, "audit": 8192}
    assert not entry.RESULTS.exists()


@pytest.mark.parametrize("flags", [["--freeze", "--run"], ["--check-only", "--run"], ["--freeze", "--check-only"]])
def test_modes_reject_conflicts_before_loading_runtime(entry, monkeypatch, flags):
    monkeypatch.setattr(entry.organization, "load_runtime", lambda: pytest.fail("conflict loaded runtime"))
    with pytest.raises(SystemExit) as exc:
        entry.main(flags)
    assert exc.value.code == 2
    assert not entry.RESULTS.exists()


def test_freeze_and_check_bind_both_wrappers_and_leave_old_results_untouched(entry, monkeypatch, capsys):
    monkeypatch.setattr(entry.base, "main", lambda *a, **k: pytest.fail("offline delegated live runner"))
    entry.main(["--freeze"])
    path = entry.RESULTS / f"{PHASE}-provenance.json"
    frozen = json.loads(path.read_text())
    assert frozen["phase"] == PHASE
    assert frozen["entrypoint_sha256"] == sha(ENTRY.read_bytes())
    assert frozen["organization_wrapper_sha256"] == sha(ORGANIZATION.read_bytes())
    assert frozen["runner_sha256"] == sha(RUNNER.read_bytes())
    assert frozen["evidence_checker_sha256"] == sha(CHECKER.read_bytes())
    assert frozen["evidence_checker_runner_sha256"] == sha(CHECKER_RUNNER.read_bytes())
    assert frozen["ledger"] == str(entry.LEDGER)
    assert frozen["caller_lock"] == str(entry.CALLER_LOCK)
    assert [s["expected_posts"] for s in frozen["samples"]] == [3, 3, 7]
    assert not entry.LEDGER.exists()
    assert not entry.base.SHARED_LEDGER.exists()
    assert not entry.organization.RESULTS.exists()
    entry.main(["--check-only"])
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["match"] is True
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        entry.main(["--freeze"])
    assert path.read_bytes() == original


@pytest.mark.parametrize("entry", ["runtime"], indirect=True)
def test_explicit_freeze_uses_org_environment_loading_before_model_resolution(entry, tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(entry.base, "PROJECT", tmp_path)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setenv("LLM_MODEL", "")
    def fake_dotenv(path, override):
        assert path == tmp_path / "backend/.env"
        assert override is False
        events.append("dotenv")
        monkeypatch.setenv("LLM_MODEL", "fixture-env-model")
    monkeypatch.setattr(entry.base, "load_dotenv", fake_dotenv)
    resolved_settings = SimpleNamespace(**entry.CONFIG, llm_provider="offline", llm_model=None)
    class Config(ModuleType):
        def __getattr__(self, name):
            if name != "settings":
                raise AttributeError(name)
            events.append("settings")
            resolved_settings.llm_model = os.environ["LLM_MODEL"]
            return resolved_settings
    app = ModuleType("app")
    app.__path__ = []
    services = ModuleType("app.services")
    services.__path__ = []
    services.llm_service = entry.base.service
    facts = ModuleType("app.services.summary_facts")
    facts.FactLimits = Limits
    for name, module in {"app": app, "app.config": Config("app.config"),
                         "app.services": services, "app.services.summary_facts": facts}.items():
        monkeypatch.setitem(sys.modules, name, module)
    before = {key: getattr(entry.base, key) for key in ("settings", "service", "FactLimits")}
    entry.main(["--freeze"])
    frozen = json.loads((entry.RESULTS / f"{PHASE}-provenance.json").read_text())
    assert events == ["dotenv", "settings"]
    assert frozen["model"] == "fixture-env-model"
    assert frozen["entrypoint_sha256"] == sha(ENTRY.read_bytes())
    assert {key: getattr(entry.base, key) for key in before} == before
    assert not entry.LEDGER.exists()


def test_module_bindings_restore_even_on_exception(entry):
    org_keys = ("REPORT", "RESULTS", "LEDGER", "PHASE", "CONFIG", "CEILING", "CALLER_LOCK", "BudgetClient", "snapshot", "verify", "check_budget")
    base_keys = ("REPORT", "RESULTS", "SHARED_LEDGER", "CONFIG", "CEILING", "BudgetClient", "snapshot", "caller_guard")
    org_before = {k: getattr(entry.organization, k) for k in org_keys}
    base_before = {k: getattr(entry.base, k) for k in base_keys}
    with pytest.raises(RuntimeError, match="fixture"):
        with entry.configured_base():
            assert entry.organization.PHASE == PHASE
            assert entry.organization.LEDGER == entry.base.SHARED_LEDGER == entry.LEDGER
            assert entry.organization.REPORT == entry.base.REPORT == entry.REPORT
            assert entry.organization.RESULTS == entry.base.RESULTS == entry.RESULTS
            assert entry.base.BudgetClient is entry.BudgetClient
            raise RuntimeError("fixture")
    assert {k: getattr(entry.organization, k) for k in org_keys} == org_before
    assert {k: getattr(entry.base, k) for k in base_keys} == base_before


@pytest.mark.parametrize("drift", ["source", "manifest", "runtime", "prompt", "codec", "module-config", "budget",
                                  "model", "options", "rubric", "entrypoint", "organization", "runner", "phase", "ledger", "lock", "ceiling",
                                  "checker", "checker-runner"])
def test_post_rechecks_entire_freeze_before_reservation(entry, monkeypatch, tmp_path, drift):
    # Real file drift uses disposable copies, never the actual historical wrappers.
    if drift in ("entrypoint", "organization", "runner"):
        module = entry if drift == "entrypoint" else entry.organization if drift == "organization" else entry.base
        copy = tmp_path / f"{drift}-entry.py"
        copy.write_bytes(Path(module.__file__).read_bytes())
        monkeypatch.setattr(module, "__file__", str(copy))
    elif drift in ("checker", "checker-runner"):
        key = "CHECKER_PATH" if drift == "checker" else "CHECKER_RUNNER_PATH"
        copy = tmp_path / f"{drift}.py"
        copy.write_bytes(getattr(entry, key).read_bytes())
        monkeypatch.setattr(entry, key, copy)
    frozen = entry.snapshot()
    if drift == "source":
        (entry.base.OLD / "corpus/short.txt").write_text("changed")
    elif drift == "manifest":
        path = entry.base.OLD / "corpus/manifest.json"
        path.write_text(path.read_text() + "\n")
    elif drift == "runtime":
        entry.base.settings.llm_max_input_chars = 60000
    elif drift == "prompt":
        entry.base.service._grounded_system = lambda *a: "changed"
    elif drift in ("codec", "module-config"):
        entry.base.MODULES["facts" if drift == "codec" else "config"].write_text('VALUE = "changed"\n')
    elif drift == "budget":
        entry.base.service._grounded_max_tokens = lambda stage: 1
    elif drift == "model":
        entry.base.settings.llm_model = "changed"
    elif drift == "options":
        entry.base.service._summary_options = lambda: {"response_format": {"type": "json_object"}}
    elif drift == "rubric":
        write(entry.REPORT / "rubric.json", {"baseline": {"sample_results": []}, "changed": True})
    elif drift in ("entrypoint", "organization", "runner", "checker", "checker-runner"):
        copy.write_bytes(copy.read_bytes() + b"\n# drift\n")
    else:
        key = {"phase": "phase", "ledger": "ledger", "lock": "caller_lock", "ceiling": "ceiling"}[drift]
        frozen[key] = "changed"
    sent = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200, json={}))) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        client.sample = "short"
        with pytest.raises(RuntimeError):
            client.post(URL, headers={}, json=payload(frozen))
    assert sent == []
    assert not entry.LEDGER.exists()
    assert not entry.base.SHARED_LEDGER.exists()


def test_standalone_client_uses_only_independent_phase_ledger(entry):
    frozen = entry.snapshot()
    old_ledgers = [entry.base.SHARED_LEDGER, entry.organization.LEDGER]
    for path in old_ledgers:
        write(path, {"ceiling": 49, "requests": [{"status": "unchanged"}]})
    prior = [path.read_bytes() for path in old_ledgers]
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        client.sample = "short"
        assert client.post(URL, headers={}, json=payload(frozen)).is_success
    ledger = json.loads(entry.LEDGER.read_text())
    assert ledger["ceiling"] == 13
    assert len(ledger["requests"]) == 1
    assert ledger["requests"][0]["phase"] == PHASE
    assert ledger["requests"][0]["stage"] == "extract"
    assert [path.read_bytes() for path in old_ledgers] == prior


def test_standalone_client_refuses_foreign_phase_before_reservation(entry):
    frozen = entry.snapshot()
    sent = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200, json={}))) as http:
        with pytest.raises(RuntimeError, match="phase"):
            client = entry.BudgetClient(http, "organization-slots", frozen)
            client.sample = "short"
            client.post(URL, headers={}, json=payload(frozen))
    assert sent == []
    assert not entry.LEDGER.exists()


def test_prior_caller_lock_excludes_final_and_ledger_lock_is_independent(entry):
    frozen = entry.snapshot()
    entry.CALLER_LOCK.mkdir(parents=True)
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("locked POST"))) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        client.sample = "short"
        with pytest.raises(FileExistsError):
            client.post(URL, headers={}, json=payload(frozen))
    with entry.configured_base():
        with entry.base.ledger_guard():
            assert (entry.RESULTS / "ledger.lock").exists()
            assert not (entry.CALLER_LOCK.parent / "ledger.lock").exists()
    assert entry.CALLER_LOCK.is_dir()
    assert not entry.LEDGER.exists()


@pytest.mark.parametrize("used, ceiling", [(1, 13), (13, 13), (0, 49)])
def test_run_refuses_insufficient_or_wrong_budget_before_delegation(entry, monkeypatch, used, ceiling):
    entry.main(["--freeze"])
    write(entry.LEDGER, {"ceiling": ceiling, "requests": [{} for _ in range(used)]})
    before = entry.LEDGER.read_bytes()
    monkeypatch.setattr(entry.base, "main", lambda *a, **k: pytest.fail("bad budget delegated runner"))
    with pytest.raises(RuntimeError, match="budget|ceiling"):
        entry.main(["--run"])
    assert entry.LEDGER.read_bytes() == before
    assert not (entry.RESULTS / f"{PHASE}-started.json").exists()


def test_run_delegates_explicit_phase_under_correct_restorable_bindings(entry, monkeypatch):
    entry.main(["--freeze"])
    old_report, old_phase = entry.organization.REPORT, entry.organization.PHASE
    def simulate(argv=None, *, phase_choices):
        assert argv == ["--phase", PHASE]
        assert phase_choices == [PHASE]
        assert entry.base.REPORT == entry.REPORT
        assert entry.base.RESULTS == entry.RESULTS
        assert entry.base.SHARED_LEDGER == entry.LEDGER
        assert entry.base.CEILING == 13
        assert entry.CALLER_LOCK.is_dir()
        return "offline delegation"
    monkeypatch.setattr(entry.base, "main", simulate)
    assert entry.main(["--run"]) == "offline delegation"
    assert entry.organization.REPORT == old_report
    assert entry.organization.PHASE == old_phase
    assert not entry.CALLER_LOCK.exists()
    assert not entry.LEDGER.exists()


@pytest.mark.parametrize("failure", ["transport", "http", "invalid_json"])
def test_failed_long_extract_spends_once_and_refuses_retry(entry, failure):
    frozen = entry.snapshot()
    sent = []
    def fail(request):
        sent.append(request)
        assert json.loads(entry.LEDGER.read_text())["requests"][-1]["status"] == "reserved"
        if failure == "transport":
            raise httpx.ConnectError("private", request=request)
        if failure == "http":
            return httpx.Response(429, json={"error": {"type": "rate_limit_error"}})
        return httpx.Response(200, content=b"private-invalid-json")
    with httpx.Client(transport=httpx.MockTransport(fail)) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        client.sample = "long"
        if failure == "http":
            assert client.post(URL, headers={}, json=payload(frozen)).status_code == 429
        else:
            with pytest.raises((httpx.ConnectError, json.JSONDecodeError)):
                client.post(URL, headers={}, json=payload(frozen))
        with pytest.raises(RuntimeError, match="failed|stopped"):
            client.post(URL, headers={}, json=payload(frozen))
    assert len(sent) == len(json.loads(entry.LEDGER.read_text())["requests"]) == 1
    assert "private" not in entry.LEDGER.read_text()


def test_thirteen_post_ceiling_is_enforced_in_own_ledger(entry):
    frozen = entry.snapshot()
    sent = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200, json={}))) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        for sample, stages in [("short", ["extract", "compose", "audit"]),
                               ("medium", ["extract", "compose", "audit"]),
                               ("long", ["extract"] * 5 + ["compose", "audit"])]:
            client.sample, client.sample_post = sample, 0
            for stage in stages:
                assert client.post(URL, headers={}, json=payload(frozen, stage, 4096 if stage == "extract" else 8192)).is_success
        next_client = entry.BudgetClient(http, PHASE, frozen)
        next_client.sample = "short"
        with pytest.raises(RuntimeError, match="ceiling"):
            next_client.post(URL, headers={}, json=payload(frozen))
    ledger = json.loads(entry.LEDGER.read_text())
    assert len(sent) == len(ledger["requests"]) == 13
    assert [r["ordinal"] for r in ledger["requests"]] == list(range(1, 14))
    assert {r["phase"] for r in ledger["requests"]} == {PHASE}


@pytest.fixture
def checker(entry, monkeypatch):
    entry.main(["--freeze"])
    frozen = json.loads((entry.RESULTS / f"{PHASE}-provenance.json").read_text())
    def fail(request):
        raise httpx.ConnectError("fixture", request=request)
    with httpx.Client(transport=httpx.MockTransport(fail)) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        client.sample = "short"
        with pytest.raises(httpx.ConnectError):
            client.post(URL, headers={}, json=payload(frozen))
    trace = entry.RESULTS / f"{PHASE}-short-trace.json"
    write(trace, {"phase": PHASE, "id": "short", "events": [{"status": "failed", "error_type": "ConnectError",
          "sources": [{"id": "S1", "text": "a", "global_start": 0, "sha256": sha("a")}], "planned_calls": 3, "facts": []}]})
    result = entry.RESULTS / f"{PHASE}-short.json"
    write(result, {"phase": PHASE, "id": "short", "source_sha256": sha("a"), "trace_sha256": sha(trace.read_bytes()),
                   "error_type": "ConnectError"})
    write(entry.RESULTS / f"{PHASE}-index.json", {"sample_results": [{"id": "short", "file": result.name,
          "sha256": sha(result.read_bytes()), "posts": 1}]})
    checker = load(CHECKER, "final_test_checker")
    for key, value in {"REPORT": entry.REPORT, "RESULTS": entry.RESULTS, "LEDGER": entry.LEDGER}.items():
        monkeypatch.setattr(checker, key, value)
    monkeypatch.setattr(checker.checker, "OLD", entry.base.OLD)
    monkeypatch.setattr(checker.checker, "BASE", entry.base.BASE)
    return checker


def test_checker_uses_hash_validated_frozen_codec_and_only_own_ledger(checker, entry, capsys):
    prior = entry.base.SHARED_LEDGER
    write(prior, {"ceiling": 49, "requests": [{"invalid": "prior must not be read"}]})
    before = prior.read_bytes()
    entry.base.MODULES["facts"].write_text('raise RuntimeError("live codec must not load")\n')
    entry.base.MODULES["service"].write_text('raise RuntimeError("live service must not load")\n')
    checker.main([])
    evidence = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert evidence["phase"] == PHASE
    assert evidence["ceiling"] == 13
    assert evidence["reserved_all_phases"] == 1
    assert evidence["offline_only"] is True
    assert evidence["trace_lexically_valid"] is True
    assert evidence["semantic_accuracy_not_proven_by_this_check"] is True
    assert prior.read_bytes() == before
    assert not (entry.RESULTS / f"{PHASE}-offline-check.json").exists()
    checker.main(["--write"])
    path = entry.RESULTS / f"{PHASE}-offline-check.json"
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        checker.main(["--write"])
    assert path.read_bytes() == before


def test_checker_rejects_frozen_codec_drift_before_loading_it(checker):
    (checker.RESULTS / f"{PHASE}-facts.py").write_text('raise RuntimeError("must not execute")\n')
    with pytest.raises(ValueError, match="Frozen module hash mismatch"):
        checker.main([])


@pytest.mark.parametrize("component", ["wrapper", "runner"])
def test_checker_refuses_its_own_code_drift_before_loading_frozen_codec(checker, monkeypatch, tmp_path, component):
    path = Path(checker.__file__) if component == "wrapper" else checker.CHECKER
    copy = tmp_path / f"{component}-changed.py"
    copy.write_bytes(path.read_bytes() + b"\n# changed checker\n")
    monkeypatch.setattr(checker, "__file__" if component == "wrapper" else "CHECKER", str(copy) if component == "wrapper" else copy)
    monkeypatch.setattr(checker.checker, "frozen_helpers", lambda *args: pytest.fail("checker drift executed frozen codec"))
    with pytest.raises(ValueError, match="Checker hash mismatch"):
        checker.main([])


@pytest.mark.parametrize("mutation", ["ceiling", "phase"])
def test_checker_refuses_foreign_ledger(checker, mutation):
    ledger = json.loads(checker.LEDGER.read_text())
    if mutation == "ceiling":
        ledger["ceiling"] = 49
    else:
        ledger["requests"][0]["phase"] = "organization-slots"
    write(checker.LEDGER, ledger)
    with pytest.raises(ValueError, match="ledger|Ledger|ceiling|phase"):
        checker.main([])


@pytest.mark.parametrize("mutation", ["float-ceiling", "foreign-phase", "bad-ordinal"])
def test_standalone_client_refuses_invalid_existing_ledger_before_send(entry, mutation):
    frozen = entry.snapshot()
    value = {"ceiling": 13, "requests": []}
    if mutation == "float-ceiling":
        value["ceiling"] = 13.0
    else:
        value["requests"] = [{"ordinal": 1, "phase": PHASE}]
        value["requests"][0]["phase" if mutation == "foreign-phase" else "ordinal"] = "foreign" if mutation == "foreign-phase" else 2
    write(entry.LEDGER, value)
    before = entry.LEDGER.read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("invalid ledger sent POST"))) as http:
        client = entry.BudgetClient(http, PHASE, frozen)
        client.sample = "short"
        with pytest.raises(RuntimeError, match="ledger|Ledger"):
            client.post(URL, headers={}, json=payload(frozen))
    assert entry.LEDGER.read_bytes() == before
    assert not (entry.RESULTS / "payloads").exists()


def test_original_fourteen_essential_rubric_bytes_are_preserved():
    # Changing expectations to suit new outputs must fail this acceptance test.
    original = REPORTS / "2026-10-07-grounded-summary-refined/rubric.json"
    current = ENTRY.parents[1] / "rubric.json"
    assert current.is_file(), "final rubric must exist"
    assert current.read_bytes() == original.read_bytes()
    rubric = json.loads(current.read_text(encoding="utf-8"))
    essentials = [item["id"] for sample in rubric["samples"] for item in sample["expectations"] if item["priority"] == "essential"]
    assert essentials == ["zh1", "zh2", "zh3", "zh4", "en1", "en2", "en3", "en4", "long1", "long2", "long3", "long4", "long5", "long6"]


@pytest.mark.parametrize("failure", [None, "transport", "http", "invalid_json", "contract"])
def test_real_runner_uses_serial_three_three_seven_and_stops_after_failure(entry, monkeypatch, failure):
    # Exercise real base.main and durable writes; replace only environment/runtime
    # imports and the external transport with deterministic local fixtures.
    entry.base.settings.llm_timeout_seconds = 10
    entry.main(["--freeze"])
    frozen = json.loads((entry.RESULTS / f"{PHASE}-provenance.json").read_text())
    sent = []
    failure_ordinal = 8
    def respond(request):
        ledger = json.loads(entry.LEDGER.read_text())
        assert ledger["requests"][-1]["status"] == "reserved"
        assert entry.CALLER_LOCK.is_dir()
        ordinal = len(sent) + 1
        sent.append(request)
        if ordinal == failure_ordinal:
            if failure == "transport":
                raise httpx.ConnectError("private", request=request)
            if failure == "http":
                return httpx.Response(429, json={"error": {"type": "rate_limit_error"}})
            if failure == "invalid_json":
                return httpx.Response(200, content=b"private-invalid-json")
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {"total_tokens": 1}})
    real_client = httpx.Client
    def fake_client(*, timeout, proxy, trust_env):
        assert timeout == 10 and proxy is None and trust_env is False
        return real_client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(entry.base.httpx, "Client", fake_client)
    monkeypatch.setattr(entry.base, "load_dotenv", lambda *args, **kwargs: None)
    class ServiceError(Exception):
        error_type = "fixture_contract_error"
    entry.base.service.LLMServiceError = ServiceError
    @dataclass
    class Result:
        summary: str = "fixture final summary"
        key_points: tuple = ("fixture point",)
        provider: str = "offline"
        model: str = "offline-model"
    def summarize(source, *, title, output_language, client, diagnostic):
        assert output_language == "zh-CN"
        stages = ["extract"] * len(source.split("|")) + ["compose", "audit"]
        for stage in stages:
            response = client.post(URL, headers={}, json=payload(frozen, stage, 4096 if stage == "extract" else 8192))
            response.raise_for_status()
            if failure == "contract" and len(sent) == failure_ordinal:
                raise ServiceError()
        diagnostic({"status": "completed"})
        return Result()
    entry.base.service.summarize_text = summarize
    app = ModuleType("app")
    app.__path__ = []
    config = ModuleType("app.config")
    config.settings = entry.base.settings
    services = ModuleType("app.services")
    services.__path__ = []
    services.llm_service = entry.base.service
    facts = ModuleType("app.services.summary_facts")
    facts.FactLimits = Limits
    for name, module in {"app": app, "app.config": config, "app.services": services, "app.services.summary_facts": facts}.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    entry.main(["--run"])
    ledger = json.loads(entry.LEDGER.read_text())
    index = json.loads((entry.RESULTS / f"{PHASE}-index.json").read_text())
    expected_stages = ["extract", "compose", "audit", "extract", "compose", "audit", "extract", "extract", "extract", "extract", "extract", "compose", "audit"]
    count = 13 if failure is None else failure_ordinal
    assert len(sent) == len(ledger["requests"]) == count
    assert [row["stage"] for row in ledger["requests"]] == expected_stages[:count]
    assert [row["posts"] for row in index["sample_results"]] == ([3, 3, 7] if failure is None else [3, 3, 2])
    final = json.loads((entry.RESULTS / f"{PHASE}-long.json").read_text())
    assert ("error_type" in final) is (failure is not None)
    assert not entry.CALLER_LOCK.exists()
    before = entry.LEDGER.read_bytes()
    with pytest.raises((RuntimeError, FileExistsError)):
        entry.main(["--run"])
    assert entry.LEDGER.read_bytes() == before
    assert len(sent) == count
