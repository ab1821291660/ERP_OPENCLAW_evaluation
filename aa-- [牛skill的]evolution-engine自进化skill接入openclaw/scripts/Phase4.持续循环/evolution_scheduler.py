#!/usr/bin/env python3
"""Evolution scheduler for continuous evolution loop (Phase 4)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from eval_runner import EvalRunner
from performance_monitor import PerformanceMonitor
from skill_evolver import SkillEvolver


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent.parent.parent


class EvolutionScheduler:
    """Periodic scheduler for review/check workflows."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.evolution_dir = self.workspace_root / "evolution"
        self.reports_dir = self.evolution_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.monitor = PerformanceMonitor(str(self.workspace_root))
        self.evolver = SkillEvolver(str(self.workspace_root))
        self.eval_runner = EvalRunner(str(self.workspace_root))

    def run_weekly_review(self) -> Dict[str, Any]:
        metrics = self.monitor.collect_metrics()
        baselines = self._run_skill_baselines()
        triage = self.monitor.auto_triage()

        evolution_result: Dict[str, Any] = {"status": "skipped", "reason": "no eligible target"}
        target = self._pick_top_skill_target(triage)
        if target:
            try:
                evolution_result = self.evolver.evolve_skill(target)
            except Exception as exc:
                evolution_result = {
                    "status": "failed",
                    "target": target,
                    "error": str(exc),
                }

        report = self.monitor.generate_report()
        payload = {
            "ok": True,
            "mode": "weekly_review",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "metrics": metrics,
            "baseline_count": len(baselines),
            "baselines": baselines,
            "triage_top": triage[:5],
            "evolution_result": evolution_result,
            "report_preview": "\n".join(report.splitlines()[:20]),
        }
        self._save_json("weekly_review", payload)
        return payload

    def run_daily_check(self) -> Dict[str, Any]:
        metrics = self.monitor.collect_metrics()
        alerts = metrics.get("alerts", []) if isinstance(metrics.get("alerts"), list) else []
        triage = self.monitor.auto_triage()

        actions: List[Dict[str, Any]] = []
        if alerts:
            target = self._pick_top_skill_target(triage)
            if target:
                try:
                    result = self.evolver.evolve_skill(target)
                    actions.append({"action": "evolve_skill", "target": target, "result": result})
                except Exception as exc:
                    actions.append({"action": "evolve_skill", "target": target, "error": str(exc)})
            else:
                actions.append({"action": "none", "reason": "no skill target in triage"})
        else:
            actions.append({"action": "none", "reason": "no metric alerts"})

        payload = {
            "ok": True,
            "mode": "daily_check",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "metrics": metrics,
            "triage_top": triage[:5],
            "actions": actions,
        }
        self._save_json("daily_check", payload)
        return payload

    def suggest_cron_setup(self) -> str:
        return (
            "openclaw cron add --name weekly-evolution-review --cron \"0 3 * * 1\" --message "
            "\"执行每周进化审查：python3 evolution_scheduler.py weekly-review\"\n"
            "openclaw cron add --name daily-evolution-check --cron \"0 8 * * *\" --message "
            "\"执行每日进化检查：python3 evolution_scheduler.py daily-check\""
        )

    def _run_skill_baselines(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        skills_dir = self.workspace_root / "skills"
        if not skills_dir.exists():
            return results

        for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
            try:
                run = self.eval_runner.run_baseline(skill_path=str(skill_file), num_cases=12, judge_mode="auto")
                results.append(
                    {
                        "skill_path": str(skill_file),
                        "total_score": run.get("total_score"),
                        "saved_to": run.get("saved_to"),
                    }
                )
            except Exception as exc:
                results.append({"skill_path": str(skill_file), "error": str(exc)})
        return results

    def _pick_top_skill_target(self, triage: List[Dict[str, Any]]) -> str:
        for item in triage:
            target = str(item.get("target") or "").strip()
            if not target:
                continue
            if not target.endswith("SKILL.md"):
                continue
            target_path = Path(target)
            if target_path.exists():
                return str(target_path)
        return ""

    def _save_json(self, prefix: str, payload: Dict[str, Any]) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.reports_dir / f"{prefix}_{ts}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
        return str(path)


def _build_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="Evolution scheduler")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("weekly-review")
    sub.add_parser("daily-check")
    sub.add_parser("cron-setup")
    return parser


def main(argv: List[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    scheduler = EvolutionScheduler(str(WORKSPACE_ROOT))

    if args.command == "weekly-review":
        print(json.dumps(scheduler.run_weekly_review(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "daily-check":
        print(json.dumps(scheduler.run_daily_check(), ensure_ascii=False, indent=2))
        return 0

    print(scheduler.suggest_cron_setup())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
