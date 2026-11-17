import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvalRun
from app.db.session import get_db, _sessionmaker
from app.schemas.evals import (
    EvalRunRequest,
    EvalRunCreated,
    EvalRunResponse,
)
from app.enums import EvalStatus
from app.exceptions import DatasetNotFoundError
from app.evals.dataset.dataset import load_dataset, list_datasets
from app.evals.reports.generator import generate_markdown

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evals", tags=["evals"])


async def _execute_eval(eval_id: str, body: EvalRunRequest):
    """Background task: run eval and persist results."""
    from app.evals.evaluators.runner import run_eval

    maker = _sessionmaker()
    async with maker() as session:
        try:
            result = await run_eval(
                eval_id=eval_id,
                dataset_name=body.dataset_name,
                candidate_config=body.candidate_config,
                baseline_config=body.baseline_config if body.baseline_config else None,
                evaluators=body.evaluators,
            )
            await session.execute(
                __import__("sqlalchemy").update(EvalRun)
                .where(EvalRun.id == eval_id)
                .values(
                    status=EvalStatus.COMPLETED,
                    summary_payload=result,
                )
            )
            await session.commit()
            logger.info("Eval %s completed: %s/%s passed", eval_id, result.get("pass_count", 0), result.get("total_cases", 0))
        except Exception as exc:
            logger.exception("Eval %s failed", eval_id)
            await session.execute(
                __import__("sqlalchemy").update(EvalRun)
                .where(EvalRun.id == eval_id)
                .values(
                    status=EvalStatus.FAILED,
                    summary_payload={"error": str(exc)},
                )
            )
            await session.commit()


@router.get("/datasets")
async def get_datasets() -> list[str]:
    """List available evaluation datasets."""
    return list_datasets()


@router.post("", response_model=EvalRunCreated, status_code=201)
async def create_eval(
    body: EvalRunRequest, db: AsyncSession = Depends(get_db)
) -> EvalRunCreated:
    """Submit an evaluation run. Executes asynchronously."""
    # Validate dataset exists
    try:
        load_dataset(body.dataset_name)
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail=f"Dataset '{body.dataset_name}' not found")

    eval_run = EvalRun(
        dataset_name=body.dataset_name,
        candidate_config=body.candidate_config,
        baseline_config=body.baseline_config,
        status=EvalStatus.RUNNING,
    )
    db.add(eval_run)
    await db.commit()
    await db.refresh(eval_run)

    asyncio.create_task(_execute_eval(eval_run.id, body))

    return EvalRunCreated(eval_id=eval_run.id, status=EvalStatus.RUNNING)


@router.get("/{eval_id}", response_model=EvalRunResponse)
async def get_eval(
    eval_id: str, db: AsyncSession = Depends(get_db)
) -> EvalRunResponse:
    """Get evaluation run status and summary."""
    from sqlalchemy import select
    result = await db.execute(select(EvalRun).where(EvalRun.id == eval_id))
    eval_run = result.scalar_one_or_none()
    if eval_run is None:
        raise HTTPException(status_code=404, detail=f"Eval {eval_id} not found")

    return EvalRunResponse(
        eval_id=eval_run.id,
        dataset_name=eval_run.dataset_name,
        status=eval_run.status,
        summary=eval_run.summary_payload,
        created_at=eval_run.created_at,
        updated_at=eval_run.updated_at,
    )


@router.get("/{eval_id}/report")
async def get_eval_report(
    eval_id: str, format: str = "json", db: AsyncSession = Depends(get_db)
):
    """Get the full evaluation report in JSON or Markdown format."""
    from sqlalchemy import select
    result = await db.execute(select(EvalRun).where(EvalRun.id == eval_id))
    eval_run = result.scalar_one_or_none()
    if eval_run is None:
        raise HTTPException(status_code=404, detail=f"Eval {eval_id} not found")

    report_data = eval_run.summary_payload or {}
    if format == "md":
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(generate_markdown(report_data), media_type="text/markdown")##===================================
    return report_data
