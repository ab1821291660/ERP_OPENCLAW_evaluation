#!/usr/bin/env python3
"""Reflect over observation signals and generate actionable hypotheses."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from proposal_manager import ProposalManager


class ActionType(Enum):
    CREATE_SKILL = "create_skill"
    MODIFY_SKILL_MD = "modify_skill_md"
    MODIFY_SKILL_SCRIPT = "modify_skill_script"
    MODIFY_MEMORY = "modify_memory"
    MODIFY_AGENTS = "modify_agents"
    MODIFY_SOUL = "modify_soul"
    CREATE_STANDING_ORDER = "create_standing_order"
    CREATE_CRON = "create_cron"
    MODIFY_CONFIG = "modify_config"


RISK_RULES = {
    ActionType.CREATE_SKILL.value: "low",
    ActionType.MODIFY_SKILL_MD.value: "medium",
    ActionType.MODIFY_SKILL_SCRIPT.value: "high",
    ActionType.MODIFY_MEMORY.value: "low",
    ActionType.MODIFY_AGENTS.value: "medium",
    ActionType.MODIFY_SOUL.value: "high",
    ActionType.CREATE_STANDING_ORDER.value: "medium",
    ActionType.CREATE_CRON.value: "medium",
    ActionType.MODIFY_CONFIG.value: "critical",
}


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("reflector")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = _setup_logger()


class Reflector:
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.evolution_dir = self.workspace_root / "evolution"
        self.hypotheses_dir = self.evolution_dir / "hypotheses"
        self.signals_dir = self.evolution_dir / "signals"
        self.proposal_manager = ProposalManager(str(self.workspace_root))
        self.hypotheses_dir.mkdir(parents=True, exist_ok=True)

    def reflect(self, signals: Dict[str, Any]) -> Dict[str, Any]:
        date = str(signals.get("date", datetime.now().strftime("%Y-%m-%d")))
        hypotheses: List[Dict[str, Any]] = []

        for signal in signals.get("signals", []):
            hypothesis = self._analyze_signal(signal)
            if hypothesis:
                hypotheses.append(hypothesis)

        hypotheses = self._deduplicate(hypotheses)

        payload = {
            "date": date,
            "hypotheses": hypotheses,
            "signal_count": len(signals.get("signals", [])),
            "hypothesis_count": len(hypotheses),
            "created_at": datetime.now().isoformat(),
        }
        self._save(payload)
        return payload

    def reflect_from_date(self, date: Optional[str] = None) -> Dict[str, Any]:
        target_date = date or datetime.now().strftime("%Y-%m-%d")
        signal_path = self.signals_dir / f"{target_date}.json"
        if signal_path.exists():
            signals = json.loads(signal_path.read_text(encoding="utf-8"))
        else:
            signals = {"date": target_date, "signals": []}
        return self.reflect(signals)

    def reflect_with_proposals(self, signals: Dict[str, Any]) -> Dict[str, Any]:
        reflected = self.reflect(signals)
        proposals: List[Dict[str, Any]] = []

        for hypothesis in reflected.get("hypotheses", []):
            signature = str(hypothesis.get("signature", "")).strip()
            target_file = str(hypothesis.get("target_file", "")).strip()
            proposed_change = str(hypothesis.get("proposed_change", "")).strip()
            if not signature or not target_file or not proposed_change:
                continue

            duplicate = self.proposal_manager.check_duplicates(signature)
            if duplicate.get("is_duplicate", False):
                proposals.append(
                    {
                        "signature": signature,
                        "status": "duplicate",
                        "duplicate": duplicate,
                    }
                )
                continue

            result = self.proposal_manager.create_proposal(
                signature=signature,
                target_file=target_file,
                trigger_type=self._trigger_type(hypothesis),
                evidence=list(hypothesis.get("signal_refs", [])),
                proposed_change=proposed_change,
                confidence=self._confidence_bucket(float(hypothesis.get("confidence", 0.0))),
                reason=str(hypothesis.get("reasoning", "")).strip() or "reflector generated proposal",
            )
            if result.get("ok"):
                eval_result = self.proposal_manager.evaluate_proposal(signature)
                result["evaluation"] = eval_result
            proposals.append(result)

        reflected["proposals"] = proposals
        reflected["proposal_count"] = len(proposals)
        return reflected

    def _analyze_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        signal_type = str(signal.get("type", ""))
        signal_id = str(signal.get("id", "")) or f"S{int(datetime.now().timestamp() * 1000)}"

        action_type, action_detail, confidence, reasoning = self._map_signal_to_action(signal)
        if not action_type:
            return None

        risk = RISK_RULES.get(action_type, "medium")
        hypothesis_id = f"H{int(datetime.now().timestamp() * 1000)}"

        hypothesis = {
            "id": hypothesis_id,
            "created_at": datetime.now().isoformat(),
            "signal_refs": [signal_id],
            "root_cause": self._root_cause(signal_type),
            "action_type": action_type,
            "action_detail": action_detail,
            "confidence": round(confidence, 2),
            "risk": risk,
            "reasoning": reasoning,
            "auto_approve_eligible": self._is_auto_approve_eligible(risk, confidence),
            "status": "pending",
        }
        hypothesis["target_file"] = self._route_target(hypothesis)
        hypothesis["signature"] = self._generate_signature(action_type, action_detail)
        hypothesis["proposed_change"] = self._build_proposed_change(hypothesis)
        return hypothesis

    def _map_signal_to_action(
        self, signal: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any], float, str]:
        signal_type = str(signal.get("type", ""))
        examples = signal.get("examples", [])
        description = str(signal.get("description", ""))

        if signal_type == "skill_miss":
            skill_name = self._infer_skill_name(examples, fallback="auto-generated-skill")
            detail = {
                "skill_name": skill_name,
                "description": f"Auto-created to cover missed scenario: {description}",
                "key_rules": ["Focus on reproducible workflow.", "Return structured output."],
            }
            return (
                ActionType.CREATE_SKILL.value,
                detail,
                0.86,
                "Missing coverage is best addressed by a dedicated skill scaffold.",
            )

        if signal_type in {"skill_quality_low", "user_correction", "repeated_request"}:
            detail = {
                "target": "skills",
                "change": "Improve SKILL.md instructions and examples for consistency.",
                "anchors": examples[:3],
            }
            return (
                ActionType.MODIFY_SKILL_MD.value,
                detail,
                0.78,
                "Repeated correction patterns suggest instruction clarity gaps.",
            )

        if signal_type == "routing_error":
            detail = {
                "file": "AGENTS.md",
                "change": "Add or refine routing hints for correct skill selection.",
                "anchors": examples[:3],
            }
            return (
                ActionType.MODIFY_AGENTS.value,
                detail,
                0.74,
                "Routing misses imply the dispatch instruction needs tightening.",
            )

        if signal_type == "config_gap":
            detail = {
                "file": "evolution/config.yaml",
                "change": "Add missing defaults and safety constraints.",
                "anchors": examples[:3],
            }
            return (
                ActionType.MODIFY_CONFIG.value,
                detail,
                0.66,
                "Config signal indicates baseline settings are incomplete.",
            )

        if signal_type == "execution_failure":
            detail = {
                "target": "scripts",
                "change": "Add defensive checks and fallback branches.",
                "anchors": examples[:3],
            }
            return (
                ActionType.MODIFY_SKILL_SCRIPT.value,
                detail,
                0.71,
                "Execution failures usually require code-level robustness updates.",
            )

        if signal_type == "process_improvement":
            detail = {
                "name": "evolution-standing-order",
                "rule": "Run observe+reflect daily and summarize pending approvals.",
            }
            return (
                ActionType.CREATE_STANDING_ORDER.value,
                detail,
                0.75,
                "Process opportunities can be stabilized through standing orders.",
            )

        return "", {}, 0.0, "No action mapping for signal type."

    def _deduplicate(self, hypotheses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}

        for hypothesis in hypotheses:
            signature_obj = {
                "action_type": hypothesis.get("action_type"),
                "action_detail": hypothesis.get("action_detail"),
                "risk": hypothesis.get("risk"),
            }
            signature = json.dumps(signature_obj, ensure_ascii=False, sort_keys=True)

            if signature not in merged:
                merged[signature] = hypothesis
                continue

            existing = merged[signature]
            existing_refs = list(existing.get("signal_refs", []))
            for ref in hypothesis.get("signal_refs", []):
                if ref not in existing_refs:
                    existing_refs.append(ref)
            existing["signal_refs"] = existing_refs
            existing["confidence"] = round(
                max(float(existing.get("confidence", 0.0)), float(hypothesis.get("confidence", 0.0))),
                2,
            )
            existing["reasoning"] = f"{existing.get('reasoning', '')} | merged similar hypothesis"
            existing["auto_approve_eligible"] = self._is_auto_approve_eligible(
                str(existing.get("risk", "medium")), float(existing.get("confidence", 0.0))
            )

        deduped = list(merged.values())
        for idx, hypothesis in enumerate(deduped, start=1):
            hypothesis["id"] = f"H{datetime.now().strftime('%Y%m%d')}{idx:03d}"
        return deduped

    def _root_cause(self, signal_type: str) -> str:
        mapping = {
            "skill_miss": "缺少针对场景的专用能力封装。",
            "skill_quality_low": "现有指令边界不清，导致输出波动。",
            "repeated_request": "首次响应没有覆盖用户真实目标。",
            "user_correction": "关键约束未被稳定遵循。",
            "execution_failure": "脚本容错不足或前置条件未校验。",
            "routing_error": "路由规则与任务类型匹配度不足。",
            "config_gap": "配置默认值或安全阈值缺失。",
            "process_improvement": "流程存在可自动化的重复步骤。",
        }
        return mapping.get(signal_type, "信号不足以定位根因。")

    def _is_auto_approve_eligible(self, risk: str, confidence: float) -> bool:
        if risk == "critical":
            return False
        if risk == "high":
            return confidence >= 0.8
        if risk == "medium":
            return confidence >= 0.85
        if risk == "low":
            return confidence >= 0.7
        return False

    def _infer_skill_name(self, examples: Any, fallback: str) -> str:
        if not isinstance(examples, list) or not examples:
            return fallback

        first = str(examples[0]).strip().lower()
        cleaned = "".join(ch if ch.isalnum() else "-" for ch in first)
        cleaned = "-".join(part for part in cleaned.split("-") if part)
        if not cleaned:
            return fallback
        return f"{cleaned[:40]}-skill"

    def _generate_signature(self, action_type: str, action_detail: Dict[str, Any]) -> str:
        target = str(action_detail.get("file") or action_detail.get("target") or action_detail.get("name") or "global")
        change = str(action_detail.get("change") or action_detail.get("rule") or action_type)
        target_slug = self._slugify(target)
        change_slug = self._slugify(change)[:48]
        return f"{target_slug}-{change_slug}".strip("-")

    def _route_target(self, hypothesis: Dict[str, Any]) -> str:
        action_type = str(hypothesis.get("action_type", ""))
        detail = hypothesis.get("action_detail", {}) if isinstance(hypothesis.get("action_detail"), dict) else {}
        target_hint = str(detail.get("target", "")).lower()
        file_hint = str(detail.get("file", "")).lower()

        if action_type in {ActionType.MODIFY_AGENTS.value, ActionType.CREATE_STANDING_ORDER.value}:
            return "AGENTS.md"
        if action_type in {ActionType.MODIFY_MEMORY.value}:
            return "MEMORY.md"
        if action_type == ActionType.MODIFY_CONFIG.value:
            return "TOOLS.md"
        if action_type == ActionType.MODIFY_SKILL_SCRIPT.value:
            return "skills/evolution-engine/scripts/reflector.py"
        if action_type in {ActionType.CREATE_SKILL.value, ActionType.MODIFY_SKILL_MD.value}:
            return "skills/evolution-engine/SKILL.md"
        if "tool" in target_hint or "config" in file_hint:
            return "TOOLS.md"
        if "memory" in target_hint:
            return "MEMORY.md"
        return "AGENTS.md"

    def _build_proposed_change(self, hypothesis: Dict[str, Any]) -> str:
        detail = hypothesis.get("action_detail", {}) if isinstance(hypothesis.get("action_detail"), dict) else {}
        signature = str(hypothesis.get("signature", ""))
        action_type = str(hypothesis.get("action_type", ""))
        reasoning = str(hypothesis.get("reasoning", ""))
        change_text = str(detail.get("change") or detail.get("rule") or detail.get("description") or "").strip()
        if not change_text:
            change_text = f"Add durable guidance for action `{action_type}`."
        return (
            f"- [evolution] {change_text}\n"
            f"  - signature: {signature}\n"
            f"  - rationale: {reasoning}"
        )

    def _slugify(self, text: str) -> str:
        lowered = text.strip().lower()
        lowered = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", lowered)
        lowered = re.sub(r"-+", "-", lowered).strip("-")
        return lowered or "rule"

    def _trigger_type(self, hypothesis: Dict[str, Any]) -> str:
        action_type = str(hypothesis.get("action_type", ""))
        if "correction" in action_type:
            return "correction"
        if "process" in action_type or "standing_order" in action_type:
            return "workflow"
        if "memory" in action_type:
            return "preference"
        return "struggle"

    def _confidence_bucket(self, value: float) -> str:
        if value >= 0.85:
            return "high"
        if value >= 0.65:
            return "medium"
        return "low"

    def _save(self, payload: Dict[str, Any]) -> None:
        date = str(payload.get("date", datetime.now().strftime("%Y-%m-%d")))
        target = self.hypotheses_dir / f"{date}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
        LOGGER.info(f"Hypotheses saved to {target}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent.parent.parent
    reflector = Reflector(str(root))
    print(json.dumps(reflector.reflect_from_date(), ensure_ascii=False, indent=2))
