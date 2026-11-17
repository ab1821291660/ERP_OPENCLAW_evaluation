class AgentHarnessError(Exception):
    """Base exception for the platform."""


class RunNotFoundError(AgentHarnessError):
    def __init__(self, run_id: str):
        super().__init__(f"Run {run_id} not found")


class ToolNotFoundError(AgentHarnessError):
    def __init__(self, tool_name: str):
        super().__init__(f"Tool {tool_name} not found")


class ToolPolicyDeniedError(AgentHarnessError):
    def __init__(self, tool_name: str, reason: str):
        super().__init__(f"Tool {tool_name} denied: {reason}")


class EvalNotFoundError(AgentHarnessError):
    def __init__(self, eval_id: str):
        super().__init__(f"Eval run {eval_id} not found")


class DatasetNotFoundError(AgentHarnessError):
    def __init__(self, dataset_name: str):
        super().__init__(f"Dataset {dataset_name} not found")


class SandboxTimeoutError(AgentHarnessError):
    def __init__(self, command: str, timeout_s: int):
        super().__init__(f"Command '{command}' exceeded {timeout_s}s timeout")


class SandboxPolicyViolation(AgentHarnessError):
    def __init__(self, command: str, reason: str):
        super().__init__(f"Sandbox policy violation for '{command}': {reason}")
