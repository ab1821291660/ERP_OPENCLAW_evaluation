#!/usr/bin/env python3
"""Enhanced signal detector for Phase 1 behavior rule distillation."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("signal_detector")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = _setup_logger()


class SignalDetector:
    """Enhanced evolution signal detection with strong/medium grading."""

    STRONG_SIGNALS = {
        "correction": "用户明确纠正了agent的输出或行为",
        "preference": "用户明确表达了稳定偏好（以后都这样/不要这样）",
        "workflow_teach": "用户教授了一个可复用的新工作流",
        "struggle_success": "经过明显失败/重试后才成功",
    }

    MEDIUM_SIGNALS = {
        "pattern": "同类任务出现了清晰的步骤模式",
        "tool_pitfall": "某个工具/环境有值得长期记住的坑点",
        "repeated_preference": "同一偏好在近期被重复提到",
    }

    SKIP_CONDITIONS = [
        "纯闲聊",
        "单轮简单问答",
        "tool call很少且没有纠正/偏好",
        "一次性上下文要求",
        "用户明确说这次只是临时的",
    ]

    _CORRECTION_PATTERNS = ["不对", "改一下", "应该是", "我说的是", "你错了", "不是这个"]
    _PREFERENCE_PATTERNS = ["以后", "总是", "不要", "帮我", "每次", "默认"]
    _WORKFLOW_PATTERNS = ["步骤", "流程", "按这个来", "先", "然后", "最后", "固定"]
    _STRUGGLE_PATTERNS = ["失败", "重试", "换一个", "报错", "不行", "卡住", "终于"]
    _PITFALL_PATTERNS = ["坑", "注意", "兼容", "环境", "权限", "路径", "配置", "包名"]
    _TEMPORARY_PATTERNS = ["这次临时", "仅这次", "一次性", "先这样"]

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.memory_dir = self.workspace_root / "memory"
        self.evolution_dir = self.workspace_root / "evolution"
        self.signals_dir = self.evolution_dir / "signals"
        self.signals_dir.mkdir(parents=True, exist_ok=True)

    def detect(self, date: Optional[str] = None) -> Dict[str, Any]:
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        extracted = self._extract_from_daily_note(target_date)

        strong_signals = [item for item in extracted if item.get("level") == "strong"]
        medium_signals = [item for item in extracted if item.get("level") == "medium"]

        skip_reason = self._infer_skip_reason(extracted)
        gate_passed = self._cheap_gate({"strong_signals": strong_signals, "medium_signals": medium_signals})
        should_check = skip_reason is None and gate_passed

        payload = {
            "date": target_date,
            "strong_signals": strong_signals,
            "medium_signals": medium_signals,
            "skip_reason": skip_reason,
            "should_check": should_check,
            "gate_passed": gate_passed,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._save(payload)
        return payload

    def _cheap_gate(self, signals: Dict[str, Any]) -> bool:
        strong_count = len(signals.get("strong_signals", []))
        medium_count = len(signals.get("medium_signals", []))
        return strong_count >= 1 or medium_count >= 2

    def _extract_from_daily_note(self, date: str) -> List[Dict[str, Any]]:
        note_path = self.memory_dir / f"{date}.md"
        if not note_path.exists():
            return []

        content = note_path.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip()]

        signals: List[Dict[str, Any]] = []
        signals.extend(self._detect_keyword_signals(lines, "correction", self._CORRECTION_PATTERNS, "strong"))
        signals.extend(self._detect_keyword_signals(lines, "preference", self._PREFERENCE_PATTERNS, "strong"))
        signals.extend(self._detect_keyword_signals(lines, "workflow_teach", self._WORKFLOW_PATTERNS, "strong"))
        signals.extend(self._detect_keyword_signals(lines, "struggle_success", self._STRUGGLE_PATTERNS, "strong"))
        signals.extend(self._detect_keyword_signals(lines, "tool_pitfall", self._PITFALL_PATTERNS, "medium"))

        repeated = self._detect_repeated_patterns(lines)
        if repeated:
            signals.append(
                {
                    "type": "pattern",
                    "level": "medium",
                    "description": self.MEDIUM_SIGNALS["pattern"],
                    "evidence": repeated,
                    "count": len(repeated),
                    "source": str(note_path),
                }
            )

        repeated_pref = self._detect_repeated_preferences(lines)
        if repeated_pref:
            signals.append(
                {
                    "type": "repeated_preference",
                    "level": "medium",
                    "description": self.MEDIUM_SIGNALS["repeated_preference"],
                    "evidence": repeated_pref,
                    "count": len(repeated_pref),
                    "source": str(note_path),
                }
            )

        deduped: Dict[str, Dict[str, Any]] = {}
        for item in signals:
            key = f"{item.get('type')}::{json.dumps(item.get('evidence', []), ensure_ascii=False, sort_keys=True)}"
            if key not in deduped:
                deduped[key] = item

        return list(deduped.values())

    def _detect_keyword_signals(
        self,
        lines: List[str],
        signal_type: str,
        patterns: List[str],
        level: str,
    ) -> List[Dict[str, Any]]:
        evidence: List[str] = []
        for line in lines:
            lowered = line.lower()
            if any(keyword.lower() in lowered for keyword in patterns):
                evidence.append(line)

        if not evidence:
            return []

        description_map = self.STRONG_SIGNALS if level == "strong" else self.MEDIUM_SIGNALS
        return [
            {
                "type": signal_type,
                "level": level,
                "description": description_map.get(signal_type, signal_type),
                "evidence": evidence[:5],
                "count": len(evidence),
            }
        ]

    def _detect_repeated_patterns(self, lines: List[str]) -> List[str]:
        normalized: Dict[str, int] = {}
        display_map: Dict[str, str] = {}

        for line in lines:
            cleaned = re.sub(r"\d+", "", line)
            cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
            if len(cleaned) < 8:
                continue
            normalized[cleaned] = normalized.get(cleaned, 0) + 1
            display_map[cleaned] = line

        repeated: List[str] = []
        for key, count in normalized.items():
            if count >= 2:
                repeated.append(f"{display_map[key]} (x{count})")
        return repeated[:5]

    def _detect_repeated_preferences(self, lines: List[str]) -> List[str]:
        pref_lines = [line for line in lines if any(token in line for token in ["以后", "不要", "总是", "默认", "风格"])]
        if len(pref_lines) < 2:
            return []

        unique: List[str] = []
        seen: set[str] = set()
        for line in pref_lines:
            normalized = re.sub(r"\s+", "", line)
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(line)
        return unique[:5]

    def _infer_skip_reason(self, signals: List[Dict[str, Any]]) -> Optional[str]:
        if not signals:
            return self.SKIP_CONDITIONS[1]

        all_evidence = "\n".join(",".join(item.get("evidence", [])) for item in signals if isinstance(item.get("evidence"), list))

        for marker in self._TEMPORARY_PATTERNS:
            if marker in all_evidence:
                return self.SKIP_CONDITIONS[4]

        if len(signals) == 1 and signals[0].get("type") == "pattern":
            return self.SKIP_CONDITIONS[2]

        return None

    def _save(self, payload: Dict[str, Any]) -> None:
        date = str(payload.get("date", datetime.now().strftime("%Y-%m-%d")))
        target = self.signals_dir / f"{date}_phase1.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
        LOGGER.info(f"Phase1 signals saved to {target}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent.parent.parent
    detector = SignalDetector(str(root))
    print(json.dumps(detector.detect(), ensure_ascii=False, indent=2))
