#!/usr/bin/env python3
"""Track effectiveness of approved behavior rules."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional


class RuleTracker:
    """Track trigger frequency and outcome trend for rules."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.store_dir = self.workspace_root / "evolution" / "rule-tracker"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.store_dir / "rule_events.jsonl"

    def record_rule_application(self, signature: str, target_file: str, context: str) -> str:
        event_id = f"evt_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        payload = {
            "event_id": event_id,
            "signature": signature.strip().lower(),
            "target_file": target_file,
            "context": context,
            "outcome_score": self._infer_outcome_score(context),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        with self.events_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return event_id

    def get_rule_stats(self, signature: str, window_days: int = 30) -> Dict[str, Any]:
        normalized = signature.strip().lower()
        records = [item for item in self._read_events() if str(item.get("signature", "")).strip().lower() == normalized]

        cutoff = datetime.now() - timedelta(days=window_days)
        windowed: List[Dict[str, Any]] = []
        for item in records:
            ts = str(item.get("created_at", ""))
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                continue
            if dt >= cutoff:
                windowed.append(item)

        active = windowed if windowed else records
        trigger_count = len(active)
        scores = [float(item.get("outcome_score", 0.5)) for item in active]
        avg_score = round(mean(scores), 4) if scores else 0.0

        last_triggered = None
        if active:
            timestamps = [str(item.get("created_at", "")) for item in active]
            last_triggered = max(timestamps)

        effectiveness = self._effectiveness_label(avg_score, trigger_count)
        recommendation = self._recommendation(effectiveness, trigger_count, last_triggered, window_days)

        return {
            "signature": normalized,
            "trigger_count": trigger_count,
            "avg_outcome_score": avg_score,
            "last_triggered": last_triggered,
            "effectiveness": effectiveness,
            "recommendation": recommendation,
        }

    def scan_stale_rules(self, threshold_days: int = 30) -> List[Dict[str, Any]]:
        events = self._read_events()
        signatures = sorted({str(item.get("signature", "")).strip().lower() for item in events if item.get("signature")})

        stale: List[Dict[str, Any]] = []
        for signature in signatures:
            stats = self.get_rule_stats(signature=signature, window_days=threshold_days)
            reason = None
            if stats.get("trigger_count", 0) == 0:
                reason = "no_recent_trigger"
            elif stats.get("effectiveness") == "negative":
                reason = "negative_effectiveness"

            if reason:
                stale.append(
                    {
                        "signature": signature,
                        "reason": reason,
                        "stats": stats,
                    }
                )
        return stale

    def generate_effect_report(self) -> Dict[str, Any]:
        events = self._read_events()
        signatures = sorted({str(item.get("signature", "")).strip().lower() for item in events if item.get("signature")})
        reports = [self.get_rule_stats(signature=sig, window_days=30) for sig in signatures]

        positive = sum(1 for item in reports if item.get("effectiveness") == "positive")
        neutral = sum(1 for item in reports if item.get("effectiveness") == "neutral")
        negative = sum(1 for item in reports if item.get("effectiveness") == "negative")

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "total_rules": len(reports),
            "positive_rules": positive,
            "neutral_rules": neutral,
            "negative_rules": negative,
            "rules": reports,
        }

    def _read_events(self) -> List[Dict[str, Any]]:
        if not self.events_file.exists():
            return []
        records: List[Dict[str, Any]] = []
        for raw in self.events_file.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
        return records

    def _infer_outcome_score(self, context: str) -> float:
        lowered = context.lower()
        positive_keywords = ["success", "improved", "解决", "修复", "顺利", "通过"]
        negative_keywords = ["fail", "error", "回退", "问题", "报错", "失败"]

        if any(token in lowered for token in positive_keywords):
            return 0.9
        if any(token in lowered for token in negative_keywords):
            return 0.2
        return 0.5

    def _effectiveness_label(self, avg_score: float, trigger_count: int) -> str:
        if trigger_count == 0:
            return "neutral"
        if avg_score >= 0.65:
            return "positive"
        if avg_score < 0.45:
            return "negative"
        return "neutral"

    def _recommendation(
        self,
        effectiveness: str,
        trigger_count: int,
        last_triggered: Optional[str],
        window_days: int,
    ) -> str:
        if trigger_count == 0:
            return "review"
        if effectiveness == "negative":
            return "cleanup"

        if last_triggered:
            try:
                dt = datetime.fromisoformat(last_triggered)
                if dt < datetime.now() - timedelta(days=window_days):
                    return "review"
            except ValueError:
                return "review"

        return "keep"


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent.parent.parent
    tracker = RuleTracker(str(root))
    print(json.dumps(tracker.generate_effect_report(), ensure_ascii=False, indent=2))
