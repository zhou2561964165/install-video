"""Serial role isolation using LCEL, without provider SDKs or external tracing.

The service supplies narrow callables for HTTP, parsing and bounded repair.
This module only carries successful points into the overview stage.
"""
from typing import Any, Callable

from langchain_core.runnables import RunnableLambda, RunnableSequence
from langsmith import tracing_context


def invoke_summary_pipeline(
    source: dict[str, Any],
    *,
    points: Callable[[dict[str, Any]], dict[str, Any]],
    overview: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    pipeline = RunnableSequence(
        RunnableLambda(points, name="summary_points"),
        RunnableLambda(overview, name="summary_overview"),
    )
    # Explicitly override both LangSmith and legacy LangChain tracing env vars.
    # Cover construction's entire invocation, including any nested runnables.
    with tracing_context(enabled=False):
        return pipeline.invoke(source)
