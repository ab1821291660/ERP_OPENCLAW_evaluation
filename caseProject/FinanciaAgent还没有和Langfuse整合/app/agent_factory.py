import asyncio
import logging
from contextlib import AsyncExitStack

from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from deepagents import register_harness_profile, HarnessProfile, GeneralPurposeSubagentProfile, create_deep_agent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite import AsyncSqliteStore

from app.config import get_settings
from app.logging_config import log_event
from app.prompts.defaults import RESEARCHER_SYSTEM_PROMPT, REVIEWER_SYSTEM_PROMPT, MAIN_SYSTEM_PROMPT
from app.tools.calculator import safe_calculate
from app.tools.retrieval import find_finqa_reports, get_financial_report, search_financial_reports

logger = logging.getLogger(__name__)

_runtime_stack = None
_checkpointer = None
_store = None
_agent = None
_runtime_lock = asyncio.Lock()

def _create_deepseek_model(model_name: str) -> BaseChatModel:
    """复用连接配置；每次调用返回独立模型实例，不修改原有公开函数参数。"""
    settings = get_settings()

    if not settings.deepseek_api_key:
        logging.error("DEEPSEEK_API_KEY is required to invoke the agent")
        raise RuntimeError("DEEPSEEK_API_KEY is required to invoke the agent")
    if not settings.deepseek_base_url:
        logging.error("DEEPSEEK_BASE_URL is required to invoke the agent")
        raise RuntimeError("DEEPSEEK_BASE_URL is required to invoke the agent")

    chat_model = init_chat_model(
        model=model_name,
        model_provider='openai',
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=1.0,
        timeout=120,
        max_retries=2,
        stream_usage=True, # 是否在流式输出中包含 usage 元数据, token的统计信息
    )
    log_event(
        logger,
        "model_configured",
        provider="deepseek",
        model=model_name,
        base_url=settings.deepseek_base_url,
    )
    return chat_model
def build_model() -> BaseChatModel:
    """创建主模型；未配置模型名时使用 deepseek-flash。"""
    return _create_deepseek_model((get_settings().main_model or "").strip() or "deepseek-flash")




def build_reviewer_model() -> BaseChatModel:
    """优先用智谱初始化独立复核模型，未配置时回退到 DeepSeek。"""
    settings = get_settings()
    reviewer_model = settings.reviewer_model.strip()
    if not reviewer_model:
        # 即使模型名与主 Agent 相同，也单独创建一个 reviewer 模型实例。
        return _create_deepseek_model("deepseek-flash")


    reviewer_provider = settings.reviewer_model_provider.strip().lower()
    if reviewer_provider not in {"", "zhipu"}:
        raise RuntimeError("REVIEWER_MODEL must use the Zhipu provider in this agent factory")
    if not settings.zhipu_api_key:
        raise RuntimeError("ZHIPU_API_KEY is required when REVIEWER_MODEL is configured")
    if not settings.zhipu_base_url:
        raise RuntimeError("ZHIPU_BASE_URL is required when REVIEWER_MODEL is configured")

    reviewer_chat_model = init_chat_model(
        model=reviewer_model,
        model_provider="openai",
        api_key=settings.zhipu_api_key,
        base_url=settings.zhipu_base_url,
        temperature=0,
        timeout=120,
        max_retries=2,
        stream_usage=False,
    )
    log_event(
        logger,
        "model_configured",
        provider="zhipu",
        model=reviewer_model,
        base_url=settings.zhipu_base_url,
    )
    return reviewer_chat_model





def ________创建create_deep_agent():pass
_profile_registered = False  # 默认没有注册Harness Profile

def register_basic_harness_profile() -> None:
    """关闭不使用的 DeepAgents 内置工具和默认通用子 Agent。

    ``tools=[...]`` 指定业务工具，
    但 DeepAgents 还会额外注入文件、待办和``task`` 工具。
    本示例保留 ``task`` 用于委派两个业务子 Agent，排除文件和待办工具。##===================================##===================================
    此 Profile 只过滤模型可见工具，并非底层文件权限机制。
    """

    global _profile_registered
    if _profile_registered:
        return

    register_harness_profile(
        'openai',
        HarnessProfile(
            excluded_tools=frozenset(
                {
                    "ls",
                    "glob",
                    "grep",
                    "read_file",
                    "write_file",
                    "edit_file",
                    "execute",##===================================##===================================
                    "write_todos",  # 任务计划的工具##===================================##===================================
                }
            ),
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        )
    )
    _profile_registered=True


