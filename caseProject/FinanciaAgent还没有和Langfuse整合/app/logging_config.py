"""结构化 JSONL 日志、请求 ID 上下文与敏感字段脱敏。"""

import json
import logging
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import get_settings


# ContextVar 自动随 async 调用链传播，使同一 HTTP 请求的日志拥有共同 request_id。##===================================##===================================##===================================
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_configured = False
_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "deepseek_api_key",
    "langfuse_secret_key",
    "password",
    "secret_key",
    "set-cookie",
    "zhipu_api_key",
}
def _sanitize(value: Any, *, max_string: int = 2_000) -> Any:
    """递归移除密钥类字段并截断超长日志值，避免日志成为敏感数据副本。"""
    if isinstance(value, dict):
        return {
            str(key): "***" if str(key).lower() in _SENSITIVE_KEYS else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value[:100]]
    if isinstance(value, str):
        return value if len(value) <= max_string else f"{value[:max_string]}...[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _sanitize(str(value), max_string=max_string)




class JsonLogFormatter(logging.Formatter):
    """将标准 logging.Record 编码为单行 JSON，适合文件检索和日志平台采集。"""
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        event_data = getattr(record, "event_data", None)
        if event_data:
            payload.update(_sanitize(event_data))##===================================
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
def _file_handler(path: Path, *, level: int) -> RotatingFileHandler:
    """创建按大小轮转的 UTF-8 文件处理器。"""
    settings = get_settings()
    handler = RotatingFileHandler(
        path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(JsonLogFormatter())##===================================
    return handler
def configure_logging() -> None:
    """进程启动时仅配置一次 agent.jsonl 与 error.log 两个文件输出。"""
    global _configured
    if _configured:
        return
    settings = get_settings()
    settings.logs_path.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(_file_handler(settings.logs_path / "agent.jsonl", level=level))##===================================
    root.addHandler(_file_handler(settings.logs_path / "error.log", level=logging.ERROR))##===================================
    _configured = True




def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """写入统一事件名与已脱敏字段，供服务、工具与追踪模块调用。"""
    logger.info(event, extra={"event_data": {"event": event, **_sanitize(fields)}})##===================================





def new_request_id() -> str:
    """生成 HTTP/Agent 请求关联用 UUID。"""
    return str(uuid4())
def get_request_id() -> str | None:
    """读取当前协程链绑定的请求 ID。"""
    return _request_id.get()
def set_request_id(value: str) -> Token[str | None]:
    """绑定请求 ID 并返回 token，以便 middleware finally 精确恢复旧上下文。"""
    return _request_id.set(value)
def reset_request_id(token: Token[str | None]) -> None:
    """恢复 ContextVar，防止长生命周期 worker 复用上一个请求 ID。"""
    _request_id.reset(token)

