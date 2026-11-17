"""Celery task definition for evaluation runs."""


async def execute_eval_run(eval_id: str) -> dict:
    """Execute an evaluation run and return summary."""
    # Phase 5: eval runs are dispatched via asyncio.create_task directly
    # from the API router. This module is a placeholder for future Celery migration.
    return {"eval_id": eval_id, "status": "delegated to async task"}
