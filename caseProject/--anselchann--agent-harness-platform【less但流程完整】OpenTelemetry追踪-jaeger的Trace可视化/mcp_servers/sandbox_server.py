"""
Sandbox tool implementation - controlled shell command execution.

Tool:
- exec_command: execute a shell command within sandbox boundaries
"""

from app.sandbox.executor import executor
from app.sandbox.limits import default_limits


async def exec_command(payload: dict) -> dict:
    """
    Execute a shell command in the sandbox.

    Payload:
        command: list[str] — command and arguments
        cwd: str — working directory (default: limits.allowed_working_dir)
    """
    command = payload.get("command", [])
    if isinstance(command, str):
        import shlex
        command = shlex.split(command)

    cwd = payload.get("cwd", default_limits.allowed_working_dir)
    timeout = payload.get("timeout_seconds", default_limits.timeout_seconds)

    result = executor.execute(command, cwd=cwd, timeout_seconds=timeout)
    return result


TOOL_HANDLERS = {
    "exec_command": exec_command,
}
