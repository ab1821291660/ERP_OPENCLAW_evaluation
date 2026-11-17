"""
Tool Registry - central registration point for all tools.

Manages ToolSpec entries and provides lookup for the gateway.
"""

from app.schemas.tools import ToolSpec


class ToolRegistry:
    """In-memory tool registry. Phase 2 will back with DB."""

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.tool_name] = spec

    def get(self, tool_name: str) -> ToolSpec | None:
        return self._tools.get(tool_name)

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def unregister(self, tool_name: str) -> None:
        self._tools.pop(tool_name, None)


# Singleton instance
registry = ToolRegistry()
