#!/usr/bin/env python3
"""Execution trace collector and statistics."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent.parent.parent


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


class TraceCollector:
    """Collect and query execution traces."""

    def __init__(self, workspace_root: str):
        self.trace_dir = Path(workspace_root).resolve() / "evolution" / "traces"
        self.trace_dir.mkdir(parents=True, exist_ok=True)

    def record_trace(
        self,
        skill_name: str,
        task_input: str,
        tool_calls: List[Dict[str, Any]],
        output: str,
        success: bool,
        user_feedback: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> str:
        trace_id = self._new_trace_id(skill_name)
        payload = {
            "trace_id": trace_id,
            "skill_name": skill_name,
            "task_input": task_input,
            "tool_calls": tool_calls,
            "output": output,
            "success": bool(success),
            "user_feedback": user_feedback,
            "duration_ms": int(duration_ms) if duration_ms is not None else None,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

        trace_path = self.trace_dir / f"{trace_id}.json"
        _atomic_write_json(trace_path, payload)
        return trace_id

    def get_traces(
        self,
        skill_name: Optional[str] = None,
        success_only: bool = False,
        failure_only: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        paths = sorted(self.trace_dir.glob("*.json"), reverse=True)

        for path in paths:
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue

            if skill_name and str(item.get("skill_name")) != skill_name:
                continue
            if success_only and not bool(item.get("success", False)):
                continue
            if failure_only and bool(item.get("success", False)):
                continue

            records.append(item)
            if len(records) >= max(1, limit):
                break

        return records

    def get_skill_stats(self, skill_name: str, window_days: int = 7) -> Dict[str, Any]:
        traces = self.get_traces(skill_name=skill_name, limit=10000)
        if not traces:
            return {
                "skill_name": skill_name,
                "window_days": window_days,
                "total_calls": 0,
                "success_rate": 0.0,
                "avg_duration_ms": None,
                "common_failures": [],
                "improvement_potential": 1.0,
            }

        cutoff = datetime.now() - timedelta(days=window_days)
        in_window: List[Dict[str, Any]] = []
        for item in traces:
            created = str(item.get("created_at", ""))
            try:
                created_dt = datetime.fromisoformat(created)
            except ValueError:
                continue
            if created_dt >= cutoff:
                in_window.append(item)

        window_records = in_window if in_window else traces
        total = len(window_records)
        successes = sum(1 for item in window_records if bool(item.get("success", False)))
        success_rate = successes / total if total else 0.0

        durations = [int(item.get("duration_ms")) for item in window_records if isinstance(item.get("duration_ms"), int)]
        avg_duration = int(mean(durations)) if durations else None

        failure_reasons = self._collect_failure_reasons(window_records)
        common_failures = sorted(failure_reasons, key=failure_reasons.get, reverse=True)[:3]

        return {
            "skill_name": skill_name,
            "window_days": window_days,
            "total_calls": total,
            "success_rate": round(success_rate, 4),
            "avg_duration_ms": avg_duration,
            "common_failures": common_failures,
            "improvement_potential": round(1.0 - success_rate, 4),
        }

    def _collect_failure_reasons(self, traces: List[Dict[str, Any]]) -> Dict[str, int]:
        reasons: Dict[str, int] = {}
        for item in traces:
            if bool(item.get("success", False)):
                continue
            feedback = str(item.get("user_feedback") or "").strip().lower()
            if feedback:
                key = feedback.split(".")[0][:40]
            else:
                key = "unknown_failure"
            reasons[key] = reasons.get(key, 0) + 1
        return reasons

    def _new_trace_id(self, skill_name: str) -> str:
        slug = "".join(ch for ch in skill_name.lower() if ch.isalnum() or ch in {"-", "_"}) or "skill"
        return f"trace_{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trace collector")
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record")
    record.add_argument("--skill-name", required=True)
    record.add_argument("--task-input", required=True)
    record.add_argument("--output", required=True)
    record.add_argument("--success", action="store_true")
    record.add_argument("--duration-ms", type=int, default=None)
    record.add_argument("--user-feedback", default=None)

    traces = sub.add_parser("list")
    traces.add_argument("--skill-name", default=None)
    traces.add_argument("--success-only", action="store_true")
    traces.add_argument("--failure-only", action="store_true")
    traces.add_argument("--limit", type=int, default=100)

    stats = sub.add_parser("stats")
    stats.add_argument("--skill-name", required=True)
    stats.add_argument("--window-days", type=int, default=7)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    collector = TraceCollector(str(WORKSPACE_ROOT))

    if args.command == "record":
        trace_id = collector.record_trace(
            skill_name=args.skill_name,
            task_input=args.task_input,
            tool_calls=[],
            output=args.output,
            success=args.success,
            user_feedback=args.user_feedback,
            duration_ms=args.duration_ms,
        )
        print(json.dumps({"trace_id": trace_id}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "list":
        items = collector.get_traces(
            skill_name=args.skill_name,
            success_only=args.success_only,
            failure_only=args.failure_only,
            limit=args.limit,
        )
        print(json.dumps({"traces": items}, ensure_ascii=False, indent=2))
        return 0

    stats = collector.get_skill_stats(skill_name=args.skill_name, window_days=args.window_days)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
