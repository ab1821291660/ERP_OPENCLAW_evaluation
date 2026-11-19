"""在控制台输入一个问题，使用 DeepAgents v3 Event Streaming 查看真实 Agent 输出。

在 PyCharm 中作为普通 Python 脚本运行，不需要 pytest、FastAPI 或 Vue。
提交问题会调用已配置的 DeepSeek/智谱模型，并写入项目的会话数据库。
"""
import asyncio
import os
from pathlib import Path
import sys
from uuid import uuid4
# 相对 SQLite URL 以项目根目录为基准，避免 PyCharm 工作目录不同导致读错库。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent_factory import (  # noqa: E402
    close_agent_runtime,
    get_agent,
    initialize_agent_runtime,
)
from app.config import get_settings  # noqa: E402



async def main() -> None:
    """读取一个用户问题，运行 Agent，并按到达顺序打印文本和工具事件。"""
    question = input("请输入财务问题：").strip()
    if not question:
        print("问题不能为空。")
        return


    await initialize_agent_runtime()##===================================
    try:
        config = {
            "configurable": {"thread_id": str(uuid4())},
        }
        # v3 属于 Event Streaming API：不能把 astream(version="v2") 直接改成 v3。
        stream = await get_agent().astream_events(##===================================
            {"messages": [{"role": "user", "content": question}]},
            config=config,
            version="v3",##===================================##===================================
        )


        current_source = None
        async for event in stream:
            method = event.get("method")
            params = event.get("params") or {}
            namespace = params.get("namespace") or []
            source = "主 Agent" if not namespace else "子 Agent"##===================================


            if method == "messages":  # AI Message里面包含有文本的，打印出来
                data = params.get("data") or []
                payload = data[0] if data else None
                if not isinstance(payload, dict) or payload.get("event") != "content-block-delta":
                    continue
                delta = payload.get("delta") or {}
                if delta.get("type") != "text-delta":
                    continue
                text = delta.get("text") or ""
                if text:
                    if source != current_source:
                        print(f"\n[{source}] ", end="", flush=True)
                        current_source = source
                    print(text, end="", flush=True)


            elif method == "tools":  # ToolMessage
                data = params.get("data") or {}
                if not isinstance(data, dict):
                    continue
                kind = data.get("event")
                if kind == "tool-started":##===================================
                    print(
                        f"\n[{source}] 调用工具：{data.get('tool_name')} "##===================================
                        f"参数：{data.get('input')}",##===================================
                        flush=True,
                    )
                    current_source = None
                elif kind == "tool-finished":##===================================
                    print(f"\n[{source}] 工具结果：{data.get('output')}", flush=True)
                    current_source = None
                elif kind == "tool-error":##===================================
                    print(f"\n[{source}] 工具失败：{data.get('message')}", flush=True)
                    current_source = None
        print("\n\n[Agent 执行结束]", flush=True)
    finally:
        await close_agent_runtime()##===================================
if __name__ == "__main__":
    asyncio.run(main())


