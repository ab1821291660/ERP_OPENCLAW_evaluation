import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.tools import (
    ToolSpec,
    ToolRegisterRequest,
    ToolInvokeRequest,
    ToolInvocationRecord,
)
from app.tool_gateway.registry import registry
from app.tool_gateway.client import invoke_tool as gateway_invoke
from app.db.session import get_db
from app.db.repositories.tools import ToolInvocationRepository

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolSpec])
async def list_tools() -> list[ToolSpec]:
    """List all registered tools."""
    return registry.list_tools()


@router.post("/register", response_model=ToolSpec, status_code=201)
async def register_tool(body: ToolRegisterRequest) -> ToolSpec:
    """Register a new tool in the gateway."""
    spec = ToolSpec(
        tool_name=body.tool_name,
        source=body.source,
        description=body.description,
        input_schema=body.input_schema,
        timeout_seconds=body.timeout_seconds,
        requires_approval=body.requires_approval,
        tags=body.tags,
    )
    registry.register(spec)
    return spec


@router.post("/{tool_name}/invoke", response_model=ToolInvocationRecord)
async def invoke_tool(
    tool_name: str,
    body: ToolInvokeRequest,
    db: AsyncSession = Depends(get_db),
) -> ToolInvocationRecord:
    """Manually invoke a registered tool for testing/debugging."""
    return await gateway_invoke(
        run_id=f"manual_{uuid.uuid4().hex[:8]}",
        tool_name=tool_name,
        payload=body.payload,
    )


@router.get("/{tool_name}/stats")
async def tool_stats(
    tool_name: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """Get invocation stats for a tool."""
    repo = ToolInvocationRepository(db)
    return await repo.stats(tool_name=tool_name)
