import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Boolean, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"run_{uuid.uuid4().hex[:12]}"
    )
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    config_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    tool_invocations: Mapped[list["ToolInvocation"]] = relationship(
        back_populates="run", lazy="selectin"
    )


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"ti_{uuid.uuid4().hex[:12]}"
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    run: Mapped["AgentRun"] = relationship(back_populates="tool_invocations")


class ToolRegistry(Base):
    __tablename__ = "tool_registry"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"tool_{uuid.uuid4().hex[:12]}"
    )
    tool_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    input_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"eval_{uuid.uuid4().hex[:12]}"
    )
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_config: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline_config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    summary_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    cases: Mapped[list["EvalCase"]] = relationship(
        back_populates="eval_run", lazy="selectin"
    )


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"ec_{uuid.uuid4().hex[:12]}"
    )
    eval_run_id: Mapped[str] = mapped_column(
        ForeignKey("eval_runs.id"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scores_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    eval_run: Mapped["EvalRun"] = relationship(back_populates="cases")
