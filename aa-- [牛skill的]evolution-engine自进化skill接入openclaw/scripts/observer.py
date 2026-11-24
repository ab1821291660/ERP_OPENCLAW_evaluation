#!/usr/bin/env python3
"""Observe daily interaction traces and extract evolution signals."""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SignalType(Enum):
    SKILL_MISS = "skill_miss"
    SKILL_QUALITY_LOW = "skill_quality_low"
    REPEATED_REQUEST = "repeated_request"
    USER_CORRECTION = "user_correction"
    EXECUTION_FAILURE = "execution_failure"
    ROUTING_ERROR = "routing_error"
    CONFIG_GAP = "config_gap"
    PROCESS_IMPROVEMENT = "process_improvement"


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


KEYWORDS_FAILURE = ["失败", "错误", "不行", "重试", "报错", "超时", "中断", "exception"]
KEYWORDS_CORRECTION = ["不对", "改一下", "改成", "不是这个", "你错了", "重新"]
KEYWORDS_ROUTING = ["应该用", "没调用", "路由", "该用", "漏了 skill", "skill 没命中"]
KEYWORDS_PROCESS = ["优化", "流程", "可以自动", "建议", "改进"]
KEYWORDS_CONFIG = ["配置", "缺失", "环境变量", "权限", "未设置"]


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("observer")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = _setup_logger()


@dataclass
class Signal:
    id: str
    type: str
    description: str
    severity: str
    count: int
    examples: List[str]
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "severity": self.severity,
            "count": self.count,
            "examples": self.examples,
            "source": self.source,
        }


