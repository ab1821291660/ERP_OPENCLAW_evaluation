from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun
from app.enums import RunStatus


class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, run: AgentRun) -> AgentRun:
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get(self, run_id: str) -> AgentRun | None:
        result = await self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, run_id: str, status: RunStatus, **kwargs
    ) -> AgentRun | None:
        run = await self.get(run_id)
        if run is None:
            return None
        run.status = status.value
        for key, value in kwargs.items():
            if hasattr(run, key):
                setattr(run, key, value)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def list_runs(self, limit: int = 20) -> list[AgentRun]:
        result = await self.session.execute(
            select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
