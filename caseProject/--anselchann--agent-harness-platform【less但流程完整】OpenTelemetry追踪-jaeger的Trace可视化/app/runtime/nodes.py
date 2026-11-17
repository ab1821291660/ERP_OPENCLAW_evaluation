"""
LangGraph node implementations for the agent workflow.

Each node creates its own OTel span as a child of the root run span.
"""

import json
import logging
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult, ChatGeneration

from app.runtime.state import AgentRunState
from app.evals.observability.tracing import start_span

logger = logging.getLogger(__name__)

SYSTEM_PROMPTS = {
    "customer_support": (
        "你是客服助手。根据用户问题分析并回应。\n"
        "如果你的问题与订单、退货、物流无关，礼貌说明你是客服助手，建议联系对应部门。\n"
        "以 JSON 格式输出：{{\"answer\": \"...\", \"actions_taken\": [...]}}"
    ),
    "general": (
        "你是通用助手。你可以使用以下工具处理文件和系统操作：\n"
        "- fs_list_dir: 列出目录中的文件，参数 path（字符串，默认 \".\"）\n"
        "- fs_read_file: 读取文件内容，参数 path（字符串）\n"
        "- exec_command: 在安全沙箱中执行 shell 命令（仅限 ls, cat, grep, find, git, echo 等白名单命令），参数 command（字符串数组），cwd（工作目录）\n\n"
        "重要规则：\n"
        "1. 只有当用户明确要求操作文件、目录或执行命令时，才建议使用工具\n"
        "2. 对于常识、天气、新闻、计算等不需要文件操作的问题，直接回答即可，不需要调用工具\n"
        "3. 如果你不知道答案，诚实说明，不要编造\n"
        "以 JSON 格式输出：{{\"answer\": \"...\", \"reasoning\": \"...\", \"needs_tool\": false}}"
    ),
}


class _MockChatModel(BaseChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last = messages[-1].content if messages else ""
        text = json.dumps(
            {"answer": f"[mock] 已处理: {str(last)[:50]}...", "actions_taken": ["mock"]},
            ensure_ascii=False,
        )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _llm_type(self) -> str:
        return "mock-chat"


def _get_llm() -> BaseChatModel:
    from app.runtime_config import get_llm_api_key, get_llm_base_url, get_llm_model
    api_key = get_llm_api_key()
    if api_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=get_llm_model(),
            temperature=0,
            api_key=api_key,
            base_url=get_llm_base_url() or None,
        )
    return _MockChatModel()


def _get_parent_ctx(state: AgentRunState):
    return state.get("context", {}).get("span_ctx")


def prepare_context(state: AgentRunState) -> AgentRunState:
    with start_span("prepare_context", run_id=state["run_id"], parent_ctx=_get_parent_ctx(state)):
        user_input = state.get("user_input", {})
        task_type = state.get("task_type", "general")
        question = user_input.get("question", str(user_input))

        system_prompt = SYSTEM_PROMPTS.get(task_type, SYSTEM_PROMPTS["general"])
        state["messages"] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=question),
        ]
        state["context"] = {
            "task_type": task_type,
            "span_ctx": state.get("context", {}).get("span_ctx"),
        }
        state["status"] = "preparing"
    return state


async def plan(state: AgentRunState) -> AgentRunState:
    with start_span("plan", run_id=state["run_id"], parent_ctx=_get_parent_ctx(state)):
        llm = _get_llm()
        with start_span("llm_call", run_id=state["run_id"], parent_ctx=_get_parent_ctx(state),
                        attrs={"node": "plan"}):
            response = await llm.ainvoke(state["messages"])
        state["messages"].append(response)
        state["status"] = "planning"
        state["intermediate_results"].append({"step": "plan", "content": str(response.content)})
    return state


def select_tool(
    state: AgentRunState,
) -> Literal["invoke_tool", "synthesize_answer"]:
    with start_span("select_tool", run_id=state["run_id"], parent_ctx=_get_parent_ctx(state)):
        last_msg = state["messages"][-1]
        content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
        user_input = state.get("user_input", {})
        question = user_input.get("question", "")

        # Check if LLM explicitly says no tool needed
        try:
            raw = str(content).strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(raw)
            if parsed.get("needs_tool") is False:
                return "synthesize_answer"
        except (json.JSONDecodeError, AttributeError):
            pass

        all_text = f"{content} {question}"
        fs_triggers = ["fs_list_dir", "fs_read_file", "列出文件", "目录下有", "查看文件", "读文件", "读取文件"]
        cmd_triggers = ["exec_command", "执行命令", "运行命令", "沙箱"]
        order_triggers = ["订单", "发货", "退货"]
        hit = any(t in str(all_text) for t in fs_triggers + cmd_triggers + order_triggers)
    return "invoke_tool" if hit else "synthesize_answer"


