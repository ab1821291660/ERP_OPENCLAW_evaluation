"""固定 demo-user 的会话目录、历史和停止接口。"""

from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas import SessionCreate, SessionResponse, SessionUpdate
from app.session_store import (
    SessionBusyError, clear_sessions, create_session, delete_session, get_history,
    get_session, list_sessions, stop_run, update_session,
)


router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def new_session(payload: SessionCreate) -> dict:
    return await create_session(payload.title)


@router.get("", response_model=list[SessionResponse])
async def sessions(limit: int = Query(200, ge=1, le=200), offset: int = Query(0, ge=0)):
    return await list_sessions(limit, offset)


@router.get("/{session_id}/messages")
async def messages(session_id: str):
    history = await get_history(session_id)
    if history is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return history


@router.patch("/{session_id}", response_model=SessionResponse)
async def rename(session_id: str, payload: SessionUpdate):
    result = await update_session(session_id, title=payload.title)
    if result is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


@router.post("/{session_id}/stop")
async def stop(session_id: str):
    if await get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"stopping": stop_run(session_id)}


@router.delete("")
async def clear():
    try:
        return {"deleted_count": await clear_sessions()}
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{session_id}", status_code=204)
async def remove(session_id: str):
    try:
        found = await delete_session(session_id)
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not found:
        raise HTTPException(status_code=404, detail="会话不存在")
    return Response(status_code=204)
