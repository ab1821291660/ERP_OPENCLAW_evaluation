"""
Tool Audit Logger - records every tool invocation for traceability.

Phase 3: persists to DB.
"""

import logging

from app.schemas.tools import ToolInvocationRecord
from app.db.session import _sessionmaker
from app.db.models import ToolInvocation

logger = logging.getLogger(__name__)


async def log_invocation(record: ToolInvocationRecord) -> None:
    """Log a tool invocation record to the database."""
    logger.info(
        "[audit] run=%s tool=%s status=%s latency=%sms",
        record.run_id, record.tool_name, record.status, record.latency_ms,
    )
    try:
        maker = _sessionmaker()
        async with maker() as session:
            ti = ToolInvocation(
                run_id=record.run_id,
                tool_name=record.tool_name,
                request_payload=record.request_payload,
                response_payload=record.response_payload,
                status=record.status,
                latency_ms=record.latency_ms,
                error_payload=record.error,
            )
            session.add(ti)
            await session.commit()
    except Exception:
        logger.exception("Failed to persist tool invocation audit record")
