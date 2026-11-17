"""
Main entry point for executing agent runs.

Wraps the compiled LangGraph graph execution with root-level tracing.
"""

import time

from app.runtime.graph import agent_graph
from app.runtime.state import AgentRunState
from app.evals.observability.tracing import start_span, SpanContext##=================================== ##===================================
from app.evals.observability.metrics import collector, RunMetrics ##=================================== ##===================================


async def execute_run(
    run_id: str,
    task_type: str,
    user_input: dict,
    config: dict | None = None,
) -> AgentRunState:
    """Execute a full agent run wrapped in a root trace span."""
    start = time.monotonic()

    with start_span("agent_run", run_id=run_id, attrs={"task_type": task_type}) as root_span:##===================================
        initial_state: AgentRunState = {
            "run_id": run_id,
            "task_type": task_type,
            "user_input": user_input,
            "context": {"span_ctx": SpanContext(root_span).ctx},##===================================
            "messages": [],
            "tool_calls": [],
            "intermediate_results": [],
            "final_output": None,
            "status": "queued",
            "error": None,
        }

        try:
            result = await agent_graph.ainvoke(##===================================##===================================
                initial_state,
                config={"configurable": {"run_id": run_id}},
            )
            root_span.set_attribute("run.status", result.get("status", "unknown"))
        except Exception as exc:
            initial_state["status"] = "failed"
            initial_state["error"] = {"type": type(exc).__name__, "message": str(exc)}
            root_span.set_attribute("run.error", str(exc))
            result = initial_state

    elapsed_ms = int((time.monotonic() - start) * 1000)

    tool_calls = result.get("tool_calls", [])
    tool_errors = sum(1 for tc in tool_calls if tc.get("result", {}).get("error"))

    collector.record(##===================================
                    RunMetrics(##===================================
                                run_id=run_id,
                                latency_ms=elapsed_ms,
                                tool_calls=len(tool_calls),
                                tool_errors=tool_errors,
                                success=result.get("status") == "completed",
                                error=result.get("error"),
                                )
    )
    return result

