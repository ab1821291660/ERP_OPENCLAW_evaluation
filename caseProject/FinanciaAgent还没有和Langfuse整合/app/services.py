"""对话服务：只编排现有 Agent 和会话组件，不持久化本地请求或追踪映射。"""

import asyncio
from contextlib import aclosing
import logging
import re
from typing import AsyncIterator
from uuid import uuid4

from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError

from app.agent_factory import get_agent
from app.config import get_settings
from app.logging_config import log_event
from app.schemas import AgentRequest
from app.session_store import RunControl, message_text, release_run, touch_session ##========  ##========
from app.streaming import graph_events##后buffered_events ##===================================##===================================


logger = logging.getLogger(__name__)
_FINQA_IDENTIFIER = re.compile(
    r"[A-Za-z0-9._-]+/\d{4}/[A-Za-z0-9._-]+\.pdf-\d+(?:#q\d+)?"
)
def build_agent_config(payload: AgentRequest) -> dict:
    """只有用户原文实际包含精确标识时才注入，不猜测数据分区。"""
    configurable = {"thread_id": payload.session_id}
    match = _FINQA_IDENTIFIER.search(payload.question)
    if match:
        configurable["finqa_identifier"] = match.group(0)
    return {
        "configurable": configurable,
        "recursion_limit": get_settings().max_agent_steps,
    }


def final_ai_message(values: dict) -> AIMessage:
    """只选择本轮最后的主 Agent 非工具回答，避免把旧回答或子 Agent 草稿当成结果。"""
    messages = values.get("messages") or []
    start = next(
        (i + 1 for i in range(len(messages) - 1, -1, -1)
         if isinstance(messages[i], HumanMessage)),
        0,
    )##从messages 列表中从后往前查找最后一个 HumanMessage 实例，并返回它的索引 + 1；如果找不到，则返回 0。
    ##next(..., 0)：：最后一条人类消息之后的位置
    # next() 获取生成器产出的第一个值。由于前面是倒序遍历，所以第一个匹配到的就是最靠后的 HumanMessage。
    # 第二个参数 0 是默认值：如果整个列表中没有找到 HumanMessage，就返回 0。
                # result = 0
                # for i in range(len(messages) - 1, -1, -1):
                #     if isinstance(messages[i], HumanMessage):
                #         result = i + 1
                #         break
                # messages = [
                #     HumanMessage("你好"),  # 索引 0
                #     AIMessage("你好"),  # 索引 1
                #     HumanMessage("继续"),  # 索引 2
                #     AIMessage("好的"),  # 索引 3
                # ]#从后往前找到最后一个 HumanMessage 在索引 2，因此返回：2 + 1 == 3也就是最后一个 HumanMessage 后面的位置。
                # #没有 HumanMessage，返回：0
    for message in reversed(messages[start:]):#取最后一条HumanMessage之后的消息==AIMessage("好的"),  # 索引 3
        if isinstance(message, AIMessage):
            if message.tool_calls or not message_text(message.content).strip():##========
                break
            return message
    raise RuntimeError("本轮未生成完整回答，请重新提问")


async def run_events(payload: AgentRequest, control: RunControl) -> AsyncIterator[dict]:##========
    """所有终态都释放会话占用；本地请求编号仅进入日志和 HTTP/SSE 响应。"""
    config = build_agent_config(payload)##===================================
    human = HumanMessage(
        id=str(uuid4()), content=payload.question,
        additional_kwargs={"request_id": control.request_id},
    )
    log_event(logger, "agent_started", agent_request_id=control.request_id, session_id=payload.session_id)
    try:
        yield {"event": "run_start", "data": {
            "request_id": control.request_id, "session_id": payload.session_id,
            "human_message_id": human.id,
        }}
        await touch_session(payload.session_id, payload.question, payload.question)##===================================
        async with aclosing(graph_events(human, config, control.cancel)) as events:##===================================##===================================##===================================
            async for event in events:
                if event["event"] in {"tool_start", "tool_result", "agent_start", "agent_end"}:
                    log_event(
                        logger, "agent_" + event["event"],
                        agent_request_id=control.request_id, session_id=payload.session_id,
                        **event["data"],
                    )
                yield event



        if control.cancel.is_set():##前端取消##===================================##===================================##===================================
            yield {"event": "done", "data": {"status": "cancelled",
                                             "request_id": control.request_id}}
            return



        snapshot = await get_agent().aget_state({"configurable": {"thread_id": payload.session_id}})##查checkpoint的数据##===================================
        final = final_ai_message(snapshot.values)##===================================
        answer = message_text(final.content)##========
        await touch_session(payload.session_id, payload.question, answer)##========
        yield {"event": "answer_complete", "data": {
            "request_id": control.request_id,
            "session_id": payload.session_id,
            "message_id": final.id or str(uuid4()),
            "answer": answer,
        }}
        yield {"event": "done", "data": {"status": "success", "request_id": control.request_id}}
        log_event(logger, "agent_completed", agent_request_id=control.request_id, session_id=payload.session_id)
    except asyncio.CancelledError:
        log_event(logger, "agent_disconnected", agent_request_id=control.request_id, session_id=payload.session_id)
        raise
    except Exception as exc:
        if control.cancel.is_set():
            yield {"event": "done", "data": {"status": "cancelled",
                                             "request_id": control.request_id}}
        else:
            logger.exception("agent_failed", extra={"event_data": {
                "agent_request_id": control.request_id, "session_id": payload.session_id,
            }})
            if isinstance(exc, GraphRecursionError):
                message = "Agent 达到图执行步数上限，请缩小问题范围后重试"
            elif isinstance(exc, ToolCallLimitExceededError):
                message = "本次任务达到工具调用上限，请缩小问题范围后重试"
            else:
                message = "Agent 执行失败，请根据请求编号查看 logs/error.log"
            yield {"event": "error", "data": {
                "message": message, "request_id": control.request_id,
            }}
            yield {"event": "done", "data": {"status": "error", "request_id": control.request_id}}
    finally:
        release_run(payload.session_id, control.request_id)##========
async def run_agent(payload: AgentRequest, control: RunControl) -> dict:##========
    """非流式接口消费同一条执行链，确保行为和停止逻辑一致。"""
    answer = None
    error = "本次生成已停止"
    async for event in run_events(payload, control):##===================================
        if event["event"] == "answer_complete":
            answer = event["data"]
        elif event["event"] == "error":
            error = event["data"]["message"]
    if answer is None:
        raise RuntimeError(error)
    return answer
