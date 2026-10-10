"""Review regressions use copied artifacts; never mutate the real ledger/results."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest


PROJECT = Path(__file__).resolve().parents[2]
REPORT = PROJECT / "docs/acceptance-reports/2026-10-05-grounded-summary-evidence"
PHASE = "evidence-wide"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def checker(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("review_evidence_checker", REPORT / "scripts/check_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = tmp_path / "results"
    results.mkdir()
    for path in (REPORT / "results").glob(f"{PHASE}-*"):
        shutil.copyfile(path, results / path.name)
    for directory in ("payloads", "responses"):
        shutil.copytree(REPORT / "results" / directory, results / directory)
    shutil.copyfile(REPORT / "rubric.json", tmp_path / "rubric.json")
    ledger = tmp_path / "request-ledger.json"
    shutil.copyfile(PROJECT / "docs/acceptance-reports/2026-10-05-grounded-summary/results/request-ledger.json", ledger)
    monkeypatch.setattr(module, "REPORT", tmp_path)
    monkeypatch.setattr(module, "RESULTS", results)
    monkeypatch.setattr(module, "SHARED_LEDGER", ledger)
    monkeypatch.setattr(sys, "argv", ["check_evidence.py", "--phase", PHASE])
    return module


def run(checker, capsys):
    checker.main()
    return json.loads(capsys.readouterr().out)


def update_trace(checker, mutate):
    trace_path = checker.RESULTS / f"{PHASE}-zh-short-trace.json"
    trace = read(trace_path)
    mutate(trace["events"][-1])
    write(trace_path, trace)
    result_path = checker.RESULTS / f"{PHASE}-zh-short.json"
    result = read(result_path)
    result["trace_sha256"] = checker.digest(trace_path)
    write(result_path, result)
    index_path = checker.RESULTS / f"{PHASE}-index.json"
    index = read(index_path)
    index["sample_results"][0]["sha256"] = checker.digest(result_path)
    write(index_path, index)


def test_checker_reports_actual_ledger_ceiling(checker, capsys):
    result = run(checker, capsys)
    assert result["ceiling"] == 49
    assert result["reserved_all_phases"] == 48
    assert [row["evidence_spans_checked"] for row in result["samples"]] == [11, 8, 54]


@pytest.mark.parametrize("field", ["manifest_sha256", "source", "cleaned"])
def test_checker_binds_to_frozen_input_hashes(checker, field):
    path = checker.RESULTS / f"{PHASE}-provenance.json"
    provenance = read(path)
    if field == "manifest_sha256":
        provenance[field] = "0" * 64
    else:
        provenance["samples"][0]["sha256" if field == "source" else "cleaned_sha256"] = "0" * 64
    write(path, provenance)
    with pytest.raises(ValueError):
        checker.main()


def test_checker_rejects_empty_index(checker):
    write(checker.RESULTS / f"{PHASE}-index.json", {"sample_results": []})
    with pytest.raises(ValueError):
        checker.main()


def test_checker_reconciles_sample_posts_with_ledger(checker):
    path = checker.RESULTS / f"{PHASE}-index.json"
    index = read(path)
    index["sample_results"][0]["posts"] = 999
    write(path, index)
    with pytest.raises(ValueError):
        checker.main()


def test_checker_rejects_missing_final_audit_checks(checker):
    update_trace(checker, lambda last: last["audit"].update(checks=[]))
    with pytest.raises(ValueError):
        checker.main()


def test_checker_rejects_noncanonical_stored_evidence_order(checker):
    def reverse(last):
        fact = next(item for item in last["audit"]["facts"] if len(item["evidence_indices"]) > 1)
        fact["evidence_indices"].reverse()
    update_trace(checker, reverse)
    with pytest.raises(ValueError):
        checker.main()


def test_checker_is_independent_of_live_cleanup_and_split(checker, monkeypatch, capsys):
    monkeypatch.setattr(checker, "_summary_input", lambda _: "different live cleanup", raising=False)
    monkeypatch.setattr(checker, "split_sentences", lambda _: (), raising=False)
    result = run(checker, capsys)
    assert result["trace_lexically_valid"] is True
    assert [row["evidence_spans_checked"] for row in result["samples"]] == [11, 8, 54]
