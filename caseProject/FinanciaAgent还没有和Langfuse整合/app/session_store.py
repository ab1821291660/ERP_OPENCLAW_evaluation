"""Store 管理会话目录，Checkpointer 管理图状态；执行占用只存在于进程内。"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from app.agent_factory import get_agent, get_checkpointer, get_store  ##===================================##===================================


DEMO_USER_ID = "demo-user"
SESSION_NAMESPACE = ("users", DEMO_USER_ID, "sessions")


class SessionBusyError(RuntimeError):
    """禁止同一会话并行执行，或在执行期间删除它。"""


class SessionNotFoundError(RuntimeError):
    """调用端指定的会话不在当前用户目录中。"""


@dataclass
class RunControl:
    """仅用于当前运行的停止信号，不写入本地请求表。"""
    request_id: str
    cancel: asyncio.Event


_active_runs: dict[str, RunControl] = {}
_deleting: set[str] = set()
_clearing = False


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def message_text(content: Any) -> str:
    """统一处理 SDK 消息的字符串、文本块和工具结果对象。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text") or block.get("content") or "")
            if isinstance(block, dict) else str(block)
            for block in content
        )
    if content is None:
        return ""
    import json
    return json.dumps(content, ensure_ascii=False, default=str)





def ________session相关(self):pass
async def create_session(title: str | None = None) -> dict:
    session_id = str(uuid4())
    now = utc_iso()
    value = {
        "title": (title or "新会话").strip() or "新会话",
        "created_at": now,
        "updated_at": now,
        "last_message_preview": "",
    }
    await get_store().aput(SESSION_NAMESPACE, session_id, value)##===================================##===================================
    return {"session_id": session_id, "user_id": DEMO_USER_ID, **value}
async def touch_session(session_id: str, question: str, preview: str) -> None:
    current = await get_session(session_id)##===================================
    if current is None:
        return
    changes = {"last_message_preview": preview.strip().replace("\n", " ")[:100]}
    if current["title"] == "新会话":
        changes["title"] = question.replace("\n", " ")[:36]
    await update_session(session_id, **changes)##===================================



async def delete_session(session_id: str) -> bool:
    if session_id in _active_runs or session_id in _deleting:
        raise SessionBusyError("请先停止生成，再删除会话")
    # 删除期间阻止新的 Agent 请求写入同一个 thread。
    _deleting.add(session_id)
    try:
        if await get_session(session_id) is None:
            return False
        await get_checkpointer().adelete_thread(session_id)
        await get_store().adelete(SESSION_NAMESPACE, session_id)##===================================##===================================
        return True
    finally:
        _deleting.discard(session_id)


async def clear_sessions() -> int:
    global _clearing
    if _active_runs or _clearing or _deleting:
        raise SessionBusyError("请先停止所有生成任务，再清空历史")
    _clearing = True
    try:
        rows = await list_sessions(limit=2_000_000)
        count = 0
        for row in rows:
            count += int(await delete_session(row["session_id"]))
        return count
    finally:
        _clearing = False

async def update_session(session_id: str, **changes: Any) -> dict | None:
    current = await get_session(session_id)##===================================
    if current is None:
        return None
    value = {
        "title": current["title"],
        "created_at": current["created_at"],
        "updated_at": utc_iso(),
        "last_message_preview": current.get("last_message_preview", ""),
    }
    for key in ("title", "last_message_preview"):
        if key in changes:
            value[key] = changes[key]
    await get_store().aput(SESSION_NAMESPACE, session_id, value)##===================================##===================================
    return {"session_id": session_id, "user_id": DEMO_USER_ID, **value}



async def get_session(session_id: str) -> dict | None:
    item = await get_store().aget(SESSION_NAMESPACE, session_id)##===================================##===================================
    if item is None:
        return None
    return {"session_id": session_id, "user_id": DEMO_USER_ID, **item.value}

async def list_sessions(limit: int = 200, offset: int = 0) -> list[dict]:
    """先读取目录再按更新时间排序，避免数据库默认顺序影响最近会话。"""
    items = []
    cursor = 0
    while True:
        batch = await get_store().asearch(SESSION_NAMESPACE, limit=200, offset=cursor)##===================================##===================================
        items.extend(batch)
        if len(batch) < 200:
            break
        cursor += len(batch)
    rows = [
        {"session_id": item.key, "user_id": DEMO_USER_ID, **item.value}
        for item in items
    ]
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    return rows[offset:offset + limit]








def ________run相关(self):pass
async def reserve_run(session_id: str, request_id: str) -> RunControl:
    """先原子登记占用再检查目录，避免删除会话与启动任务之间的竞态。"""
    if _clearing or session_id in _deleting or session_id in _active_runs:
        raise SessionBusyError("该会话正在执行，请等待完成或先停止生成")
    control = RunControl(request_id, asyncio.Event())
    _active_runs[session_id] = control
    try:
        if await get_session(session_id) is None:
            raise SessionNotFoundError("会话不存在，请新建会话")
    except BaseException:
        release_run(session_id, request_id)
        raise
    return control


def release_run(session_id: str, request_id: str) -> None:
    current = _active_runs.get(session_id)
    if current is not None and current.request_id == request_id:
        _active_runs.pop(session_id, None)


def stop_run(session_id: str) -> bool:
    current = _active_runs.get(session_id)
    if current is None:
        return False
    current.cancel.set()
    return True


def stop_all_runs() -> None:
    for current in _active_runs.values():
        current.cancel.set()






def ________history历史数据__get_agent__aget_state(self):pass
def serialize_message(message: BaseMessage, index: int) -> dict | None:
    """只恢复 Checkpointer 实际保存的消息，不伪造临时子 Agent 过程。"""
    if isinstance(message, HumanMessage):
        role = "human"
    elif isinstance(message, AIMessage):
        role = "ai"
    elif isinstance(message, ToolMessage):
        role = "tool"
    else:
        return None
    result = {
        "id": message.id or f"history-{index}",
        "role": role,
        "content": message_text(message.content),
        "agent": "main",
        "streaming": False,
    }
    if isinstance(message, AIMessage):
        result["tool_calls"] = message.tool_calls
    if isinstance(message, ToolMessage):
        result.update(
            name=message.name or "tool",
            tool_call_id=message.tool_call_id,
            status=getattr(message, "status", "success"),
        )
    return result

async def get_history(session_id: str) -> list[dict] | None:
    if await get_session(session_id) is None:
        return None
    snapshot = await get_agent().aget_state({"configurable": {"thread_id": session_id}})##===================================
    return [
        serialized
        for index, message in enumerate(snapshot.values.get("messages") or [])
        if (serialized := serialize_message(message, index)) is not None##===================================
    ]
