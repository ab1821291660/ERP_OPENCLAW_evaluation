"""FastAPI 入口：初始化现有 DeepAgents 和 SQLite 会话组件，不创建业务表。"""

from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.agent_factory import close_agent_runtime, initialize_agent_runtime
from app.config import get_settings
from app.logging_config import configure_logging, log_event, reset_request_id, set_request_id
from app.repositories.database import SessionLocal
from app.repositories.finqa import FinQARepository
from app.routers.agent import router as agent_router
from app.routers.sessions import router as sessions_router
from app.session_store import stop_all_runs


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """yield 前初始化，yield 后释放；不迁移或重建已有财务数据。"""
    configure_logging()
    await initialize_agent_runtime()
    log_event(logger, "application_ready")
    try:
        yield
    finally:
        stop_all_runs()
        await close_agent_runtime()
        log_event(logger, "application_stopped")


app = FastAPI(title="财务研究 Agent", version=get_settings().app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_methods=["*"], allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.include_router(agent_router)
app.include_router(sessions_router)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """每个 HTTP 请求生成本地编号，后续 SSE 日志沿用该编号。"""
    request_id = str(uuid4())
    token = set_request_id(request_id)
    started = perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log_event(
            logger, "http_completed", method=request.method, path=request.url.path,
            status=response.status_code, duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        return response
    finally:
        reset_request_id(token)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    with SessionLocal() as db:
        counts = FinQARepository(db).counts()
    return {"status": "ready" if counts["reports"] else "not_ready", "data": counts}
