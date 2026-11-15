from datetime import datetime, timezone

from sqlalchemy import String, UniqueConstraint, JSON, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.database import Base
def utc_now() -> datetime:
    """为 SQLite 时间字段提供带 UTC 时区的默认时间。"""
    return datetime.now(timezone.utc)




class CompanyAlias(Base):
    """公司名称到 FinQA 原始公司代码的映射；复合主键允许同名公司歧义。"""

    __tablename__ = "company_aliases"
    alias: Mapped[str] = mapped_column(String(255), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(64))



class FinancialReport(Base):
    """一份按 split 隔离的 FinQA 报告正文、表格和其题目关系。"""
    __tablename__ = "financial_reports"
    __table_args__ = (
        UniqueConstraint("split", "source_id", name="uq_financial_report_split_source"),
    )

    id: Mapped[str] = mapped_column(String(320), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    split: Mapped[str] = mapped_column(String(32), index=True)
    pre_text: Mapped[list] = mapped_column(JSON)
    post_text: Mapped[list] = mapped_column(JSON)
    table: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TraceMapping(Base):
    """一次 Agent 请求与会话消息、Langfuse Trace/根 Observation 的本地关联。"""
    __tablename__ = "trace_mappings"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), index=True)
    user_id: Mapped[str] = mapped_column(String(200), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    root_observation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    human_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    answer_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    run_status: Mapped[str] = mapped_column(String(32), default="legacy", server_default="legacy")
    trace_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    question_id: Mapped[str | None] = mapped_column(String(320), nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FeedbackRecord(Base):
    """用户点赞/点踩及其同步到 Langfuse Scores API 的结果。"""
    __tablename__ = "feedback_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(200), index=True)
    user_id: Mapped[str] = mapped_column(String(200), default="demo-user", index=True)
    value: Mapped[int]
    helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    issue_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    sync_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

