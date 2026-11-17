from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ToolInvocation


class ToolInvocationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_run(self, run_id: str) -> list[ToolInvocation]:
        result = await self.session.execute(
            select(ToolInvocation)
            .where(ToolInvocation.run_id == run_id)
            .order_by(ToolInvocation.created_at)
        )
        return list(result.scalars().all())

    async def stats(self, tool_name: str | None = None) -> dict:
        q = select(
            func.count(ToolInvocation.id).label("total"),
            func.sum(
                func.case((ToolInvocation.status == "success", 1), else_=0)
            ).label("successes"),
            func.avg(ToolInvocation.latency_ms).label("avg_latency_ms"),
        )
        if tool_name:
            q = q.where(ToolInvocation.tool_name == tool_name)
        result = await self.session.execute(q)
        row = result.one()
        total = row.total or 0
        successes = row.successes or 0
        return {
            "total_calls": total,
            "success_rate": (successes / total) if total > 0 else 0,
            "avg_latency_ms": round(row.avg_latency_ms, 1) if row.avg_latency_ms else None,
        }
