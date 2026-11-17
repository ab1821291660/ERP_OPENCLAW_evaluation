import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun
from app.db.session import get_db, _sessionmaker
from app.db.repositories.runs import RunRepository
from app.schemas.runs import (
    RunCreated,
    RunInput,
    RunResponse,
    RunMetrics,
    RunTraceResponse,
)
from app.enums import RunStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


async def _execute_and_persist(run_id: str, task_type: str, user_input: dict, config: dict):
    """Background task: execute the agent workflow and update the DB."""
    from app.runtime.runner import execute_run

    maker = _sessionmaker()
    async with maker() as session:
        repo = RunRepository(session)
        try:
            result = await execute_run(run_id, task_type, user_input, config)
            output = result.get("final_output")
            error = result.get("error")
            final_status = result.get("status", "completed")

            await repo.update_status(
                run_id,
                RunStatus(final_status) if final_status in ("completed", "failed") else RunStatus.COMPLETED,
                output_payload=output,
                error_payload=error,
                metrics_payload={
                    "tool_calls": len(result.get("tool_calls", [])),
                    "steps": len(result.get("intermediate_results", [])),
                },
            )
            logger.info("Run %s completed with status %s", run_id, final_status)
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            await repo.update_status(
                run_id,
                RunStatus.FAILED,
                error_payload={"type": type(exc).__name__, "message": str(exc)},
            )


@router.post("", response_model=RunCreated, status_code=201)
async def create_run(
    body: RunInput, db: AsyncSession = Depends(get_db)
) -> RunCreated:
    """Create a new agent run, persist, and dispatch background execution."""
    repo = RunRepository(db)

    run = AgentRun(
        agent_name=body.agent_name,
        task_type=body.task_type,
        input_payload=body.input,
        config_payload=body.config.model_dump(),
        status=RunStatus.RUNNING,
    )
    await repo.create(run)

    asyncio.create_task(
        _execute_and_persist(
            run_id=run.id,
            task_type=body.task_type,
            user_input=body.input,
            config=body.config.model_dump(),
        )
    )

    return RunCreated(run_id=run.id, status=RunStatus.RUNNING)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)) -> RunResponse:
    """Get the current status and result of a run."""
    repo = RunRepository(db)
    run = await repo.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    metrics = None
    if run.metrics_payload:
        metrics = RunMetrics(
            latency_ms=None,
            tool_calls=run.metrics_payload.get("tool_calls", 0),
            estimated_cost_usd=None,
        )

    return RunResponse(
        run_id=run.id,
        status=run.status,
        input=run.input_payload,
        output=run.output_payload,
        metrics=metrics,
        error=run.error_payload,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get("/{run_id}/trace", response_model=RunTraceResponse)
async def get_run_trace(run_id: str) -> RunTraceResponse:
    """Get the full trace (spans) for a run."""
    from app.evals.observability.tracing import get_trace

    trace_data = get_trace(run_id)
    if trace_data is None:
        raise HTTPException(status_code=404, detail=f"No trace found for run {run_id}")

    return RunTraceResponse(
        run_id=run_id,
        trace_id=trace_data["trace_id"],
        trace_url=None,  # Phase 4: set Jaeger/Phoenix URL when configured
    )


@router.get("/{run_id}/trace/spans")
async def get_run_trace_spans(run_id: str) -> dict:
    """Get the full span list for a run."""
    from app.evals.observability.tracing import get_trace

    trace_data = get_trace(run_id)
    if trace_data is None:
        raise HTTPException(status_code=404, detail=f"No trace found for run {run_id}")
    return trace_data