async def invoke_tool(state: AgentRunState) -> AgentRunState:
    with start_span("invoke_tool", run_id=state["run_id"], parent_ctx=_get_parent_ctx(state)):
        from app.tool_gateway.client import invoke_tool as gateway_call

        user_input = state.get("user_input", {})
        question = user_input.get("question", "")
        plan_content = str(state["messages"][-1].content) if state["messages"] else ""

        tool_name, payload = _resolve_tool_call(question, plan_content)
        logger.info("Resolved tool=%s payload=%s", tool_name, payload)

        if tool_name == "_none":
            result = {"info": "此问题不需要工具调用，直接用知识回答"}
        else:
            try:
                record = await gateway_call(
                    run_id=state["run_id"],
                    tool_name=tool_name,
                    payload=payload,
                )
                result = record.response_payload or {"error": record.error}
            except Exception as exc:
                result = {"error": str(exc)}
                logger.exception("Gateway call failed for tool=%s", tool_name)

        state["tool_calls"].append({"tool": tool_name, "payload": payload, "result": result})
        state["intermediate_results"].append(
            {"step": "invoke_tool", "tool": tool_name, "result": result}
        )
        state["messages"].append(
            AIMessage(content=f"[工具调用结果] {json.dumps(result, ensure_ascii=False)}")
        )
        state["status"] = "invoking_tool"
    return state


def _resolve_tool_call(question: str, plan_content: str) -> tuple[str, dict]:
    combined = f"{question} {plan_content}"
    if any(kw in combined for kw in ["fs_list_dir", "列出文件", "目录下", "有哪些文件"]):
        return ("fs_list_dir", {"path": "."})
    if any(kw in combined for kw in ["fs_read_file", "读取文件", "查看文件", "读文件", "读一下"]):
        path = "README.md"
        for word in combined.split():
            if "." in word and not word.startswith("{"):
                path = word.strip(".,;:!?\"'")
                break
        return ("fs_read_file", {"path": path})
    if any(kw in combined for kw in ["exec_command", "执行命令", "运行命令", "沙箱"]):
        return ("exec_command", {"command": ["ls", "-la"], "cwd": "."})
    # No tool matched — return a sentinel that invoke_tool handles gracefully
    return ("_none", {})


async def synthesize_answer(state: AgentRunState) -> AgentRunState:
    with start_span("synthesize_answer", run_id=state["run_id"], parent_ctx=_get_parent_ctx(state)):
        llm = _get_llm()

        context_msg = ""
        if state.get("tool_calls"):
            context_msg = f"\n工具调用结果：{json.dumps(state['tool_calls'], ensure_ascii=False)}"

        state["messages"].append(
            HumanMessage(content=f"请综合以上信息和工具结果，给出最终回答。{context_msg}")
        )

        with start_span("llm_call", run_id=state["run_id"], parent_ctx=_get_parent_ctx(state),
                        attrs={"node": "synthesize_answer"}):
            response = await llm.ainvoke(state["messages"])
        state["messages"].append(response)
        state["status"] = "synthesizing"
        state["intermediate_results"].append(
            {"step": "synthesize", "content": str(response.content)}
        )

        raw = str(response.content).strip()
        if raw.startswith("```"):
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            final = json.loads(raw)
        except json.JSONDecodeError:
            final = {"answer": raw, "raw": True}

        state["final_output"] = final
    return state


def validate_output(state: AgentRunState) -> AgentRunState:
    with start_span("validate_output", run_id=state["run_id"], parent_ctx=_get_parent_ctx(state)):
        output = state.get("final_output")
        if output is None:
            state["error"] = {"type": "ValidationError", "message": "No final output produced"}
            state["status"] = "failed"
        else:
            state["status"] = "validating"
    return state


def finish(state: AgentRunState) -> AgentRunState:
    with start_span("finish", run_id=state["run_id"], parent_ctx=_get_parent_ctx(state)):
        if not state.get("error"):
            state["status"] = "completed"
        state["intermediate_results"].append({"step": "finish", "status": state["status"]})
    return state
