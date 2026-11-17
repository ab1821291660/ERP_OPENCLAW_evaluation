"""
Filesystem tool implementation - exposes safe file system operations.

Tools:
- fs_list_dir: list files in a directory
- fs_read_file: read content of a file
"""

import os
from pathlib import Path

SAFE_BASE = os.getenv("FS_TOOL_BASE_DIR", os.getcwd())


def _resolve_path(path: str) -> Path:
    """Resolve and validate a path stays within the safe base directory."""
    base = Path(SAFE_BASE).resolve()
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        raise PermissionError(f"Access denied: {path} is outside {SAFE_BASE}")
    return target


async def fs_list_dir(payload: dict) -> dict:
    """List files and directories at the given path."""
    path = payload.get("path", ".")
    target = _resolve_path(path)
    if not target.exists():
        return {"error": f"Path not found: {path}", "items": []}
    if not target.is_dir():
        return {"error": f"Not a directory: {path}", "items": []}

    items = []
    for entry in sorted(target.iterdir()):
        items.append({
            "name": entry.name,
            "type": "dir" if entry.is_dir() else "file",
            "size": entry.stat().st_size if entry.is_file() else None,
        })
    return {"path": str(target), "count": len(items), "items": items}


async def fs_read_file(payload: dict) -> dict:
    """Read the content of a file."""
    path = payload.get("path", "")
    target = _resolve_path(path)
    if not target.exists():
        return {"error": f"File not found: {path}", "content": None}
    if not target.is_file():
        return {"error": f"Not a file: {path}", "content": None}

    try:
        content = target.read_text(encoding="utf-8")
        max_chars = payload.get("max_chars", 5000)
        truncated = len(content) > max_chars
        return {
            "path": str(target),
            "content": content[:max_chars],
            "size": len(content),
            "truncated": truncated,
        }
    except UnicodeDecodeError:
        return {"error": f"Cannot read {path} as text (binary file)", "content": None}


# Map tool names to callable functions
TOOL_HANDLERS = {
    "fs_list_dir": fs_list_dir,
    "fs_read_file": fs_read_file,
}
