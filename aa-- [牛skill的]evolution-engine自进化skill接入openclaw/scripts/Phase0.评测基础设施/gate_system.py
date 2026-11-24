#!/usr/bin/env python3
"""Three-gate system: constraint, regression, safety."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class GateSystem:
    """Three-gate policy for release decisions."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or self._default_config()

    def run_all_gates(
        self,
        variant_content: str,
        baseline_content: str,
        variant_scores: Dict[str, Any],
        baseline_scores: Dict[str, Any],
        target_type: str = "skill",
    ) -> Dict[str, Any]:
        results = {
            "constraint": self.constraint_gate(variant_content, target_type),
            "regression": self.regression_gate(variant_scores, baseline_scores),
            "safety": self.safety_gate(variant_content, baseline_content, target_type),
        }

        all_passed = all(bool(item.get("passed", False)) for item in results.values())
        recommendation = "approve" if all_passed else "reject"
        return {
            "passed": all_passed,
            "gates": results,
            "recommendation": recommendation,
        }

    def constraint_gate(self, content: str, target_type: str) -> Dict[str, Any]:
        errors: List[str] = []

        if not content.strip():
            errors.append("content is empty")

        content_size = len(content.encode("utf-8"))
        size_limit = int(self.config.get("skill_max_bytes", 15 * 1024))
        if target_type == "skill" and content_size > size_limit:
            errors.append(f"skill exceeds size limit ({content_size} > {size_limit})")

        if target_type == "skill":
            frontmatter = self._parse_frontmatter(content)
            if not frontmatter.get("name"):
                errors.append("frontmatter missing name")
            if not frontmatter.get("description"):
                errors.append("frontmatter missing description")
            description = str(frontmatter.get("description", ""))
            if len(description) > int(self.config.get("description_max_chars", 1024)):
                errors.append("description exceeds 1024 chars")

        if "\x00" in content:
            errors.append("contains null bytes")

        return {
            "passed": len(errors) == 0,
            "details": {
                "target_type": target_type,
                "content_bytes": content_size,
                "errors": errors,
            },
        }

    def regression_gate(
        self,
        variant_scores: Dict[str, Any],
        baseline_scores: Dict[str, Any],
        tolerance: float = 0.02,
    ) -> Dict[str, Any]:
        if not baseline_scores:
            return {
                "passed": True,
                "details": {
                    "reason": "no baseline found; first run pass",
                    "tolerance": tolerance,
                },
            }

        threshold = float(self.config.get("regression_tolerance", tolerance))

        variant_total = float(variant_scores.get("total_score", 0.0))
        baseline_total = float(baseline_scores.get("total_score", 0.0))
        delta_total = variant_total - baseline_total

        total_pass = delta_total >= -threshold

        variant_dims = variant_scores.get("dimensions", {}) if isinstance(variant_scores.get("dimensions"), dict) else {}
        baseline_dims = baseline_scores.get("dimensions", {}) if isinstance(baseline_scores.get("dimensions"), dict) else {}

        dim_regression_limit = float(self.config.get("dimension_regression_limit", 0.05))
        dimension_failures: Dict[str, float] = {}
        for name, base_value in baseline_dims.items():
            base = float(base_value)
            current = float(variant_dims.get(name, 0.0))
            diff = current - base
            if diff < -dim_regression_limit:
                dimension_failures[name] = round(diff, 4)

        passed = total_pass and not dimension_failures
        return {
            "passed": passed,
            "details": {
                "baseline_total": baseline_total,
                "variant_total": variant_total,
                "delta_total": round(delta_total, 4),
                "tolerance": threshold,
                "dimension_failures": dimension_failures,
            },
        }

    def safety_gate(self, variant_content: str, baseline_content: str, target_type: str = "skill") -> Dict[str, Any]:
        failures: List[str] = []
        lowered = variant_content.lower()

        for pattern in self.config.get("dangerous_patterns", []):
            if str(pattern).lower() in lowered:
                failures.append(f"dangerous pattern detected: {pattern}")

        for pattern in self.config.get("secret_patterns", []):
            if re.search(pattern, variant_content, flags=re.I):
                failures.append("possible credential leakage")
                break

        freeze_marker = str(self.config.get("freeze_marker", "evolution:freeze"))
        if freeze_marker in baseline_content and freeze_marker not in variant_content:
            failures.append("frozen content removed")

        if target_type == "python":
            try:
                ast.parse(variant_content)
            except SyntaxError as exc:
                failures.append(f"python syntax error: {exc}")

        base_frontmatter = self._parse_frontmatter(baseline_content)
        var_frontmatter = self._parse_frontmatter(variant_content)
        if base_frontmatter and var_frontmatter:
            if base_frontmatter.get("name") != var_frontmatter.get("name"):
                failures.append("name changed from baseline")
            if base_frontmatter.get("description") != var_frontmatter.get("description"):
                failures.append("description changed from baseline")

        return {
            "passed": len(failures) == 0,
            "details": {
                "target_type": target_type,
                "failures": failures,
            },
        }

    def _default_config(self) -> Dict[str, Any]:
        return {
            "skill_max_bytes": 15 * 1024,
            "description_max_chars": 1024,
            "regression_tolerance": 0.02,
            "dimension_regression_limit": 0.05,
            "freeze_marker": "evolution:freeze",
            "dangerous_patterns": [
                "rm -rf",
                "os.system(",
                "subprocess.Popen",
                "eval(",
                "exec(",
            ],
            "secret_patterns": [
                r"api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}",
                r"token\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}",
                r"password\s*[:=]\s*['\"].+['\"]",
            ],
        }

    def _parse_frontmatter(self, content: str) -> Dict[str, str]:
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}

        data: Dict[str, str] = {}
        for i in range(1, len(lines)):
            line = lines[i]
            if line.strip() == "---":
                break
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
        return data


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run gate checks")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check")
    check.add_argument("--variant", required=True)
    check.add_argument("--baseline", required=True)
    check.add_argument("--scores", required=True)
    check.add_argument("--baseline-scores", default=None)
    check.add_argument("--target-type", default="skill", choices=["skill", "prompt", "config", "python"])

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command != "check":
        return 1

    variant_content = Path(args.variant).read_text(encoding="utf-8")
    baseline_content = Path(args.baseline).read_text(encoding="utf-8")
    variant_scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    baseline_scores: Dict[str, Any] = {}
    if args.baseline_scores:
        baseline_scores = json.loads(Path(args.baseline_scores).read_text(encoding="utf-8"))

    gate = GateSystem()
    result = gate.run_all_gates(
        variant_content=variant_content,
        baseline_content=baseline_content,
        variant_scores=variant_scores,
        baseline_scores=baseline_scores,
        target_type=args.target_type,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
