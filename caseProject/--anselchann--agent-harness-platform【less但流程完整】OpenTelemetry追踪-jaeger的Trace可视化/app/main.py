from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.config import settings
from app.db.models import Base
from app.db.session import _engine
from app.api.routers import runs, tools, evals, reports, config
from app.tool_gateway.registry import registry
from app.schemas.tools import ToolSpec


def _register_builtin_tools() -> None:
    """Register platform built-in tool specs on startup."""
    builtins = [
        ToolSpec(
            tool_name="fs_list_dir",
            source="builtin://filesystem/list_dir",
            description="列出指定目录中的文件和子目录",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "目录路径，默认 '.'"}},
            },
            tags=["filesystem", "safe"],
        ),
        ToolSpec(
            tool_name="fs_read_file",
            source="builtin://filesystem/read_file",
            description="读取文件内容（文本文件）",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "文件路径"}, "max_chars": {"type": "integer", "description": "最大读取字符数"}},
            },
            tags=["filesystem", "safe"],
        ),
        ToolSpec(
            tool_name="exec_command",
            source="builtin://sandbox/exec",
            description="在受控沙箱中执行 shell 命令（仅限白名单命令：ls, cat, grep, find, git 等）",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "array", "items": {"type": "string"}, "description": "命令和参数，如 ['ls', '-la']"},
                    "cwd": {"type": "string", "description": "工作目录"},
                },
                "required": ["command"],
            },
            timeout_seconds=15,
            tags=["sandbox", "execution", "requires_approval"],
        ),
    ]
    for spec in builtins:
        registry.register(spec)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    engine = _engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Register built-in tools
    _register_builtin_tools()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
async def root():
    return HTMLResponse(INDEX_HTML)


INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Harness Platform</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0d1117;color:#c9d1d9;line-height:1.6}
.header{background:#161b22;border-bottom:1px solid #30363d;padding:24px 32px}
.header h1{color:#58a6ff;font-size:28px;margin-bottom:4px}
.header p{color:#8b949e}
.hero{padding:60px 32px;text-align:center}
.hero h2{font-size:36px;color:#f0f6fc;margin-bottom:16px}
.hero p{font-size:18px;color:#8b949e;max-width:700px;margin:0 auto 32px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;padding:0 32px 60px;max-width:1200px;margin:0 auto}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:24px}
.card h3{color:#58a6ff;margin-bottom:8px}
.card .method{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold;margin-right:8px}
.get{background:#1f6feb33;color:#58a6ff;border:1px solid #1f6feb55}
.post{background:#23863633;color:#3fb950;border:1px solid #23863655}
.card .path{font-family:monospace;color:#f0f6fc;margin-bottom:8px}
.card .desc{color:#8b949e;font-size:14px}
.btn{display:inline-block;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold;margin:8px}
.btn-primary{background:#238636;color:#fff}
.btn-secondary{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn:hover{opacity:.9}
.footer{padding:32px;text-align:center;border-top:1px solid #30363d;color:#8b949e}
</style>
</head>
<body>

<div class="header">
  <h1>Agent Harness Platform</h1>
  <p>面向 AI Agent 的工程化平台 — 可观测、可评测、可回归、可上线</p>
</div>

<div class="hero">
  <h2>把 Agent 从"能跑"推进到"生产就绪"</h2>
  <p>一个平台解决 Agent 开发的五个核心问题：运行调度、工具安全、链路追踪、质量评测、回归门禁</p>
  <a href="/docs" class="btn btn-primary">API 文档</a>
  <a href="/demo" class="btn btn-secondary">快速体验</a>
</div>

<div class="grid">
  <div class="card">
    <h3>创建 Agent 任务</h3>
    <p><span class="method post">POST</span><span class="path">/api/v1/runs</span></p>
    <p class="desc">提交一个 Agent 任务，AI 自动分析问题、调用工具、生成回答。支持客服、代码分析、通用问答等类型。</p>
  </div>
  <div class="card">
    <h3>查询执行结果</h3>
    <p><span class="method get">GET</span><span class="path">/api/v1/runs/{run_id}</span></p>
    <p class="desc">查询任务状态（运行中/已完成/失败）、输出内容、工具调用次数等指标。</p>
  </div>
  <div class="card">
    <h3>查看全链路 Trace</h3>
    <p><span class="method get">GET</span><span class="path">/api/v1/runs/{run_id}/trace/spans</span></p>
    <p class="desc">OpenTelemetry 采集的完整调用链：plan → tool invoke → synthesize → validate，每个步骤的耗时。</p>
  </div>
  <div class="card">
    <h3>工具网关</h3>
    <p><span class="method get">GET</span><span class="path">/api/v1/tools</span></p>
    <p class="desc">查看已注册的工具列表（文件系统、沙箱命令等），可手动调用测试。</p>
  </div>
  <div class="card">
    <h3>自动评测</h3>
    <p><span class="method post">POST</span><span class="path">/api/v1/evals</span></p>
    <p class="desc">对数据集批量运行 Agent，用 exact_match + rubric_judge 自动评分，生成评测报告。</p>
  </div>
  <div class="card">
    <h3>平台指标</h3>
    <p><span class="method get">GET</span><span class="path">/api/v1/metrics</span></p>
    <p class="desc">成功率、平均延迟、工具调用次数、错误率等平台级聚合指标。</p>
  </div>
</div>

<div class="footer">
  Agent Harness Platform v0.1.0 &nbsp;|&nbsp;
  <a href="/docs" style="color:#58a6ff">Swagger API</a> &nbsp;|&nbsp;
  <a href="/health" style="color:#58a6ff">Health Check</a>
</div>

</body>
</html>"""


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


@app.get(f"{settings.api_prefix}/metrics")
async def platform_metrics():
    """Get aggregated platform metrics."""
    from app.evals.observability.metrics import collector
    return collector.summary()


# Mount routers
app.include_router(runs.router, prefix=settings.api_prefix)
app.include_router(tools.router, prefix=settings.api_prefix)
app.include_router(evals.router, prefix=settings.api_prefix)
app.include_router(reports.router, prefix=settings.api_prefix)
app.include_router(config.router, prefix=settings.api_prefix)