def build_agent(*, checkpointer: AsyncSqliteSaver, store: AsyncSqliteStore):
    """组装主 Agent 与两个只使用显式业务工具的 SubAgent。"""
    settings = get_settings()
    register_basic_harness_profile()##===================================
    main_model = build_model()

    # researcher 直接查询已导入的 FinQA SQLite；不能调用计算工具。
    researcher = {
        "name": "researcher",
        "description": "查询 FinQA 财务报告数据，返回原始数值、单位及出处。",
        "system_prompt": RESEARCHER_SYSTEM_PROMPT,
        "tools": [
            find_finqa_reports,
            get_financial_report,
            search_financial_reports,
        ],
        "middleware": [
            ModelCallLimitMiddleware(
                run_limit=settings.researcher_max_model_calls,
                exit_behavior="end",
            ),
            ToolCallLimitMiddleware(
                tool_name="find_finqa_reports",
                run_limit=settings.researcher_max_search_calls,
                exit_behavior="error",
            ),
            ToolCallLimitMiddleware(
                tool_name="get_financial_report",
                run_limit=settings.researcher_max_report_calls,
                exit_behavior="continue",
            ),
            ToolCallLimitMiddleware(
                tool_name="search_financial_reports",
                run_limit=settings.researcher_max_search_calls,
                exit_behavior="continue",
            ),
        ],
    }

    # reviewer 只能使用安全计算工具，根据主 Agent 交接的数据进行独立复核。
    reviewer = {"name": "reviewer", "description": "复核财务公式、计算结果、年份、单位及证据引用。",
                "system_prompt": REVIEWER_SYSTEM_PROMPT, "tools": [safe_calculate], "middleware": [
            ModelCallLimitMiddleware(
                run_limit=settings.reviewer_max_model_calls,
                exit_behavior="end",
            ),
            ToolCallLimitMiddleware(
                tool_name="safe_calculate",
                run_limit=settings.reviewer_max_calculations,
                exit_behavior="error",
            ),
        ], "model": build_reviewer_model()}


    # if settings.reviewer_model:
    #     reviewer_provider = settings.reviewer_model_provider.strip().lower()
    #     if reviewer_provider not in {"", "deepseek"}:
    #         raise RuntimeError("This agent factory supports only DeepSeek reviewer models")
    #     reviewer["model"] = build_model(model=settings.reviewer_model)

    return create_deep_agent(
        model=main_model,
        tools=[safe_calculate],
        subagents=[researcher, reviewer],
        middleware=[
            ModelCallLimitMiddleware(run_limit=settings.max_model_calls, exit_behavior='end'),
            ToolCallLimitMiddleware(run_limit=settings.max_tool_calls, exit_behavior='error'),
            ToolCallLimitMiddleware(
                tool_name='safe_calculate',
                run_limit=settings.main_max_calculations,
                exit_behavior='error'
            )
        ],
        checkpointer=checkpointer,
        store=store,
        system_prompt=MAIN_SYSTEM_PROMPT
    )


async def initialize_agent_runtime() -> None:
    """初始化相关的资源，并创建主Agent"""
    settings = get_settings()
    global _runtime_stack, _checkpointer, _store, _agent
    if _agent is not None:##===================================
        return


    async with _runtime_lock:
        # 并发初始化的第二次检查，避免重复创建 SQLite 连接与 Agent。
        if _agent is not None:
            return
        # 1、初始数据库所需的目录
        settings.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        settings.store_path.parent.mkdir(parents=True, exist_ok=True)
        stack = AsyncExitStack()
        try:
            checkpointer = await stack.enter_async_context(
                AsyncSqliteSaver.from_conn_string(str(settings.checkpoint_path))
            )
            store = await stack.enter_async_context(
                AsyncSqliteStore.from_conn_string(str(settings.store_path))
            )
            await checkpointer.setup()
            await store.setup()
            agent = build_agent(checkpointer=checkpointer, store=store)##===================================
        except Exception:
            await stack.aclose()  # 释放资源
            raise
        _runtime_stack = stack##===================================
        _checkpointer = checkpointer
        _store = store
        _agent = agent
        log_event(logger, "agent_runtime_initialized", graph_type=type(agent).__name__)


def get_agent():
    """取得已初始化的 Agent 图，供 HTTP 和 SSE 服务层调用。"""
    if _agent is None:
        raise RuntimeError("Agent runtime is not initialized")
    return _agent


def get_store() -> AsyncSqliteStore:
    """取得用于会话目录和标题的 Store。"""
    if _store is None:
        raise RuntimeError("Agent store is not initialized")
    return _store


def get_checkpointer() -> AsyncSqliteSaver:
    """取得保存 LangGraph 状态和完整消息历史的 Checkpointer。"""
    if _checkpointer is None:
        raise RuntimeError("Agent checkpointer is not initialized")
    return _checkpointer


async def close_agent_runtime() -> None:
    """释放异步 SQLite 资源，清空本模块的运行时单例。"""
    global _runtime_stack, _checkpointer, _store, _agent
    if _runtime_stack is not None:##===================================
        await _runtime_stack.aclose()##===================================
    _runtime_stack = None##===================================
    _checkpointer = None
    _store = None
    _agent = None
    log_event(logger, "agent_runtime_closed")
