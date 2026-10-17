"""Run official Ragas faithfulness through a single controlled completion boundary.

Engineering constraints: mature components, narrow interfaces and one-way dependency;
no production/yt-dlp/UI/account changes. Existing evidence remains byte-for-byte intact.
This module performs no HTTP itself and creates no Instructor or provider SDK client.
"""

from __future__ import annotations

import copy
import math
import os
from collections.abc import Callable
from importlib.metadata import version
from typing import Any, TypeVar

# Must precede the first import of Ragas and its transitive optional integrations.
# Assignment intentionally overrides inherited tracking settings in this isolated tool.
os.environ["RAGAS_DO_NOT_TRACK"] = "true"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_TRACING"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"
os.environ["DO_NOT_TRACK"] = "1"

from pydantic import BaseModel  # noqa: E402
from ragas.llms.base import InstructorBaseRagasLLM  # noqa: E402
from ragas.metrics.collections import Faithfulness  # noqa: E402
from ragas.metrics.collections.faithfulness.util import (  # noqa: E402
    NLIStatementOutput,
    StatementGeneratorOutput,
)

Model = TypeVar("Model", bound=BaseModel)
Complete = Callable[[str, type[BaseModel]], dict[str, Any]]
MAX_INPUT_CHARACTERS = 60_000
MAX_STATEMENTS = 128
MAX_OUTPUT_CHARACTERS = 120_000
QUESTION = "Summarize the source."


def _text(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    if len(value) > MAX_INPUT_CHARACTERS:
        raise ValueError(f"{name} exceeds the text character limit")
    return value


def _statement_list(raw: Any) -> list[Any]:
    if type(raw) is not dict or set(raw) != {"statements"}:
        raise ValueError("completion must contain only the statements field")
    statements = raw["statements"]
    if type(statements) is not list or not 1 <= len(statements) <= MAX_STATEMENTS:
        raise ValueError("statements must be a nonempty bounded list")
    return statements


def _validate_score(score: Any) -> float:
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Ragas returned a nonfinite or out-of-range faithfulness score")
    return float(score)


class ControlledRagasLLM(InstructorBaseRagasLLM):
    """The official abstract LLM contract, with no SDK retry/cache/fallback layer."""

    def __init__(self, complete: Complete):
        if not callable(complete):
            raise TypeError("complete must be callable")
        self._complete = complete
        self._extraction_attempted = False
        self._nli_attempted = False
        self.statement_output: dict[str, Any] | None = None
        self.nli_output: dict[str, Any] | None = None

    def generate(self, prompt: str, response_model: type[Model]) -> Model:
        if response_model is StatementGeneratorOutput:
            if self._extraction_attempted or self._nli_attempted:
                raise ValueError("statement extraction may run only once")
            self._extraction_attempted = True
        elif response_model is NLIStatementOutput:
            if self.statement_output is None or self._nli_attempted:
                raise ValueError("NLI requires exactly one preceding extraction")
            self._nli_attempted = True
        else:
            raise ValueError("unexpected Ragas response model")

        # Preserve raw provider types before Pydantic can coerce e.g. True to 1.
        raw = self._complete(prompt, response_model)
        items = _statement_list(raw)
        if response_model is StatementGeneratorOutput:
            strings = [_text(item, "statement") for item in items]
            if len(set(strings)) != len(strings):
                raise ValueError("duplicate extracted statements")
            character_count = sum(map(len, strings))
        else:
            strings = []
            character_count = 0
            for item in items:
                if type(item) is not dict or set(item) != {"statement", "reason", "verdict"}:
                    raise ValueError("NLI item must contain exactly statement/reason/verdict")
                statement = _text(item["statement"], "NLI statement")
                reason = _text(item["reason"], "NLI reason")
                if type(item["verdict"]) is not int or item["verdict"] not in (0, 1):
                    raise ValueError("NLI verdict must be a strict integer 0 or 1")
                strings.append(statement)
                character_count += len(statement) + len(reason)
            expected = self.statement_output["statements"]
            if len(strings) != len(expected) or len(set(strings)) != len(strings) or set(strings) != set(expected):
                raise ValueError("NLI statements must match extraction exactly once without rewriting")
        if character_count > MAX_OUTPUT_CHARACTERS:
            raise ValueError("completion exceeds the output character limit")

        parsed = response_model.model_validate(raw, strict=True)
        if response_model is StatementGeneratorOutput:
            self.statement_output = copy.deepcopy(raw)
        else:
            self.nli_output = copy.deepcopy(raw)
        return parsed

    async def agenerate(self, prompt: str, response_model: type[Model]) -> Model:
        # Ragas invokes this sequentially. The injected synchronous caller owns its
        # lock, persistent pre-reservation, transport timeout and request accounting.
        return self.generate(prompt, response_model)


def evaluate(source: str, response: str, complete: Complete) -> dict[str, Any]:
    """Return official metric score plus raw decomposition and per-statement NLI.

    Fail closed on the first malformed response or completion exception; there is
    no retry. Semantic correctness of decomposition/judgments remains a human
    calibration concern. No labels, expected verdicts or coverage questions enter
    either official Ragas prompt.
    """
    _text(source, "source")
    _text(response, "response")
    if len(source) + len(response) > MAX_INPUT_CHARACTERS:
        raise ValueError("combined source and response exceed the input character limit")
    installed_version = version("ragas")
    if installed_version != "0.4.3":
        raise ValueError("this adapter requires ragas==0.4.3")

    llm = ControlledRagasLLM(complete)
    metric = Faithfulness(llm=llm)
    # Use the real public metric pipeline, its official prompts and its scoring.
    result = metric.score(user_input=QUESTION, response=response, retrieved_contexts=[source])
    score = _validate_score(result.value)
    if llm.statement_output is None or llm.nli_output is None:
        raise ValueError("Ragas did not complete both evaluation stages")
    statements = llm.statement_output["statements"]
    verdicts = llm.nli_output["statements"]
    by_statement = {item["statement"]: item for item in verdicts}
    return {
        "metric": "ragas.faithfulness",
        "ragas_version": installed_version,
        "source": source,
        "response": response,
        "statement_output": llm.statement_output,
        "nli_output": llm.nli_output,
        "statements": statements,
        "verdicts": verdicts,
        "results": [by_statement[statement] for statement in statements],
        "score": score,
        "all_supported": all(item["verdict"] == 1 for item in verdicts),
        "decomposition_fidelity": "not_automatically_verified",
        "source_scope_semantics": "not_automatically_verified",
        "coverage": "not_evaluated",
        "limitations": [
            "Statement extraction can omit or alter qualifiers; original response and extracted statements require comparison.",
            "Exact statement binding validates structure, not source subject/scope semantics or NLI correctness.",
            "Faithfulness and all_supported do not certify core-topic coverage or overall summary acceptance.",
        ],
    }
