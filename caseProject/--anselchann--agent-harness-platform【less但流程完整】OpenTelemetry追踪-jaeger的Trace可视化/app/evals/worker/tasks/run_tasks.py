"""
Task definitions for agent run execution.

Phase 2 will implement Celery/RQ tasks that:
1. Receive a run_id
2. Load the agent config
3. Execute via platform.runtime.runner
4. Persist results
"""


def execute_agent_run(run_id: str) -> dict:
    """Stub for agent run execution task."""
    return {"run_id": run_id, "status": "stub"}
