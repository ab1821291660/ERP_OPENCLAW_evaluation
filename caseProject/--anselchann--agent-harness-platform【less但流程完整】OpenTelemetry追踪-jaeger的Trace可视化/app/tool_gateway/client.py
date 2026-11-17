"""
Tool Gateway Client - unified interface for invoking tools.

Runtime calls this instead of talking to tool implementations directly.
"""

import time

from app.schemas.tools import ToolInvocationRecord
from app.tool_gateway.registry import registry
from app.tool_gateway.policy import check_policy
from app.tool_gateway.executor import execute
from app.tool_gateway.audit import log_invocation
from app.evals.observability.tracing import start_span


async def invoke_tool(
    run_id: str,
    tool_name: str,
    payload: dict,
) -> ToolInvocationRecord:
    spec = registry.get(tool_name)
    if spec is None:
        from app.exceptions import ToolNotFoundError
        raise ToolNotFoundError(tool_name)

    check_policy(run_id=run_id, spec=spec, payload=payload)

    with start_span(
        "tool_gateway.invoke",
        run_id=run_id,
        attrs={"tool_name": tool_name, "tool_source": spec.source},
    ) as gateway_span:
        start = time.monotonic()

        with start_span(
            "mcp_call",
            run_id=run_id,
            attrs={"tool_name": tool_name},
        ):
            try:
                result = await execute(spec, payload)
                error_info = result.get("error")
                status = "failed" if error_info else "success"
                error = {"type": "ToolError", "message": error_info} if error_info else None
            except Exception as exc:
                result = None
                status = "failed"
                error = {"type": type(exc).__name__, "message": str(exc)}

        latency_ms = int((time.monotonic() - start) * 1000)
        gateway_span.set_attribute("tool.status", status)
        gateway_span.set_attribute("tool.latency_ms", latency_ms)

    record = ToolInvocationRecord(
        run_id=run_id,
        tool_name=tool_name,
        request_payload=payload,
        response_payload=result,
        status=status,
        latency_ms=latency_ms,
        error=error,
    )

    await log_invocation(record)
    return record
