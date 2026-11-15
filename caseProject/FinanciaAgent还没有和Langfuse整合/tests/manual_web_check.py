"""普通 Python 脚本：离线验证真实 DeepAgents v3、FastAPI、SQLite 历史和停止。

直接在 PyCharm 运行或 python tests/manual_web_check.py；不用 pytest。
所有会话库位于 TemporaryDirectory；不会调用真实模型或修改项目会话数据。
"""

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest.mock import patch
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app import agent_factory, services, streaming
from app.config import get_settings
from app.main import app
from app import session_store


slow_started = Event()
active_streams = 0


class OfflineModel(BaseChatModel):
    """脚本模型负责模拟输出；真实 Agent 图、task 子 Agent 和计算工具照常执行。"""
    role: str = "main"

    @property
    def _llm_type(self):
        return "offline-test"

    def bind_tools(self, tools, **kwargs):
        return self

    def response(self, messages):
        index = next(i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage))
        question = str(messages[index].content)
        results = [m for m in messages[index + 1:] if isinstance(m, ToolMessage)]
        call = None
        if self.role == "main":
            if "慢请求" in question:
                text = "正在执行慢请求"
            elif not results:
                call = ("task", {"subagent_type": "researcher", "description": "离线测试：返回数值20和25，单位百万美元"})
                text = ""
            elif len(results) == 1:
                call = ("task", {"subagent_type": "reviewer", "description": "离线测试：对20至25的增长率进行独立复核"})
                text = ""
            else:
                text = "离线主 Agent：20至25的增长率为25%，研究与独立复核已完成。"
        elif self.role == "researcher":
            text = "离线 researcher：原始数值20和25，单位百万美元，证据仅用于链路测试。"
        elif not results:
            call = ("safe_calculate", {"expression": "(25-20)/20*100"})
            text = ""
        else:
            text = "离线 reviewer：公式(25-20)/20*100，复核结果25%。"
        calls = [] if call is None else [{"id": str(uuid4()), "name": call[0], "args": call[1], "type": "tool_call"}]
        return AIMessage(id=str(uuid4()), content=text, tool_calls=calls)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self.response(messages))])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        global active_streams
        active_streams += 1
        try:
            result = self.response(messages)
            if result.tool_calls:
                call = result.tool_calls[0]
                yield ChatGenerationChunk(message=AIMessageChunk(
                    id=result.id, content="", tool_call_chunks=[{
                        "name": call["name"], "args": json.dumps(call["args"], ensure_ascii=False),
                        "id": call["id"], "index": 0,
                    }],
                ))
            else:
                for character in result.content:
                    yield ChatGenerationChunk(message=AIMessageChunk(id=result.id, content=character))
                    await asyncio.sleep(0)
                if "慢请求" in result.content:
                    slow_started.set()
                    await asyncio.sleep(30)
        finally:
            active_streams -= 1


def parse_sse(text):
    result = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        lines = block.splitlines()
        event = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = [line[6:] for line in lines if line.startswith("data: ")]
        if event and data:
            result.append((event, json.loads("\n".join(data))))
    return result


@asynccontextmanager
async def test_lifespan(application):
    await agent_factory.initialize_agent_runtime()
    try:
        yield
    finally:
        session_store.stop_all_runs()
        await agent_factory.close_agent_runtime()


