import logging
import re

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.repositories.database import SessionLocal
from app.repositories.finqa import FinQARepository
from app.logging_config import log_event

logger = logging.getLogger(__name__)

# 完整报告 ID 的结构：
# 公司代码 / 四位年份 / PDF片段名称.pdf-编号
# 例如：AAPL/2014/page_38.pdf-2
_REPORT_ID_PATTERN = re.compile(
    r"[A-Za-z0-9._-]+/\d{4}/[A-Za-z0-9._-]+\.pdf-\d+"
)

def _search_financial_reports(
    repository: FinQARepository,
    query: str,
    limit: int = 3,
    config: RunnableConfig = None,
) -> list[dict]:
    """按查询文本搜索；程序指定精确 ID 时转为精确读取。"""

    forced_identifier, forced_split = _runtime_identifier(config)

    # 精确 ID 只能来自程序运行配置，搜索工具本身不接收 report_id。
    if forced_identifier:
        forced_report_id = forced_identifier.split("#q", maxsplit=1)[0]

        log_event(
            logger,
            "finqa_search_redirected_to_exact_report",
            effective_identifier=forced_report_id,
            query=query,
        )

        result = _get_financial_report(
            repository=repository,
            report_id=forced_report_id,
            query=query,
            config=config,
        )
        return [result] if result.get("found") else []

    return repository.search_reports(
        query=query,
        split=forced_split,
        limit=min(limit, 3),
    )

def _runtime_identifier(config: RunnableConfig | None) -> tuple[str, str | None]:
    """从 LangGraph configurable 中读取服务端强制注入的原始 FinQA 标识。"""
    configurable = (config or {}).get("configurable", {})
    return (
        str(configurable.get("finqa_identifier") or "").strip(),
        configurable.get("finqa_split"),
    )

def _get_financial_report(
    repository: FinQARepository,
    report_id: str,
    query: str = "",
    metrics: list[str] | None = None,
    config: RunnableConfig = None,
) -> dict:
    """精确读取一份 FinQA 报告；多个指标必须一次性放入 metrics。"""
    # config 中的原始 ID 优先级最高，避免 researcher 将 AAPL/2014 等事实改写后查错报告。
    '''
    调用 _runtime_identifier()，从运行配置的 configurable 中读取：
        - finqa_identifier：服务端保存的 FinQA 标识；
        - finqa_split：服务端保存的数据分区。
    '''
    forced_identifier, forced_split = _runtime_identifier(config)

    # 程序提供的题目标识可以转换成其所属报告标识。
    forced_report_id = forced_identifier.split("#q", maxsplit=1)[0]

    requested_report_id = report_id.strip()

    # 程序明确指定的 ID 优先，否则使用模型传入的完整 ID。
    effective_report_id = forced_report_id or requested_report_id
    effective_split = forced_split

    identifier_forced = bool(
        forced_report_id
        and forced_report_id != requested_report_id
    )

    # fullmatch 要求整个字符串符合格式，不能只匹配其中一部分。
    if not _REPORT_ID_PATTERN.fullmatch(effective_report_id):
        return {
            "found": False,
            "error": "invalid_report_id",
            "identifier_type": "report_id",
            "report_id": effective_report_id,
            "requested_report_id": requested_report_id,
            "identifier_forced": identifier_forced,
            "recommended_tool": "find_finqa_reports",
            "hint": (
                "report_id 必须是完整报告标识，例如 "
                "AAPL/2014/page_38.pdf-2。"
                "公司名、公司年份组合以及带 #qN 的题目标识不能用于此参数。"
                "没有完整 ID 时，先使用 find_finqa_reports 定位候选，"
                "再使用其返回的完整 ID；不要猜测页码。"
            ),
        }
    # 合并用户要查的指标
    # 将用户所有指标组合为一次查询，减少工具调用并让同一张表的单位/年份保持一致。
    requested_metrics = [item.strip() for item in (metrics or []) if item.strip()]
    combined_query = " ".join([query.strip(), *requested_metrics]).strip()
    if not combined_query:
        return {
            "found": False,
            "error": "missing_query",
            "identifier_type": "report_id",
            "report_id": report_id,
            "hint": "必须提供 query 或 metrics，并把全部指标放在同一次调用中。",
        }
    # 从数据库读取报告
    report = repository.get_report(
        effective_report_id,
        split=effective_split,
    )
    if report is None:
        return {
            "found": False,
            "error": "report_not_found",
            "identifier_type": "report_id",
            "report_id": effective_report_id,
            "split": effective_split,
            "requested_report_id": report_id,
            "identifier_forced": identifier_forced,
            "recommended_tool": "find_finqa_reports",
            "hint": (
                "该完整 report_id 在当前查询范围内不存在。"
                "这不代表整个 FinQA 缺少所需财务指标。"
                "如果尚未定位报告，请先按公司和年份查询候选，"
                "使用工具返回的完整 ID；禁止猜测相邻页码，"
                "也不要重复提交相同的无效 ID。"
            ),
        }
    # 报告存在不等于请求指标已全部找到。
    evidence = repository.compact_report(
        report,
        query=combined_query,
        queries=requested_metrics,
        max_table_rows=min(max(6, len(requested_metrics)), 20),
    )
    return {
        "found": True,
        "identifier_type": "report_id",
        "requested_report_id": requested_report_id,
        "effective_identifier": effective_report_id,
        "identifier_forced": identifier_forced,
        **evidence,
    }