class Observer:
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.memory_dir = self.workspace_root / "memory"
        self.evolution_dir = self.workspace_root / "evolution"
        self.signals_dir = self.evolution_dir / "signals"
        self.signals_dir.mkdir(parents=True, exist_ok=True)

    def observe(self, date: Optional[str] = None) -> Dict[str, Any]:
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        signals: List[Dict[str, Any]] = []

        signals.extend(self._extract_from_daily_note(target_date))
        signals.extend(self._check_skill_coverage(target_date))
        signals.extend(self._check_execution_failures(target_date))

        payload = {
            "date": target_date,
            "signals": signals,
            "summary": self._summarize(signals),
            "signal_count": len(signals),
            "created_at": datetime.now().isoformat(),
        }
        self._save_observation(payload)
        return payload

    def _extract_from_daily_note(self, date: str) -> List[Dict[str, Any]]:
        note_path = self.memory_dir / f"{date}.md"
        if not note_path.exists():
            return []

        content = note_path.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        signals: List[Dict[str, Any]] = []

        def collect(keyword_list: List[str]) -> List[str]:
            matches: List[str] = []
            for line in lines:
                lowered = line.lower()
                for keyword in keyword_list:
                    if keyword.lower() in lowered:
                        matches.append(line)
                        break
            return matches

        failed_lines = collect(KEYWORDS_FAILURE)
        if failed_lines:
            signals.append(
                self._build_signal(
                    SignalType.EXECUTION_FAILURE,
                    Severity.HIGH,
                    f"Daily note contains failure indicators ({len(failed_lines)}).",
                    failed_lines,
                    source=str(note_path),
                )
            )

        correction_lines = collect(KEYWORDS_CORRECTION)
        if correction_lines:
            signals.append(
                self._build_signal(
                    SignalType.USER_CORRECTION,
                    Severity.MEDIUM,
                    f"Daily note contains user correction cues ({len(correction_lines)}).",
                    correction_lines,
                    source=str(note_path),
                )
            )

        routing_lines = collect(KEYWORDS_ROUTING)
        if routing_lines:
            signals.append(
                self._build_signal(
                    SignalType.ROUTING_ERROR,
                    Severity.HIGH,
                    f"Daily note suggests skill routing misses ({len(routing_lines)}).",
                    routing_lines,
                    source=str(note_path),
                )
            )

        process_lines = collect(KEYWORDS_PROCESS)
        if process_lines:
            signals.append(
                self._build_signal(
                    SignalType.PROCESS_IMPROVEMENT,
                    Severity.LOW,
                    f"Daily note includes process improvement opportunities ({len(process_lines)}).",
                    process_lines,
                    source=str(note_path),
                )
            )

        config_lines = collect(KEYWORDS_CONFIG)
        if config_lines:
            signals.append(
                self._build_signal(
                    SignalType.CONFIG_GAP,
                    Severity.MEDIUM,
                    f"Daily note points to potential config gaps ({len(config_lines)}).",
                    config_lines,
                    source=str(note_path),
                )
            )

        repeated = self._detect_repeated_requests(lines)
        if repeated:
            signals.append(
                self._build_signal(
                    SignalType.REPEATED_REQUEST,
                    Severity.MEDIUM,
                    f"Repeated request patterns detected ({len(repeated)} groups).",
                    repeated,
                    source=str(note_path),
                )
            )

        return signals

    def _check_skill_coverage(self, date: str) -> List[Dict[str, Any]]:
        note_path = self.memory_dir / f"{date}.md"
        if not note_path.exists():
            return []

        content = note_path.read_text(encoding="utf-8")
        mention_count = len(re.findall(r"\bskill\b", content, flags=re.IGNORECASE))
        if mention_count > 0:
            return []

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if len(lines) < 2:
            return []

        signal = self._build_signal(
            SignalType.SKILL_MISS,
            Severity.MEDIUM,
            "No explicit skill reference found in daily note; coverage may be missing.",
            lines[:3],
            source=str(note_path),
        )
        return [signal]

    def _check_execution_failures(self, date: str) -> List[Dict[str, Any]]:
        log_path = self.evolution_dir / "log" / f"{date}.md"
        if not log_path.exists():
            return []

        content = log_path.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip().startswith("-")]
        failed = [line for line in lines if "fail" in line.lower() or "error" in line.lower()]
        if not failed:
            return []

        severity = Severity.CRITICAL if len(failed) >= 3 else Severity.HIGH
        signal = self._build_signal(
            SignalType.EXECUTION_FAILURE,
            severity,
            f"Evolution logs contain failure events ({len(failed)}).",
            failed[:5],
            source=str(log_path),
        )
        return [signal]

    def _build_signal(
        self,
        signal_type: SignalType,
        severity: Severity,
        description: str,
        examples: List[str],
        source: str,
    ) -> Dict[str, Any]:
        signal_id = f"S{int(datetime.now().timestamp() * 1000)}{len(examples):02d}"
        signal = Signal(
            id=signal_id,
            type=signal_type.value,
            description=description,
            severity=severity.value,
            count=max(1, len(examples)),
            examples=examples[:5],
            source=source,
        )
        return signal.to_dict()

    def _detect_repeated_requests(self, lines: List[str]) -> List[str]:
        normalized: List[str] = []
        for line in lines:
            cleaned = re.sub(r"\d+", "", line)
            cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
            if len(cleaned) < 6:
                continue
            normalized.append(cleaned)

        counter = Counter(normalized)
        repeated: List[str] = []
        for text, count in counter.items():
            if count >= 2:
                repeated.append(f"{text} (x{count})")
        return repeated[:5]

    def _summarize(self, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}

        for signal in signals:
            signal_type = str(signal.get("type", "unknown"))
            severity = str(signal.get("severity", "unknown"))
            by_type[signal_type] = by_type.get(signal_type, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1

        return {
            "total": len(signals),
            "by_type": by_type,
            "by_severity": by_severity,
            "has_critical": by_severity.get(Severity.CRITICAL.value, 0) > 0,
        }

    def _save_observation(self, payload: Dict[str, Any]) -> None:
        date = str(payload.get("date", datetime.now().strftime("%Y-%m-%d")))
        target = self.signals_dir / f"{date}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
        LOGGER.info(f"Observation saved to {target}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent.parent.parent
    observer = Observer(str(root))
    print(json.dumps(observer.observe(), ensure_ascii=False, indent=2))
