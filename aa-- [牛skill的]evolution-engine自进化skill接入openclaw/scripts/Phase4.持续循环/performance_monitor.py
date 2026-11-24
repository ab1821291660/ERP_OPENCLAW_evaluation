#!/usr/bin/env python3
"""Performance monitor and auto-triage for Phase 4."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from trace_collector import TraceCollector


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent.parent.parent


class PerformanceMonitor:
    """Performance monitoring and auto-triage."""

    METRICS = {
        "skill_success_rate": {
            "threshold": 0.8,
            "window_days": 7,
            "action": "触发 skill 进化",
        },
        "user_correction_rate": {
            "threshold": 0.1,
            "window_days": 7,
            "action": "触发 prompt 进化",
        },
        "task_completion_rate": {
            "threshold": 0.85,
            "window_days": 7,
            "action": "全局诊断",
        },
        "proposal_approval_rate": {
            "threshold": 0.5,
            "window_days": 14,
            "action": "降低进化敏感度",
        },
    }

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.evolution_dir = self.workspace_root / "evolution"
        self.memory_dir = self.workspace_root / "memory"
        self.reports_dir = self.evolution_dir / "reports"
        self.traces_dir = self.evolution_dir / "traces"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.collector = TraceCollector(str(self.workspace_root))

    def collect_metrics(self) -> Dict[str, Any]:
        values = {
            "skill_success_rate": self._skill_success_rate(),
            "user_correction_rate": self._user_correction_rate(),
            "task_completion_rate": self._task_completion_rate(),
            "proposal_approval_rate": self._proposal_approval_rate(),
        }

        metrics: Dict[str, Dict[str, Any]] = {}
        alerts: List[str] = []
        actions: List[str] = []

        for metric_name, value in values.items():
            config = self.METRICS[metric_name]
            threshold = float(config["threshold"])
            status = "ok" if value >= threshold else "alert"
            metrics[metric_name] = {
                "value": round(value, 4),
                "threshold": threshold,
                "window_days": int(config["window_days"]),
                "status": status,
            }
            if status == "alert":
                alerts.append(f"{metric_name} 低于阈值 ({value:.4f} < {threshold})")
                actions.append(str(config["action"]))

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "metrics": metrics,
            "alerts": alerts,
            "actions": sorted(set(actions)),
        }

    def auto_triage(self) -> List[Dict[str, Any]]:
        traces = self._recent_traces(window_days=7)
        usage_by_skill: Dict[str, int] = {}
        failures_by_skill: Dict[str, int] = {}

        for item in traces:
            skill = str(item.get("skill_name") or "").strip()
            if not skill:
                continue
            usage_by_skill[skill] = usage_by_skill.get(skill, 0) + 1
            if not bool(item.get("success", False)):
                failures_by_skill[skill] = failures_by_skill.get(skill, 0) + 1

        max_usage = max(usage_by_skill.values()) if usage_by_skill else 1
        ranked: List[Dict[str, Any]] = []

        for skill, usage in usage_by_skill.items():
            failure_count = failures_by_skill.get(skill, 0)
            improvement_potential = failure_count / usage if usage else 0.0
            frequency = usage / max_usage if max_usage else 0.0
            priority = round(improvement_potential * frequency, 4)

            target = self._skill_target_path(skill)
            reason = f"成功率低({1.0 - improvement_potential:.2f})且使用频繁({usage}次/7天)"
            ranked.append(
                {
                    "target": target,
                    "priority": priority,
                    "reason": reason,
                    "skill_name": skill,
                    "usage": usage,
                    "improvement_potential": round(improvement_potential, 4),
                }
            )

        correction_metric = self._user_correction_rate()
        if correction_metric < self.METRICS["user_correction_rate"]["threshold"]:
            ranked.append(
                {
                    "target": str(self.workspace_root / "AGENTS.md"),
                    "priority": round(1.0 - correction_metric, 4),
                    "reason": f"用户纠正率偏高({1.0 - correction_metric:.2f})",
                    "skill_name": None,
                    "usage": 0,
                    "improvement_potential": round(1.0 - correction_metric, 4),
                }
            )

        ranked.sort(key=lambda x: float(x.get("priority", 0.0)), reverse=True)
        return ranked

    def generate_report(self) -> str:
        metrics = self.collect_metrics()
        triage = self.auto_triage()

        lines: List[str] = []
        lines.append("# Evolution Performance Report")
        lines.append("")
        lines.append(f"Generated at: {metrics['generated_at']}")
        lines.append("")
        lines.append("## Metrics")
        for name, item in metrics["metrics"].items():
            lines.append(
                f"- {name}: {item['value']:.4f} (threshold={item['threshold']:.2f}, status={item['status']})"
            )

        lines.append("")
        lines.append("## Alerts")
        if metrics["alerts"]:
            lines.extend([f"- {x}" for x in metrics["alerts"]])
        else:
            lines.append("- None")

        lines.append("")
        lines.append("## Suggested Actions")
        if metrics["actions"]:
            lines.extend([f"- {x}" for x in metrics["actions"]])
        else:
            lines.append("- Keep monitoring")

        lines.append("")
        lines.append("## Triage Top Targets")
        if triage:
            for item in triage[:10]:
                lines.append(
                    f"- {item['target']} | priority={item['priority']:.4f} | {item['reason']}"
                )
        else:
            lines.append("- No targets")

        report = "\n".join(lines).rstrip() + "\n"
        self._save_report(report)
        return report

    def _skill_success_rate(self) -> float:
        traces = self._recent_traces(window_days=self.METRICS["skill_success_rate"]["window_days"])
        if not traces:
            return 1.0
        successes = sum(1 for x in traces if bool(x.get("success", False)))
        return successes / len(traces)

    def _task_completion_rate(self) -> float:
        traces = self._recent_traces(window_days=self.METRICS["task_completion_rate"]["window_days"])
        if not traces:
            return 1.0
        completed = sum(1 for x in traces if bool(x.get("success", False)))
        return completed / len(traces)

    def _user_correction_rate(self) -> float:
        window_days = int(self.METRICS["user_correction_rate"]["window_days"])
        files = self._recent_memory_files(window_days)
        total_lines = 0
        correction_lines = 0
        patt = re.compile(r"不对|改一下|改成|不是这个|你错了|重新|纠正", flags=re.I)

        for path in files:
            content = path.read_text(encoding="utf-8", errors="ignore")
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            total_lines += len(lines)
            correction_lines += sum(1 for line in lines if patt.search(line))

        if total_lines == 0:
            return 1.0
        return max(0.0, 1.0 - (correction_lines / total_lines))

    def _proposal_approval_rate(self) -> float:
        window_days = int(self.METRICS["proposal_approval_rate"]["window_days"])
        cutoff = datetime.now() - timedelta(days=window_days)

        candidate_dirs = [
            self.workspace_root / "evolution-drafts",
            self.evolution_dir / "drafts",
            self.evolution_dir / "proposals",
        ]

        total = 0
        approved = 0
        for base in candidate_dirs:
            if not base.exists():
                continue
            for path in base.rglob("*.json"):
                try:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                except Exception:
                    continue
                if mtime < cutoff:
                    continue

                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue

                status = str(payload.get("status", "")).lower()
                if not status and isinstance(payload.get("approved"), bool):
                    status = "approved" if payload.get("approved") else "rejected"

                if status not in {"approved", "rejected", "declined"}:
                    continue
                total += 1
                if status == "approved":
                    approved += 1

        if total == 0:
            return 1.0
        return approved / total

    def _recent_memory_files(self, window_days: int) -> List[Path]:
        files: List[Path] = []
        today = datetime.now().date()

        for i in range(window_days):
            target = today - timedelta(days=i)
            path = self.memory_dir / f"{target.isoformat()}.md"
            if path.exists():
                files.append(path)
        return files

    def _recent_traces(self, window_days: int) -> List[Dict[str, Any]]:
        cutoff = datetime.now() - timedelta(days=window_days)
        records: List[Dict[str, Any]] = []

        if not self.traces_dir.exists():
            return records

        for path in sorted(self.traces_dir.glob("*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            created = str(payload.get("created_at", ""))
            try:
                created_dt = datetime.fromisoformat(created)
            except Exception:
                continue
            if created_dt < cutoff:
                continue
            records.append(payload)
        return records

    def _skill_target_path(self, skill_name: str) -> str:
        candidate = self.workspace_root / "skills" / skill_name / "SKILL.md"
        if candidate.exists():
            return str(candidate)
        return skill_name

    def _save_report(self, markdown: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.reports_dir / f"performance_{ts}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(markdown, encoding="utf-8")
        os.replace(tmp, path)
        return str(path)


def _build_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="Performance monitor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("metrics")
    sub.add_parser("triage")
    sub.add_parser("report")
    return parser


def main(argv: List[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    monitor = PerformanceMonitor(str(WORKSPACE_ROOT))

    if args.command == "metrics":
        print(json.dumps(monitor.collect_metrics(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "triage":
        print(json.dumps({"targets": monitor.auto_triage()}, ensure_ascii=False, indent=2))
        return 0

    print(monitor.generate_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