@tool(parse_docstring=True)
def get_financial_report(
    report_id: str,
    query: str = "",
    metrics: list[str] | None = None,
    config: RunnableConfig = None,
) -> dict:
    """读取指定 FinQA 财务报告中的原始证据。

    Args:
        report_id: 完整 FinQA 报告标识，例如 ``AAPL/2014/page_38.pdf-2``。
            必须使用用户提供的完整 ID，或者报告定位工具返回的完整 ID。
            不接受 ``AAPL/2014`` 等公司年份组合，也不接受包含 ``#qN``
            的题目标识。禁止自行猜测页码或编号。
        query: 对报告内容的自然语言检索词。通常填写用户问题或指标名称，
            用于压缩正文片段和表格行。
        metrics: 需要同时提取的财务指标列表，例如
            ``["long-term debt", "cash generated by operating activities"]``。
            多个指标应在一次调用中传入，避免重复读取同一份报告。
        config: LangGraph 运行时配置。由服务端注入的
            ``finqa_identifier`` 和 ``finqa_split`` 优先于模型传入的同名值，
            该参数不是用户业务输入。

    Returns:
        一个当前报告的证据字典。found=True 仅表示报告记录存在。
        matched_metrics 和 unmatched_metrics 表示当前报告的表格指标行匹配情况。
        context_snippets 保留期间和单位说明，table_rows 保留表头及相关原始行。
        是否足以回答问题，还需要结合年份、数值和单位判断。
        失败时包含 found=False、error 和 hint。

    Notes:
        工具只读取 SQLite 中已经导入的 FinQA 数据，不会访问文件系统或模型。
        返回的 ``score`` 仅表示候选证据的关键词相关度，不代表财务答案正确率。
    """
    with SessionLocal() as db:
        return _get_financial_report(
            FinQARepository(db),
            report_id,
            query,
            metrics,
            config,
        )


@tool(parse_docstring=True)
def search_financial_reports(
    query: str,
    limit: int = 3,
    config: RunnableConfig = None,
) -> list[dict]:
    """通过自然语言查询文本搜索 FinQA 财务报告候选。

    Args:
        query: 自然语言查询文本，例如 ``Apple 2014 long-term debt``。
            已知公司和年份时，优先使用 find_finqa_reports 定位报告。
        limit: 最多返回的候选数量，工具层最多返回 3 条。
        config: LangGraph 自动注入的运行配置，不是模型业务输入。
            程序可以通过 configurable.finqa_identifier 指定精确标识，
            通过 configurable.finqa_split 明确限定分区。
            未配置 finqa_split 时查询全部分区。

    Returns:
        候选报告列表，每项包含完整 report_id、实际 split 和有限证据。
        当前查询未命中时返回空列表。

    Notes:
        本工具不接受 report_id。
        已取得完整报告 ID 后，应使用 get_financial_report 精确读取。
        不要将 AAPL/2014 等公司年份组合当作完整报告 ID。
    """
    with SessionLocal() as db:
        return _search_financial_reports(
            repository=FinQARepository(db),
            query=query,
            limit=limit,
            config=config,
        )


@tool(parse_docstring=True)
def find_finqa_reports(
    company: str,
    year: int | None = None,
    metrics: list[str] | None = None,
    query: str = "",
    limit: int = 5,
    config: RunnableConfig = None,
) -> dict:
    """按公司、年份和财务指标定位 FinQA 报告候选。

    Args:
        company: 公司名称、常用别名或股票代码，例如 ``Apple``、``苹果`` 或
            ``AAPL``。只有在 company_aliases 中唯一匹配时才会继续查询。
        year: 报告年份，例如 ``2014``。不传时不会猜测年份，而是返回
            ``year_required`` 和该公司的可用年份。
        metrics: 需要在报告中查找的财务指标列表。建议将用户问题中的全部
            指标一次性传入，例如 ``["property plant and equipment net",
            "long-term debt"]``。
        query: 补充检索文本，用于提高正文和表格证据排序；可以传入完整用户
            问题，也可以留空。
        limit: 最多返回的候选报告数量，默认 5。候选结果仍需交给
            ``get_financial_report`` 做精确证据读取。
        config: LangGraph 运行时配置。服务端注入的 FinQA 标识和 split 优先，
            该参数不是模型业务输入。

    Returns:
        一个定位结果字典。成功时包含 ``found=True``、候选 ``results``、
        ``ticker``、``year`` 和可用证据；公司未知、公司重名或缺少年份时，
        返回 ``company_unknown``、``company_ambiguous`` 或 ``year_required``。

    Notes:
        本工具只负责从 SQLite 的 company_aliases 和 financial_reports 中定位
        候选，不负责计算财务公式，也不表示候选报告已经完成答案验证。
    """
    # 先从运行时配置中获取强制标识
    forced, forced_split = _runtime_identifier(config)
    with SessionLocal() as db:
        repository = FinQARepository(db)
        if forced:
            result = _get_financial_report(
                repository,
                forced.split("#q", 1)[0],
                query=query or " ".join(metrics or []) or company,
                metrics=metrics,
                config=config,
            )
            return {"found": result.get("found", False), "results": [result]}
        return repository.find_reports(
            company,
            year,
            metrics,
            query,
            forced_split,
            limit,
        )
