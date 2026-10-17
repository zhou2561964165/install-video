"""Offline boundary tests using the installed Ragas metric and official prompts."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ragas_adapter as adapter


class ScriptedComplete:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, prompt, response_model):
        self.calls.append((prompt, response_model))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def verdict(statement="A is limited.", verdict=1, reason="The source says so."):
    return {"statement": statement, "verdict": verdict, "reason": reason}


def test_real_metric_preserves_raw_statements_and_reordered_verdicts():
    statements = ["A is limited.", "B is unlimited."]
    raw_verdicts = [verdict(statements[1], 0, "Unsupported."), verdict(statements[0])]
    complete = ScriptedComplete({"statements": statements}, {"statements": raw_verdicts})
    result = adapter.evaluate("Only A is limited.", "A is limited. B is unlimited.", complete)
    assert result["metric"] == "ragas.faithfulness"
    assert result["ragas_version"] == "0.4.3"
    assert result["score"] == 0.5
    assert result["all_supported"] is False
    assert result["statements"] == statements
    assert result["verdicts"] == raw_verdicts
    assert result["results"] == [raw_verdicts[1], raw_verdicts[0]]
    assert result["statement_output"] == {"statements": statements}
    assert result["nli_output"] == {"statements": raw_verdicts}
    assert len(complete.calls) == 2
    from ragas.metrics.collections.faithfulness.util import (
        NLIStatementOutput, NLIStatementPrompt, StatementGeneratorOutput, StatementGeneratorPrompt,
    )
    assert complete.calls[0][1] is StatementGeneratorOutput
    assert complete.calls[1][1] is NLIStatementOutput
    assert StatementGeneratorPrompt.instruction in complete.calls[0][0]
    assert NLIStatementPrompt.instruction in complete.calls[1][0]
    json.dumps(result, allow_nan=False)


def test_cross_language_passes_original_source_and_response_without_translation():
    source = "This particular calculator supports only arithmetic."
    response = "所有固定程序都只能做四则运算。"
    complete = ScriptedComplete({"statements": [response]}, {"statements": [verdict(response, 0)]})
    result = adapter.evaluate(source, response, complete)
    assert response in complete.calls[0][0]
    assert source in complete.calls[1][0]
    assert response in complete.calls[1][0]
    assert result["source"] == source
    assert result["response"] == response
    assert result["statements"] == [response]


def test_qualifier_lost_in_decomposition_is_reported_as_unverified_not_certified():
    source = "Only this calculator is limited to arithmetic."
    response = "All fixed programs are limited to arithmetic."
    complete = ScriptedComplete(
        {"statements": ["This calculator is limited to arithmetic."]},
        {"statements": [verdict("This calculator is limited to arithmetic.")]},
    )
    result = adapter.evaluate(source, response, complete)
    assert result["score"] == 1.0
    assert result["all_supported"] is True
    assert result["response"] == response
    assert result["decomposition_fidelity"] == "not_automatically_verified"
    assert result["source_scope_semantics"] == "not_automatically_verified"
    assert result["coverage"] == "not_evaluated"
    assert result["limitations"]


@pytest.mark.parametrize("source,response", [("", "A"), ("  ", "A"), (None, "A"),
    ("A", ""), ("A", "\n"), ("A", 12), ("x" * 60000, "A")],
    ids=["empty-source", "blank-source", "null-source", "empty-response", "blank-response", "wrong-response-type", "oversized-input"])
def test_invalid_inputs_fail_before_any_call(source, response):
    complete = ScriptedComplete()
    with pytest.raises((ValueError, TypeError)):
        adapter.evaluate(source, response, complete)
    assert complete.calls == []


@pytest.mark.parametrize("output", [None, [], {"statements": []}, {"statements": "A"},
    {"statements": [""]}, {"statements": [" "]}, {"statements": [1]},
    {"statements": ["A", "A"]}, {"statements": ["x" * 60001]},
    {"statements": [str(i) for i in range(129)]},
    {"statements": ["A"], "unrequested": True}])
def test_bad_decomposition_stops_after_first_call(output):
    complete = ScriptedComplete(output)
    with pytest.raises((ValueError, TypeError)):
        adapter.evaluate("Source", "Response", complete)
    assert len(complete.calls) == 1


@pytest.mark.parametrize("bad_verdict", [True, False, 2, -1, "1", 1.0, None])
def test_verdict_is_strict_integer_enum_before_pydantic_coercion(bad_verdict):
    complete = ScriptedComplete({"statements": ["A"]}, {"statements": [verdict("A", bad_verdict)]})
    with pytest.raises((ValueError, TypeError)):
        adapter.evaluate("A", "A", complete)
    assert len(complete.calls) == 2


@pytest.mark.parametrize("items", [[], [verdict("A")], [verdict("A"), verdict("A")],
    [verdict("A"), verdict("Reworded B")], [verdict("A"), verdict("B"), verdict("C")]])
def test_nli_requires_exact_one_to_one_statement_binding(items):
    complete = ScriptedComplete({"statements": ["A", "B"]}, {"statements": items})
    with pytest.raises(ValueError):
        adapter.evaluate("A B", "A B", complete)
    assert len(complete.calls) == 2


@pytest.mark.parametrize("output", [None, {}, {"statements": "A"},
    {"statements": [verdict("A", reason="")]}, {"statements": [verdict("A", reason=1)]},
    {"statements": [{"statement": "A", "verdict": 1}]},
    {"statements": [{**verdict("A"), "extra": "field"}]},
    {"statements": [verdict("A")], "extra": True}])
def test_malformed_nli_stops_without_retry(output):
    complete = ScriptedComplete({"statements": ["A"]}, output)
    with pytest.raises((ValueError, TypeError)):
        adapter.evaluate("A", "A", complete)
    assert len(complete.calls) == 2


@pytest.mark.parametrize("first_fails", [True, False])
def test_provider_or_parse_exception_propagates_without_retry(first_fails):
    error = RuntimeError("provider failed")
    outputs = [error] if first_fails else [{"statements": ["A"]}, error]
    complete = ScriptedComplete(*outputs)
    with pytest.raises(RuntimeError, match="provider failed"):
        adapter.evaluate("A", "A", complete)
    assert len(complete.calls) == (1 if first_fails else 2)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1, True])
def test_nonfinite_or_invalid_score_is_rejected(score):
    with pytest.raises(ValueError):
        adapter._validate_score(score)


def test_generate_and_agenerate_use_same_sync_boundary_and_real_base_class():
    from ragas.llms.base import InstructorBaseRagasLLM
    from ragas.metrics.collections.faithfulness.util import StatementGeneratorOutput
    complete = ScriptedComplete({"statements": ["A"]}, {"statements": ["B"]})
    llm = adapter.ControlledRagasLLM(complete)
    assert isinstance(llm, InstructorBaseRagasLLM)
    assert llm.generate("first", StatementGeneratorOutput).statements == ["A"]
    # A fresh instance represents another metric run; no cross-run state is reused.
    llm = adapter.ControlledRagasLLM(complete)
    assert asyncio.run(llm.agenerate("second", StatementGeneratorOutput)).statements == ["B"]
    assert [prompt for prompt, _ in complete.calls] == ["first", "second"]


def test_failed_extraction_cannot_be_called_again_on_same_llm():
    from ragas.metrics.collections.faithfulness.util import StatementGeneratorOutput
    complete = ScriptedComplete({"statements": []}, {"statements": ["A"]})
    llm = adapter.ControlledRagasLLM(complete)
    with pytest.raises(ValueError):
        llm.generate("first", StatementGeneratorOutput)
    with pytest.raises(ValueError):
        llm.generate("retry", StatementGeneratorOutput)
    assert len(complete.calls) == 1


@pytest.mark.parametrize("failed_stage", ["extraction", "nli"])
@pytest.mark.parametrize("failure", [ValueError("parse failure"), {"statements": []}], ids=["exception", "invalid-output"])
def test_failed_stage_locks_instance_against_all_further_calls(failed_stage, failure):
    from ragas.metrics.collections.faithfulness.util import NLIStatementOutput, StatementGeneratorOutput
    outputs = [failure] if failed_stage == "extraction" else [{"statements": ["A"]}, failure]
    complete = ScriptedComplete(*outputs)
    llm = adapter.ControlledRagasLLM(complete)
    if failed_stage == "nli":
        llm.generate("extract", StatementGeneratorOutput)
    with pytest.raises(ValueError):
        llm.generate("fail", StatementGeneratorOutput if failed_stage == "extraction" else NLIStatementOutput)
    count = len(complete.calls)
    for response_model in (StatementGeneratorOutput, NLIStatementOutput):
        with pytest.raises(ValueError):
            llm.generate("retry", response_model)
    assert len(complete.calls) == count


def test_large_nli_response_is_rejected_without_truncating_provider_output():
    outputs = {"statements": [verdict("A", reason="x" * 60000), verdict("B", reason="x" * 60000)]}
    complete = ScriptedComplete({"statements": ["A", "B"]}, outputs)
    with pytest.raises(ValueError, match="character limit"):
        adapter.evaluate("A B", "A B", complete)
    assert len(outputs["statements"][0]["reason"]) == 60000
    assert len(complete.calls) == 2


def test_successful_evaluation_is_deterministic_for_raw_replay():
    raw = [{"statements": ["A"]}, {"statements": [verdict("A")]}]
    first = adapter.evaluate("A", "A", ScriptedComplete(*raw))
    second = adapter.evaluate("A", "A", ScriptedComplete(*raw))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_labels_are_not_accepted_by_evaluate():
    with pytest.raises(TypeError):
        adapter.evaluate("A", "A", ScriptedComplete(), expected_supported=True)


def test_fresh_import_and_real_metric_issue_no_network_and_override_tracking_env():
    script = r'''
import os, socket, sys
os.environ.update(RAGAS_DO_NOT_TRACK="false", LANGSMITH_TRACING="true", LANGCHAIN_TRACING_V2="true", HF_HUB_OFFLINE="0")
# Windows asyncio creates its self-pipe via a loopback socketpair. Pre-create
# exactly that IPC pair before the network guard, then deny every connect/DNS.
# Ragas still uses the real event loop; no provider or telemetry path is exempt.
self_pipe = socket.socketpair()
def event_loop_socketpair(*args, **kwargs):
    global self_pipe
    assert self_pipe is not None, "unexpected additional socketpair"
    pair, self_pipe = self_pipe, None
    return pair
socket.socketpair = event_loop_socketpair
def blocked(*args, **kwargs):
    raise AssertionError("unexpected network access")
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
socket.getaddrinfo = blocked
sys.path.insert(0, sys.argv[1])
import ragas_adapter
outputs = iter([{"statements": ["A"]}, {"statements": [{"statement": "A", "verdict": 1, "reason": "A"}]}])
result = ragas_adapter.evaluate("A", "A", lambda prompt, model: next(outputs))
from ragas._analytics import do_not_track
assert do_not_track() is True
assert os.environ["LANGSMITH_TRACING"] == "false"
assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
assert os.environ["HF_HUB_OFFLINE"] == "1"
assert result["score"] == 1.0
print("offline real metric passed")
'''
    proc = subprocess.run([sys.executable, "-B", "-c", script, str(Path(adapter.__file__).parent)],
        capture_output=True, text=True, timeout=60, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "offline real metric passed" in proc.stdout
