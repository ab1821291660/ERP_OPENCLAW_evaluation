"""
Metrics collection for the platform.

Tracks: run_success_rate, run_latency_ms, tool_error_rate,
        avg_tool_calls_per_run, token_usage, estimated_cost_usd, eval_pass_rate
"""

from dataclasses import dataclass, field


@dataclass
class RunMetrics:
    run_id: str
    latency_ms: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    token_usage_input: int = 0
    token_usage_output: int = 0
    estimated_cost_usd: float = 0.0
    success: bool = False
    error: dict | None = None


class MetricsCollector:
    """In-memory metrics collector with summary aggregation."""

    def __init__(self):
        self._metrics: list[RunMetrics] = []

    def record(self, metrics: RunMetrics) -> None:
        self._metrics.append(metrics)

    def summary(self) -> dict:
        if not self._metrics:
            return {"total_runs": 0}

        total = len(self._metrics)
        successes = sum(1 for m in self._metrics if m.success)
        failures = total - successes
        latencies = [m.latency_ms for m in self._metrics if m.latency_ms > 0]

        return {
            "total_runs": total,
            "success_count": successes,
            "failure_count": failures,
            "success_rate": round(successes / total, 4) if total > 0 else 0,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "avg_tool_calls": round(sum(m.tool_calls for m in self._metrics) / total, 1),
            "tool_error_count": sum(m.tool_errors for m in self._metrics),
            "total_cost_usd": round(sum(m.estimated_cost_usd for m in self._metrics), 6),
        }


collector = MetricsCollector()
