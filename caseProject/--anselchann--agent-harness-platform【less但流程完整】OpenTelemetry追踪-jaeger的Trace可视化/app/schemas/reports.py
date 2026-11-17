from datetime import datetime

from pydantic import BaseModel


class ReportSummary(BaseModel):
    total_cases: int
    pass_count: int
    fail_count: int
    pass_rate: float
    avg_latency_ms: float | None = None
    avg_cost_usd: float | None = None
    failed_cases: list[dict] = []


class ReportResponse(BaseModel):
    report_id: str
    eval_id: str
    summary: ReportSummary
    created_at: datetime | None = None
