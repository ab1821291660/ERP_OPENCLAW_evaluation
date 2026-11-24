"""Agent 对话接口，仅提供对话与停止，不包含数据浏览、反馈或遥测。"""

from fastapi import APIRouter, HTTPException
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app.logging_config import get_request_id, new_request_id
from app.schemas import AgentRequest, AgentResponse

from app.session_store import (
    SessionBusyError, SessionNotFoundError, release_run, reserve_run,
)
from app.streaming import buffered_events##===================================
from app.services import run_agent, run_events##===================================
router = APIRouter(prefix="/v1/agent", tags=["agent"])



async def prepare(payload: AgentRequest):
    try:
        return await reserve_run(payload.session_id, get_request_id() or new_request_id())
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



@router.post("/stream")
async def stream_agent(payload: AgentRequest) -> StreamingResponse:
    control = await prepare(payload)
    return StreamingResponse(
        buffered_events(##见app.streaming##===================================
                run_events(payload, control)),##见app.services##===================================
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        # 如果响应尚未消费生成器就断开，仍释放已经登记的会话占用。
        background=BackgroundTask(release_run, payload.session_id, control.request_id),
    )
@router.post("/invoke", response_model=AgentResponse)
async def invoke_agent(payload: AgentRequest) -> dict:
    control = await prepare(payload)
    try:
        return await run_agent(payload, control)##见app.services--run_agent里面调run_events##===================================
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
