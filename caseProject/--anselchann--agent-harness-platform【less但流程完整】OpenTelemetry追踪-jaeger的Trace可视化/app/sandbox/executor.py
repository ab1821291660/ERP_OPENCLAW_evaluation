"""
Sandbox Executor - controlled execution environment for high-risk tool calls.

Phase 7: real subprocess execution with policy enforcement and audit.
"""

import time
import subprocess
from typing import Protocol

from app.sandbox.policy import check_command
from app.sandbox.limits import default_limits


class SandboxExecutor(Protocol):
    def execute(
        self, command: list[str], cwd: str, timeout_seconds: int
    ) -> dict: ...


class LocalSandboxExecutor:
    """Local executor with timeout, cwd constraints, and command allowlist."""

    def execute(
        self,
        command: list[str],
        cwd: str = "",
        timeout_seconds: int = 0,
    ) -> dict:
        if not cwd:
            cwd = default_limits.allowed_working_dir
        if timeout_seconds <= 0:
            timeout_seconds = default_limits.timeout_seconds

        check_command(command)

        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            stdout = proc.stdout[:default_limits.max_output_bytes] if proc.stdout else ""
            stderr = proc.stderr[:default_limits.max_output_bytes] if proc.stderr else ""

            return {
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration_ms": duration_ms,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"TimeoutExpired after {timeout_seconds}s",
                "duration_ms": timeout_seconds * 1000,
                "timed_out": True,
            }


executor = LocalSandboxExecutor()
