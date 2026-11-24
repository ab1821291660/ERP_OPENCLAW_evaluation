#!/usr/bin/env python3
"""Rule-based prompt variant testing."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional


class PromptTester:
    """测试 prompt 变体的行为变化"""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()

    def test_variant(
        self,
        target_file: str,
        variant_path: str,
        test_scenarios: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        baseline_path = self.workspace_root / target_file
        variant_file = Path(variant_path).resolve()
        if not baseline_path.exists():
            raise FileNotFoundError(f"Baseline file not found: {baseline_path}")
        if not variant_file.exists():
            raise FileNotFoundError(f"Variant file not found: {variant_file}")

        baseline = baseline_path.read_text(encoding="utf-8")
        variant = variant_file.read_text(encoding="utf-8")

        scenarios = test_scenarios or self._generate_scenarios(baseline)
        if not scenarios:
            scenarios = [
                {
                    "id": "S001",
                    "name": "general_instruction_following",
                    "tags": ["general"],
                    "prompt": "执行规则时保持可操作性和边界清晰。",
                }
            ]

        baseline_per = self._score_document(baseline, scenarios)
        variant_per = self._score_document(variant, scenarios)
        baseline_avg = round(mean(item["score"] for item in baseline_per), 4)
        variant_avg = round(mean(item["score"] for item in variant_per), 4)

        deltas: List[Dict[str, Any]] = []
        regressions = 0
        improvements = 0
        for base_item, var_item in zip(baseline_per, variant_per):
            delta = round(var_item["score"] - base_item["score"], 4)
            if delta < -0.05:
                regressions += 1
            if delta > 0.05:
                improvements += 1
            deltas.append(
                {
                    "scenario_id": base_item["scenario_id"],
                    "baseline": base_item["score"],
                    "variant": var_item["score"],
                    "delta": delta,
                }
            )

        return {
            "target_file": target_file,
            "variant_path": str(variant_file),
            "num_scenarios": len(scenarios),
            "baseline_scores": {
                "average": baseline_avg,
                "per_scenario": baseline_per,
            },
            "variant_scores": {
                "average": variant_avg,
                "per_scenario": variant_per,
            },
            "delta": {
                "average_delta": round(variant_avg - baseline_avg, 4),
                "improved_scenarios": improvements,
                "regressed_scenarios": regressions,
                "per_scenario": deltas,
            },
            "regression_detected": regressions > 0 and variant_avg < baseline_avg,
        }

    def _generate_scenarios(self, content: str) -> List[Dict[str, Any]]:
        scenarios: List[Dict[str, Any]] = []
        idx = 1

        low = content.lower()
        if "群聊规则" in content:
            scenarios.append(
                {
                    "id": f"S{idx:03d}",
                    "name": "group_chat_without_ping",
                    "prompt": "群聊里大家闲聊，没有人@你。",
                    "tags": ["group_chat", "silence"],
                    "expected": "保持静默",
                }
            )
            idx += 1
            scenarios.append(
                {
                    "id": f"S{idx:03d}",
                    "name": "group_chat_with_ping",
                    "prompt": "群聊里有人@你并明确提问。",
                    "tags": ["group_chat", "respond"],
                    "expected": "应回复",
                }
            )
            idx += 1

        if "heartbeat" in low:
            scenarios.append(
                {
                    "id": f"S{idx:03d}",
                    "name": "heartbeat_noise_control",
                    "prompt": "短时间内无新信息，是否连续发HEARTBEAT_OK。",
                    "tags": ["heartbeat", "rate_limit"],
                    "expected": "不应刷屏",
                }
            )
            idx += 1

        if "web_search" in low or "web tools" in low:
            scenarios.append(
                {
                    "id": f"S{idx:03d}",
                    "name": "web_search_failure_path",
                    "prompt": "web_search失败时处理顺序。",
                    "tags": ["web_tools", "fallback_order"],
                    "expected": "先opencli再browser",
                }
            )
            idx += 1

        if "session启动" in content:
            scenarios.append(
                {
                    "id": f"S{idx:03d}",
                    "name": "session_bootstrap",
                    "prompt": "新会话启动时应加载关键上下文文件。",
                    "tags": ["session"],
                    "expected": "读取SOUL/USER/近期memory",
                }
            )

        return scenarios

    def _score_document(self, content: str, scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        low = content.lower()
        scores: List[Dict[str, Any]] = []
        for scenario in scenarios:
            tags = scenario.get("tags", [])
            if "group_chat" in tags and "silence" in tags:
                score = self._binary_score(
                    "有价值时说话" in content and ("闲聊时沉默" in content or "保持静默" in content)
                )
            elif "group_chat" in tags and "respond" in tags:
                score = self._binary_score("@" in content or "明确求助" in content or "被@" in content)
            elif "heartbeat" in tags:
                score = self._binary_score("不要每次都 HEARTBEAT_OK" in content and ("每天2-4次" in content))
            elif "web_tools" in tags:
                has_order = "opencli" in low and "browser" in low
                score = self._binary_score(has_order)
            elif "session" in tags:
                has_session = ("SOUL.md" in content) and ("USER.md" in content) and ("memory/" in content)
                score = self._binary_score(has_session)
            else:
                score = 0.5

            # Reward explicit evolution patches only when they are concise and actionable.
            if "<!-- evolution:patch:start -->" in content and "触发条件" in content:
                score = min(1.0, score + 0.1)

            scores.append(
                {
                    "scenario_id": scenario.get("id", "S000"),
                    "score": round(score, 4),
                    "expected": scenario.get("expected", ""),
                }
            )
        return scores

    def _binary_score(self, ok: bool) -> float:
        return 1.0 if ok else 0.0


def load_scenarios(path: str) -> List[Dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("scenarios"), list):
        return payload["scenarios"]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError(f"Unsupported scenarios payload: {path}")