def check_http():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/v1/agent/invoke", json={"question": "测试", "session_id": "missing"}).status_code == 404
        response = client.post("/v1/sessions", json={})
        assert response.status_code == 201, response.text
        sid = response.json()["session_id"]
        payload = {"question": "请研究并独立复核20至25的增长率", "session_id": sid}
        response = client.post("/v1/agent/stream", json=payload)
        assert response.status_code == 200, response.text
        events = parse_sse(response.text)
        assert events, response.text
        names = [name for name, data in events]
        assert "text_delta" in names and "tool_start" in names and "tool_result" in names, names
        sources = {data.get("agent") for name, data in events if name == "text_delta"}
        assert {"main", "researcher", "reviewer"} <= sources, sources
        assert any(data.get("name") == "safe_calculate" for name, data in events if name == "tool_start"), events
        assert events[-1][0] == "done" and events[-1][1]["status"] == "success", events[-4:]
        answer = next(data for name, data in events if name == "answer_complete")
        assert any(
            data.get("message_id") == answer["message_id"] and data.get("agent") == "main"
            for name, data in events if name == "message_start"
        ), "流式消息 ID 与最终 Checkpointer 消息未对齐"
        assert "25%" in answer["answer"], answer
        assert response.headers.get("X-Request-ID") == answer["request_id"]
        history = client.get(f"/v1/sessions/{sid}/messages").json()
        assert sum(message["role"] == "human" for message in history) == 1
        assert history[-1]["content"] == answer["answer"], history
        assert any(message["role"] == "tool" for message in history), history
        response = client.post("/v1/agent/invoke", json={"question": "请第二轮复核同一增长率", "session_id": sid})
        assert response.status_code == 200, response.text
        assert "25%" in response.json()["answer"]
        assert sum(message["role"] == "human" for message in client.get(f"/v1/sessions/{sid}/messages").json()) == 2
        assert client.patch(f"/v1/sessions/{sid}", json={"title": "离线验证会话"}).status_code == 200
        print("PASS：真实 v3 文本/工具/两个默认 SubAgent，HTTP 与两轮 Checkpointer 历史")

        slow_sid = client.post("/v1/sessions", json={}).json()["session_id"]
        collected = {}
        def invoke_slow():
            try:
                collected["response"] = client.post("/v1/agent/invoke", json={"question": "慢请求", "session_id": slow_sid})
            except BaseException as exc:
                collected["error"] = exc
        thread = Thread(target=invoke_slow, daemon=True)
        thread.start()
        assert slow_started.wait(5), "慢请求未进入模型输出"
        assert client.post("/v1/agent/invoke", json={"question": "重复请求", "session_id": slow_sid}).status_code == 409
        assert client.delete(f"/v1/sessions/{slow_sid}").status_code == 409
        assert client.post(f"/v1/sessions/{slow_sid}/stop").json()["stopping"] is True
        thread.join(8)
        assert not thread.is_alive(), "停止没有及时取消图执行"
        assert "error" not in collected, collected
        assert collected["response"].status_code == 503, collected["response"].text
        assert client.delete(f"/v1/sessions/{slow_sid}").status_code == 204
        assert not session_store._active_runs, session_store._active_runs
        print("PASS：同会话并发保护、执行中禁止删除、真实 v3 abort 和占用释放")

    # 再次初始化同一临时数据库，证明历史不是靠进程内列表保存。
    with TestClient(app) as client:
        sessions = client.get("/v1/sessions").json()
        assert any(item["session_id"] == sid and item["title"] == "离线验证会话" for item in sessions)
        assert sum(m["role"] == "human" for m in client.get(f"/v1/sessions/{sid}/messages").json()) == 2
        assert client.delete(f"/v1/sessions/{sid}").status_code == 204
        assert client.get(f"/v1/sessions/{sid}/messages").status_code == 404
        client.post("/v1/sessions", json={})
        client.post("/v1/sessions", json={})
        assert client.delete("/v1/sessions").json()["deleted_count"] == 2
        assert client.get("/v1/sessions").json() == []
        print("PASS：重启恢复、重命名、单条删除和清空历史")


async def check_disconnect():
    await agent_factory.initialize_agent_runtime()
    try:
        session = await session_store.create_session()
        sid = session["session_id"]
        control = await session_store.reserve_run(sid, "disconnect-test")
        from app.schemas import AgentRequest
        events = services.run_events(AgentRequest(question="慢请求", session_id=sid), control)
        try:
            while True:
                event = await asyncio.wait_for(anext(events), 3)
                if event["event"] == "text_delta":
                    break
        finally:
            await asyncio.wait_for(events.aclose(), 3)
        await asyncio.sleep(0)
        assert sid not in session_store._active_runs
        assert active_streams == 0, "页面断连后仍有离线模型在后台流式输出"
        await session_store.delete_session(sid)
        print("PASS：真实 Agent SSE 消费者断连关闭图及模型流")
    finally:
        await agent_factory.close_agent_runtime()


async def check_queue():
    closed = asyncio.Event()
    async def source():
        try:
            yield {"event": "test", "data": {"content": "中文"}}
            await asyncio.sleep(30)
        finally:
            closed.set()
    output = streaming.buffered_events(source())
    first = await anext(output)
    assert "中文" in first
    assert await asyncio.wait_for(anext(output), 1) == ": heartbeat\n\n"
    await output.aclose()
    assert closed.is_set(), "断连未关闭队列生产任务"
    print("PASS：SSE 心跳、有界队列及消费者断连清理")


def main():
    with TemporaryDirectory(prefix="finqa-web-check-") as temp:
        settings = get_settings().model_copy(update={
            "checkpoint_db_path": str(Path(temp) / "checkpoints.db"),
            "store_db_path": str(Path(temp) / "store.db"),
            "log_dir": str(Path(temp) / "logs"),
            "sse_heartbeat_seconds": 0.1,
        })
        original_lifespan = app.router.lifespan_context
        app.router.lifespan_context = test_lifespan
        try:
            with patch.object(agent_factory, "get_settings", return_value=settings), \
                 patch.object(agent_factory, "build_model", side_effect=lambda: OfflineModel(role="main")), \
                 patch.object(agent_factory, "build_reviewer_model", side_effect=lambda: OfflineModel(role="reviewer")), \
                 patch.object(services, "get_settings", return_value=settings), \
                 patch.object(streaming, "get_settings", return_value=settings):
                # researcher 在当前工厂继承主模型。通过模型输入中的 system 提示识别角色。
                original_response = OfflineModel.response
                def routed_response(self, messages):
                    system = str(messages[0].content)
                    if self.role == "main":
                        # 两份提示可能都提到 researcher；使用实际研究员首句判定。
                        from app.prompts.defaults import RESEARCHER_SYSTEM_PROMPT
                        if RESEARCHER_SYSTEM_PROMPT in system:
                            return original_response(self.model_copy(update={"role": "researcher"}), messages)
                    return original_response(self, messages)
                with patch.object(OfflineModel, "response", routed_response):
                    check_http()
                    asyncio.run(check_disconnect())
                asyncio.run(check_queue())
        finally:
            app.router.lifespan_context = original_lifespan
    print("\n全部验证通过；未调用真实模型，未修改项目财务库或聊天历史。")


if __name__ == "__main__":
    main()
