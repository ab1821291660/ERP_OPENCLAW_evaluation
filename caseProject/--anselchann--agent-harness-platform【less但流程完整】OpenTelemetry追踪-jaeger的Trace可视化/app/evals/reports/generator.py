"""
Report Generator - produces Markdown and JSON reports from eval results.
"""

import json
from datetime import datetime, timezone


def generate_markdown(report: dict) -> str:
    """Generate a Markdown report from eval summary data."""
    summary = report.get("summary", report)
    total = summary.get("total_cases", 0)
    passed = summary.get("pass_count", 0)
    pass_rate = summary.get("pass_rate", 0)
    lines = [
        "# Eval Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total cases | {total} |",
        f"| Passed | {passed} |",
        f"| Failed | {total - passed} |",
        f"| Pass rate | {pass_rate:.1%} |",
    ]
    if summary.get("avg_latency_ms"):
        lines.append(f"| Avg latency | {summary['avg_latency_ms']:.0f}ms |")
    if summary.get("avg_cost_usd"):
        lines.append(f"| Avg cost | ${summary['avg_cost_usd']:.4f} |")


    if summary.get("failed_cases"):##===================================
        lines.extend(["", "## Failed Cases", ""])
        for case in summary["failed_cases"]:
            lines.append(f"- **{case.get('case_id', 'unknown')}**: {case.get('reason', 'N/A')}")


    diff = report.get("diff")##===================================
    if diff:
        lines.extend(["", "## Baseline Comparison", "", "```json", json.dumps(diff, indent=2), "```"])
    return "\n".join(lines)


def generate_json(report: dict) -> str:
    """Generate a JSON report."""
    return json.dumps(report, indent=2, default=str)
