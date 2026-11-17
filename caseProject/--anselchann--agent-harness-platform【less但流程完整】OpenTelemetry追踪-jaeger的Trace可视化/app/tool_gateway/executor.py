"""
Tool Executor - dispatches tool invocations to actual implementations.

Maps tool names registered in the gateway to handler functions.
"""

import asyncio

from app.schemas.tools import ToolSpec
from mcp_servers.filesystem_server import TOOL_HANDLERS as FS_HANDLERS
from mcp_servers.sandbox_server import TOOL_HANDLERS as SB_HANDLERS


# Aggregate all available tool handlers
_ALL_HANDLERS: dict[str, object] = {}
_ALL_HANDLERS.update(FS_HANDLERS)
_ALL_HANDLERS.update(SB_HANDLERS)


async def execute(spec: ToolSpec, payload: dict) -> dict:
    """Execute a tool by name with the given payload."""
    handler = _ALL_HANDLERS.get(spec.tool_name)
    if handler is None:
        raise ValueError(f"No handler registered for tool: {spec.tool_name}")

    timeout = spec.timeout_seconds or 30
    try:
        result = await asyncio.wait_for(handler(payload), timeout=timeout)
    except asyncio.TimeoutError:
        return {"error": f"Tool {spec.tool_name} timed out after {timeout}s"}
    except Exception as exc:
        return {"error": f"Tool execution failed: {str(exc)}"}

    return result
