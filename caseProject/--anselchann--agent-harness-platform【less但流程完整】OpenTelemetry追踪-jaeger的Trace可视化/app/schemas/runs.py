from datetime import datetime

from pydantic import BaseModel, Field


class RunConfig(BaseModel):
    model: str = "gpt-4.1"
    max_tool_calls: int = 4
    timeout_seconds: int = 60


class RunInput(BaseModel):
    agent_name: str = Field(..., examples=["support-agent"])
    task_type: str = Field(..., examples=["customer_support"])
    input: dict = Field(..., examples=[{"question": "请帮我查一下订单 12345 的状态"}])
    config: RunConfig = Field(default_factory=RunConfig)
    metadata: dict = Field(default_factory=dict)


class RunCreated(BaseModel):
    run_id: str
    status: str = "queued"


class RunMetrics(BaseModel):
    latency_ms: int | None = None
    tool_calls: int = 0
    estimated_cost_usd: float | None = None


class RunResponse(BaseModel):
    run_id: str
    status: str
    input: dict | None = None
    output: dict | None = None
    metrics: RunMetrics | None = None
    error: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RunTraceResponse(BaseModel):
    run_id: str
    trace_id: str
    trace_url: str | None = None
