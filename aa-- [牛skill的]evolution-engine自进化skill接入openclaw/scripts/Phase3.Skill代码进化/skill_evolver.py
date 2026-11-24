#!/usr/bin/env python3
"""Skill evolution utilities for Phase 3."""

from __future__ import annotations

import difflib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eval_runner import EvalRunner
from trace_collector import TraceCollector


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent.parent.parent


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


class SkillEvolver:
    """Skill evolver: auto-create, patch, and iterative evolution."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.evolution_dir = self.workspace_root / "evolution"
        self.staging_dir = self.evolution_dir / "staging" / "skills"
        self.diff_dir = self.evolution_dir / "staging" / "patches"
        self.history_dir = self.evolution_dir / "staging" / "history"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.diff_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.eval_runner = EvalRunner(str(self.workspace_root))
        self.trace_collector = TraceCollector(str(self.workspace_root))

    def auto_create_skill(
        self,
        task_description: str,
        steps: List[str],
        pitfalls: List[str],
        tools_used: List[str],
        success_output: str,
    ) -> Dict[str, Any]:
        if not task_description.strip():
            raise ValueError("task_description is required")

        safe_name = self._slugify(task_description)
        skill_name = f"auto-{safe_name}"
        description = f"Auto-generated skill from successful task: {task_description.strip()[:120]}"

        content = self._generate_skill_content(
            name=skill_name,
            description=description,
            steps=steps,
            pitfalls=pitfalls,
            tools=tools_used,
            output_example=success_output,
        )

        staged_path = self.staging_dir / skill_name / "SKILL.md"
        _atomic_write_text(staged_path, content)

        payload = {
            "type": "create_skill",
            "skill_name": skill_name,
            "task_description": task_description,
            "staged_skill_path": str(staged_path),
            "steps_count": len(steps),
            "pitfalls_count": len(pitfalls),
            "tools_count": len(tools_used),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._append_history(payload)
        return payload

    def auto_patch_skill(
        self,
        skill_path: str,
        issue: str,
        fix: str,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        target = Path(skill_path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Skill file not found: {target}")

        content = target.read_text(encoding="utf-8")
        patch = self._compute_patch(content=content, issue=issue, fix=fix)

        old_section = str(patch["old_section"])
        new_section = str(patch["new_section"])
        if old_section and old_section in content:
            patched_content = content.replace(old_section, new_section, 1)
        else:
            patched_content = self._append_patch(content, str(patch["section_header"]), new_section)

        staged_path = self._staged_variant_path(target)
        _atomic_write_text(staged_path, patched_content)

        diff = "\n".join(
            difflib.unified_diff(
                content.splitlines(),
                patched_content.splitlines(),
                fromfile=str(target),
                tofile=str(staged_path),
                lineterm="",
            )
        )

        payload = {
            "type": "patch_skill",
            "skill_path": str(target),
            "staged_skill_path": str(staged_path),
            "trace_id": trace_id,
            "issue": issue,
            "fix": fix,
            "patch": patch,
            "diff": diff,
            "patched_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._append_history(payload)
        return payload

    def evolve_skill(self, skill_path: str, baseline_scores: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        target = Path(skill_path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Skill file not found: {target}")

        baseline = baseline_scores
        if baseline is None:
            baseline = self.eval_runner.run_baseline(skill_path=str(target), num_cases=20, judge_mode="auto")

        failures = self.trace_collector.get_traces(
            skill_name=target.parent.name,
            failure_only=True,
            limit=20,
        )
        variant_path = self._build_variant_from_failures(target, failures)

        eval_result = self.eval_runner.run_evaluation(
            skill_path=str(target),
            variant_path=str(variant_path),
            judge_mode="auto",
        )

        baseline_total = float(baseline.get("total_score", 0.0))
        variant_total = float(eval_result.get("total_score", 0.0))
        improved = variant_total > baseline_total
        gates = eval_result.get("gates", {}) if isinstance(eval_result.get("gates"), dict) else {}
        gate_passed = bool(gates.get("passed", False))

        decision = "improved" if improved and gate_passed else "no_improvement"
        payload = {
            "type": "evolve_skill",
            "skill_path": str(target),
            "variant_path": str(variant_path),
            "baseline_total": round(baseline_total, 4),
            "variant_total": round(variant_total, 4),
            "delta_total": round(variant_total - baseline_total, 4),
            "gate_passed": gate_passed,
            "decision": decision,
            "failures_used": len(failures),
            "evaluation": eval_result,
            "evolved_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._append_history(payload)
        return payload

    def _generate_skill_content(
        self,
        name: str,
        description: str,
        steps: List[str],
        pitfalls: List[str],
        tools: List[str],
        output_example: str,
    ) -> str:
        normalized_steps = [s.strip() for s in steps if str(s).strip()]
        normalized_pitfalls = [p.strip() for p in pitfalls if str(p).strip()]
        normalized_tools = [t.strip() for t in tools if str(t).strip()]

        if not normalized_steps:
            normalized_steps = ["Clarify user intent and expected output.", "Execute the core workflow safely.", "Validate output before returning."]
        if not normalized_pitfalls:
            normalized_pitfalls = ["Avoid skipping verification on final outputs.", "Do not assume missing inputs."]

        trigger_lines = [
            f"- The request matches this workflow: {description[:120]}",
            "- The task needs repeatable, multi-step execution.",
            "- The result quality can be validated with concrete checks.",
        ]

        step_lines = [f"{idx}. {text}" for idx, text in enumerate(normalized_steps, start=1)]
        pitfall_lines = [f"- {text}" for text in normalized_pitfalls]
        tools_line = ", ".join(normalized_tools) if normalized_tools else "No specific tools required"
        output = (output_example or "Output should be concise, correct, and verifiable.").strip()

        return (
            f"---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"---\n\n"
            f"# {name}\n\n"
            "## When to Use\n"
            f"{'\n'.join(trigger_lines)}\n\n"
            "## Procedure\n"
            f"{'\n'.join(step_lines)}\n\n"
            "## Pitfalls\n"
            f"{'\n'.join(pitfall_lines)}\n\n"
            "## Tools\n"
            f"- {tools_line}\n\n"
            "## Verification\n"
            "- Confirm the answer follows all procedure steps.\n"
            "- Check boundaries and failure handling are explicitly addressed.\n"
            "- Compare result with the expected output style below.\n\n"
            "## Success Output Example\n"
            "```text\n"
            f"{output[:1200]}\n"
            "```\n"
        )

    def _compute_patch(self, content: str, issue: str, fix: str) -> Dict[str, Any]:
        sections = self._extract_h2_sections(content)
        chosen_header = self._choose_section_header(list(sections.keys()), issue, fix)
        old_section = sections.get(chosen_header, "")

        if old_section:
            addition = self._render_patch_line(issue, fix)
            if chosen_header.strip().lower() == "## procedure":
                next_index = self._next_step_index(old_section)
                new_section = f"{old_section}\n{next_index}. {addition}"
            else:
                new_section = f"{old_section}\n- {addition}"
        else:
            new_section = f"{chosen_header}\n- {self._render_patch_line(issue, fix)}"

        return {
            "old_section": old_section,
            "new_section": new_section,
            "section_header": chosen_header,
        }

    def _build_variant_from_failures(self, skill_path: Path, failures: List[Dict[str, Any]]) -> Path:
        content = skill_path.read_text(encoding="utf-8")
        sections = self._extract_h2_sections(content)
        pit_header = "## Pitfalls"
        original = sections.get(pit_header, pit_header)

        notes: List[str] = []
        for item in failures[:5]:
            feedback = str(item.get("user_feedback") or "").strip()
            if feedback:
                notes.append(f"- Trace fix hint: {feedback[:160]}")

        if not notes:
            notes = ["- Trace fix hint: add clearer fallback and explicit boundary checks."]

        updated = original + "\n" + "\n".join(notes)
        if original in content:
            variant = content.replace(original, updated, 1)
        else:
            variant = content + "\n\n" + updated + "\n"

        variant_path = self._staged_variant_path(skill_path)
        _atomic_write_text(variant_path, variant)
        return variant_path

    def _staged_variant_path(self, source_path: Path) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        skill_name = source_path.parent.name
        return self.staging_dir / skill_name / f"SKILL.variant.{ts}.md"

    def _append_history(self, item: Dict[str, Any]) -> None:
        date_key = datetime.now().strftime("%Y-%m-%d")
        target = self.history_dir / f"{date_key}.json"

        payload: Dict[str, Any]
        if target.exists():
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        else:
            payload = {}

        records = payload.get("records", []) if isinstance(payload.get("records"), list) else []
        records.append(item)
        payload["date"] = date_key
        payload["records"] = records
        _atomic_write_text(target, json.dumps(payload, ensure_ascii=False, indent=2))

    def _extract_h2_sections(self, content: str) -> Dict[str, str]:
        lines = content.splitlines()
        spans: List[Tuple[str, int, int]] = []
        current_header: Optional[str] = None
        start_idx = 0

        for idx, line in enumerate(lines):
            if line.startswith("## "):
                if current_header is not None:
                    spans.append((current_header, start_idx, idx))
                current_header = line.strip()
                start_idx = idx
        if current_header is not None:
            spans.append((current_header, start_idx, len(lines)))

        sections: Dict[str, str] = {}
        for header, start, end in spans:
            sections[header] = "\n".join(lines[start:end]).rstrip()
        return sections

    def _choose_section_header(self, headers: List[str], issue: str, fix: str) -> str:
        text = f"{issue} {fix}".lower()
        rules = [
            ("procedure", "## Procedure"),
            ("步骤", "## Procedure"),
            ("流程", "## Procedure"),
            ("pitfall", "## Pitfalls"),
            ("风险", "## Pitfalls"),
            ("warning", "## Pitfalls"),
            ("verify", "## Verification"),
            ("校验", "## Verification"),
        ]
        for keyword, target in rules:
            if keyword in text and target in headers:
                return target

        for preferred in ["## Procedure", "## Pitfalls", "## Verification"]:
            if preferred in headers:
                return preferred
        return "## Procedure"

    def _render_patch_line(self, issue: str, fix: str) -> str:
        issue_text = issue.strip() or "identified issue"
        fix_text = fix.strip() or "apply safe fallback"
        return f"Fix for '{issue_text}': {fix_text}."

    def _next_step_index(self, section_text: str) -> int:
        indices = [int(m.group(1)) for m in re.finditer(r"^\s*(\d+)\.\s", section_text, flags=re.M)]
        return (max(indices) + 1) if indices else 1

    def _append_patch(self, content: str, header: str, section: str) -> str:
        if content.endswith("\n"):
            return content + "\n" + section + "\n"
        return content + "\n\n" + section + "\n"

    def _slugify(self, text: str) -> str:
        lowered = text.lower().strip()
        lowered = re.sub(r"[^a-z0-9\u4e00-\u9fff\-\s_]", "", lowered)
        lowered = lowered.replace("_", "-")
        lowered = re.sub(r"\s+", "-", lowered)
        lowered = re.sub(r"-+", "-", lowered).strip("-")
        return lowered[:48] or "skill"


def _build_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="Skill evolver")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--task", required=True)
    create.add_argument("--steps", required=True)
    create.add_argument("--pitfalls", default="[]")
    create.add_argument("--tools", default="[]")
    create.add_argument("--success-output", default="")

    patch = sub.add_parser("patch")
    patch.add_argument("--skill-path", required=True)
    patch.add_argument("--issue", required=True)
    patch.add_argument("--fix", required=True)
    patch.add_argument("--trace-id", default=None)

    evolve = sub.add_parser("evolve")
    evolve.add_argument("--skill-path", required=True)

    return parser


def _parse_list(value: str) -> List[str]:
    raw = value.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except Exception:
        pass
    return [x.strip() for x in raw.split("|") if x.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    evolver = SkillEvolver(str(WORKSPACE_ROOT))

    if args.command == "create":
        result = evolver.auto_create_skill(
            task_description=args.task,
            steps=_parse_list(args.steps),
            pitfalls=_parse_list(args.pitfalls),
            tools_used=_parse_list(args.tools),
            success_output=args.success_output,
        )
    elif args.command == "patch":
        result = evolver.auto_patch_skill(
            skill_path=args.skill_path,
            issue=args.issue,
            fix=args.fix,
            trace_id=args.trace_id,
        )
    else:
        result = evolver.evolve_skill(skill_path=args.skill_path)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
