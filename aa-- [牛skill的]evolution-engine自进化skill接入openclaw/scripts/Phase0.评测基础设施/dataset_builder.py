#!/usr/bin/env python3
"""Synthetic evaluation dataset builder for SKILL.md."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent.parent.parent


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


class DatasetBuilder:
    """Generate synthetic evaluation dataset from SKILL.md."""

    def __init__(self, skill_path: str):
        self.skill_path = Path(skill_path).resolve()
        self.skill_content = self._read_skill()

    def generate_dataset(
        self,
        num_cases: int = 20,
        output_path: Optional[str] = None,
        seed: int = 42,
    ) -> Dict[str, Any]:
        if num_cases <= 0:
            raise ValueError("num_cases must be > 0")

        skill_info = self._parse_skill()
        cases = self._generate_cases(skill_info, num_cases)
        split = self._split_dataset(cases, seed)

        payload: Dict[str, Any] = {
            "skill_name": skill_info.get("name") or self.skill_path.parent.name,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "skill_path": str(self.skill_path),
            "total_cases": len(cases),
            "splits": split,
            "cases": cases,
        }

        if output_path:
            output = Path(output_path).resolve()
        else:
            output = WORKSPACE_ROOT / "evolution" / "eval" / "datasets" / f"{payload['skill_name']}.json"

        _atomic_write_json(output, payload)
        payload["saved_to"] = str(output)
        return payload

    def load_dataset(self, path: str) -> Dict[str, Any]:
        target = Path(path).resolve()
        return json.loads(target.read_text(encoding="utf-8"))

    def _read_skill(self) -> str:
        if not self.skill_path.exists():
            raise FileNotFoundError(f"Skill file not found: {self.skill_path}")
        return self.skill_path.read_text(encoding="utf-8")

    def _parse_skill(self) -> Dict[str, Any]:
        text = self.skill_content
        lines = text.splitlines()

        frontmatter: Dict[str, str] = {}
        if lines and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                line = lines[i]
                if line.strip() == "---":
                    break
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                frontmatter[key.strip()] = value.strip()

        sections = self._extract_sections(text)
        name = frontmatter.get("name") or self.skill_path.parent.name
        description = frontmatter.get("description") or ""

        return {
            "name": name,
            "description": description,
            "frontmatter": frontmatter,
            "sections": sections,
            "source_path": str(self.skill_path),
        }

    def _extract_sections(self, text: str) -> Dict[str, str]:
        sections: Dict[str, List[str]] = {}
        current = "body"
        sections[current] = []

        for line in text.splitlines():
            if line.startswith("#"):
                current = re.sub(r"^#+\s*", "", line).strip().lower() or "body"
                sections.setdefault(current, [])
                continue
            sections.setdefault(current, []).append(line)

        return {name: "\n".join(content).strip() for name, content in sections.items()}

    def _generate_cases(self, skill_info: Dict[str, Any], n: int) -> List[Dict[str, Any]]:
        name = str(skill_info.get("name", "skill"))
        description = str(skill_info.get("description", "")).strip()
        sections = skill_info.get("sections", {}) if isinstance(skill_info.get("sections"), dict) else {}

        when_text = self._find_section_text(sections, ["when to use", "use", "trigger", "primary", "weather"])
        procedure_text = self._find_section_text(sections, ["procedure", "steps", "workflow", "wttr", "fallback"])
        pitfalls_text = self._find_section_text(sections, ["pitfalls", "tips", "warning", "boundary", "fallback"])

        description_hint = description if description else f"Use the {name} skill correctly."

        templates = {
            "trigger_positive": [
                (
                    "用户想用{name}解决问题：{hint}",
                    "应识别该请求匹配 {name}，并按 skill 指令给出可执行结果。",
                ),
                (
                    "请用{name}处理：{when}",
                    "应触发 {name} 的核心能力，并输出面向用户的结果。",
                ),
            ],
            "procedure": [
                (
                    "请按照步骤完成：{proc}",
                    "应按技能流程执行，先说明步骤，再给出最终结果。",
                ),
                (
                    "执行这个任务并解释过程：{proc}",
                    "应体现流程完整性，关键步骤不可省略。",
                ),
            ],
            "boundary": [
                (
                    "边界场景：{pit}",
                    "应稳健处理异常或边界条件，不编造信息。",
                ),
                (
                    "当条件不充分时该怎么做？{pit}",
                    "应说明限制并给出安全的替代方案。",
                ),
            ],
            "negative": [
                (
                    "这个请求和{name}无关，要求写一首诗。",
                    "不应误触发 {name}，应明确不适用并建议合适路径。",
                ),
                (
                    "用户请求与{name}完全无关：修理机械硬盘。",
                    "应判断不匹配，不强行套用技能流程。",
                ),
            ],
        }

        categories = ["trigger_positive", "procedure", "boundary", "negative"]
        pool: List[Dict[str, Any]] = []
        idx = 1

        while len(pool) < max(n * 2, 12):
            category = categories[(idx - 1) % len(categories)]
            variants = templates[category]
            template_input, template_expected = variants[(idx - 1) % len(variants)]
            rendered_input = template_input.format(
                name=name,
                hint=description_hint,
                when=when_text or description_hint,
                proc=procedure_text or description_hint,
                pit=pitfalls_text or "请避免风险并明确边界",
            )
            rendered_expected = template_expected.format(name=name)
            difficulty = self._difficulty_for_case(category, idx)

            pool.append(
                {
                    "id": f"TC{idx:03d}",
                    "task_input": self._clean_text(rendered_input),
                    "expected_behavior": self._clean_text(rendered_expected),
                    "category": category,
                    "difficulty": difficulty,
                    "source": "synthetic",
                }
            )
            idx += 1

        return pool[:n]

    def _find_section_text(self, sections: Dict[str, str], keys: List[str]) -> str:
        for section_name, content in sections.items():
            lowered = section_name.lower()
            if any(key in lowered for key in keys):
                return self._first_meaningful_sentence(content)
        return ""

    def _first_meaningful_sentence(self, text: str) -> str:
        cleaned = self._clean_text(text)
        parts = re.split(r"[。！？.!?]\s*", cleaned)
        for part in parts:
            if len(part.strip()) >= 10:
                return part.strip()
        return cleaned[:120]

    def _clean_text(self, text: str) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        return compact[:300]

    def _difficulty_for_case(self, category: str, index: int) -> str:
        if category == "negative":
            return "medium" if index % 2 == 0 else "easy"
        if category == "boundary":
            return "hard" if index % 3 == 0 else "medium"
        if category == "procedure":
            return "medium"
        return "easy"

    def _split_dataset(self, cases: List[Dict[str, Any]], seed: int) -> Dict[str, List[str]]:
        case_ids = [str(item.get("id")) for item in cases]
        rng = random.Random(seed)
        rng.shuffle(case_ids)

        total = len(case_ids)
        train_n = max(1, int(total * 0.6))
        val_n = max(1, int(total * 0.2))
        if train_n + val_n >= total:
            val_n = max(1, total - train_n - 1)
        holdout_n = max(1, total - train_n - val_n)

        train = case_ids[:train_n]
        val = case_ids[train_n : train_n + val_n]
        holdout = case_ids[train_n + val_n : train_n + val_n + holdout_n]

        if not holdout:
            holdout = case_ids[-1:]
            if holdout and holdout[0] in train:
                train.remove(holdout[0])

        return {"train": train, "val": val, "holdout": holdout}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build synthetic evaluation dataset from SKILL.md")
    parser.add_argument("--skill-path", required=True)
    parser.add_argument("--num-cases", type=int, default=20)
    parser.add_argument("--output", default=None)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    builder = DatasetBuilder(args.skill_path)
    payload = builder.generate_dataset(num_cases=args.num_cases, output_path=args.output, seed=args.seed)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
