"""DeepAgents v3 协议转换与 SSE 队列；不依赖遥测 SDK 或页面消息快照。"""

import asyncio
from contextlib import aclosing, suppress
import json
from typing import Any, AsyncIterator
from uuid import uuid4

from langchain_core.messages import BaseMessage

from app.agent_factory import get_agent
from app.config import get_settings
from app.session_store import message_text


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


class EventAdapter:
    """把 v3 消息块、工具生命周期和子图生命周期转换成前端稳定事件。"""

    def __init__(self) -> None:
        self.messages: dict[tuple, str] = {}
        self.namespaces: dict[tuple, str] = {}
        self.tools: dict[str, dict] = {}

    def source(self, namespace: tuple, metadata: dict | None = None) -> str:
        explicit = (metadata or {}).get("lc_agent_name") or (metadata or {}).get("agent_name")
        if explicit in {"researcher", "reviewer"}:
            self.namespaces[namespace] = explicit
            return explicit
        for depth in range(len(namespace), 0, -1):
            if namespace[:depth] in self.namespaces:
                return self.namespaces[namespace[:depth]]
        return "subagent" if any(str(s).startswith("tools:") for s in namespace) else "main"

    def convert(self, event: dict) -> list[dict]:
        params = event.get("params") or {}
        namespace = tuple(params.get("namespace") or ())
        method = event.get("method")
        data = params.get("data")
        results = []

        if method == "lifecycle" and isinstance(data, dict):
            path = tuple(data.get("namespace") or namespace)
            name = data.get("graph_name")
            cause = data.get("cause") or {}
            if isinstance(cause, dict):
                cause_input = cause.get("input")
                if isinstance(cause_input, dict):
                    name = name or cause_input.get("subagent_type")
            if name not in {"researcher", "reviewer"}:
                name = self.source(path)
            if name == "main":
                return results
            self.namespaces[path] = name
            status = data.get("event", "")
            results.append({
                "event": "agent_start" if status == "started" else "agent_end",
                "data": {"agent": name, "namespace": list(path), "status": status},
            })

        elif method == "messages" and isinstance(data, (list, tuple)) and data:
            payload = data[0]
            metadata = data[1] if len(data) > 1 and isinstance(data[1], dict) else {}
            if not isinstance(payload, dict):
                return results
            source = self.source(namespace, metadata)
            kind = payload.get("event")
            if kind == "message-start":
                # v3 的正式字段为 message_id；与 Checkpointer ID 对齐，避免最终答案重复。
                message_id = payload.get("message_id") or payload.get("id") or str(uuid4())
                self.messages[namespace] = message_id
                results.append({"event": "message_start", "data": {
                    "message_id": message_id, "agent": source,
                }})
            elif kind == "content-block-delta":
                delta = payload.get("delta") or {}
                if delta.get("type") == "text-delta" and delta.get("text"):
                    message_id = self.messages.get(namespace)
                    if message_id is None:
                        message_id = str(uuid4())
                        self.messages[namespace] = message_id
                        results.append({"event": "message_start", "data": {
                            "message_id": message_id, "agent": source,
                        }})
                    results.append({"event": "text_delta", "data": {
                        "message_id": message_id, "agent": source,
                        "content": delta["text"],
                    }})
            elif kind == "message-finish" and namespace in self.messages:
                results.append({"event": "message_complete", "data": {
                    "message_id": self.messages[namespace], "agent": source,
                }})

        elif method == "tools" and isinstance(data, dict):
            source = self.source(namespace)
            call_id = data.get("tool_call_id") or str(uuid4())
            kind = data.get("event")
            if kind == "tool-started":
                details = {
                    "tool_call_id": call_id,
                    "name": data.get("tool_name") or "tool",
                    "agent": source,
                    "arguments": json.dumps(data.get("input") or {}, ensure_ascii=False, default=str),
                }
                self.tools[call_id] = details
                results.append({"event": "tool_start", "data": details})
            elif kind == "tool-output-delta":
                results.append({"event": "tool_delta", "data": {
                    "tool_call_id": call_id, "content": message_text(data.get("delta")),
                }})
            elif kind in {"tool-finished", "tool-error"}:
                output = data.get("output")
                status = "error" if kind == "tool-error" else "success"
                if isinstance(output, BaseMessage):
                    status = getattr(output, "status", status)
                    output = output.content
                details = self.tools.get(call_id, {
                    "tool_call_id": call_id, "name": "tool", "agent": source, "arguments": "",
                })
                results.append({"event": "tool_result", "data": {
                    **details, "status": status,
                    "content": data.get("message", "") if kind == "tool-error" else message_text(output),
                }})
        return results


async def graph_events(message: BaseMessage, config: dict, cancel: asyncio.Event) -> AsyncIterator[dict]:
    """取消信号通过 v3 run.abort 传播到模型、工具及子 Agent。"""
    adapter = EventAdapter()
    async with await get_agent().astream_events(##===================================##===================================
        {"messages": [message]}, config=config, version="v3",
    ) as run:
        async def stop_on_signal() -> None:
            await cancel.wait()
            await run.abort()
        stopper = asyncio.create_task(stop_on_signal())##===================================
        try:
            async for event in run:
                for converted in adapter.convert(event):
                    yield converted
        finally:
            stopper.cancel()##===================================
            with suppress(asyncio.CancelledError):
                await stopper


async def buffered_events(events: AsyncIterator[dict]) -> AsyncIterator[str]:
    """独立生产任务 + 有界队列；断连时关闭生成器并等待生产任务退出。"""
    settings = get_settings()
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=settings.sse_queue_size)
    sentinel = object()

    async def produce() -> None:
        try:
            async with aclosing(events):
                async for event in events:
                    await queue.put(event)
        finally:
            # 断连时消费者已停止，不能让取消任务卡在满队列的 put 中。
            if not asyncio.current_task().cancelling():
                await queue.put(sentinel)

    producer = asyncio.create_task(produce())
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=settings.sse_heartbeat_seconds)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if event is sentinel:
                await producer
                break
            yield sse_event(event["event"], event["data"])
    finally:
        producer.cancel()
        with suppress(asyncio.CancelledError):
            await producer
