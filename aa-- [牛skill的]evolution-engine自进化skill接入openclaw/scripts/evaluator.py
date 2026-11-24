#!/usr/bin/env python3
"""Evaluate staged mutations for safety and correctness."""

from __future__ import annotations

import ast
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set


DANGEROUS_PATTERNS = [
    "rm -rf",
    "os.remove",
    "shutil.rmtree",
    "subprocess.call",
    "subprocess.Popen",
    "os.system",
    "requests.post",
    "urllib.request",
    "__import__(",
    "eval(",
    "exec(",
    "open('/etc",
    "open(\"/etc",
    "open('~/.ssh",
    "open(\"~/.ssh",
]


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("evaluator")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = _setup_logger()


class Evaluator:
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.evolution_dir = self.workspace_root / "evolution"
        self.mutations_dir = self.evolution_dir / "mutations"
        self.evaluations_dir = self.evolution_dir / "evaluations"
        self.evaluations_dir.mkdir(parents=True, exist_ok=True)

    def evaluate(self, mutation: Dict[str, Any]) -> Dict[str, Any]:
        checks = {
            "syntax": self._check_syntax(mutation),
            "structure": self._check_structure(mutation),
            "security": self._check_security(mutation),
            "size": self._check_size(mutation),
            "regression": self._check_regression(mutation),
        }

        all_passed = all(bool(item.get("passed", False)) for item in checks.values())
        evaluation = {
            "mutation_id": mutation.get("id"),
            "checks": checks,
            "overall": "pass" if all_passed else "fail",
            "recommendation": self._recommend(checks),
            "evaluated_at": datetime.now().isoformat(),
        }
        self._save_evaluation(evaluation)
        return evaluation

    def evaluate_by_mutation_id(self, mutation_id: str) -> Dict[str, Any]:
        mutation_path = self.mutations_dir / f"{mutation_id}.json"
        if not mutation_path.exists():
            raise FileNotFoundError(f"Mutation not found: {mutation_id}")
        mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
        return self.evaluate(mutation)

    def _iter_file_infos(self, mutation: Dict[str, Any]) -> List[Dict[str, Any]]:
        files: List[Dict[str, Any]] = []
        for key in ["files_created", "files_modified"]:
            entries = mutation.get(key, [])
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict):
                        files.append(entry)
        return files

    def _check_syntax(self, mutation: Dict[str, Any]) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []
        for info in self._iter_file_infos(mutation):
            file_path = Path(str(info.get("staging_path", "")))
            if not file_path.exists():
                details.append({"file": str(file_path), "passed": False, "error": "staging file missing"})
                continue

            suffix = file_path.suffix.lower()
            if suffix == ".py":
                try:
                    ast.parse(file_path.read_text(encoding="utf-8"))
                    details.append({"file": str(file_path), "passed": True})
                except SyntaxError as exc:
                    details.append({"file": str(file_path), "passed": False, "error": str(exc)})
                continue

            if suffix == ".json":
                try:
                    json.loads(file_path.read_text(encoding="utf-8"))
                    details.append({"file": str(file_path), "passed": True})
                except Exception as exc:
                    details.append({"file": str(file_path), "passed": False, "error": str(exc)})
                continue

            if suffix in {".yaml", ".yml"}:
                valid, error = self._basic_yaml_check(file_path.read_text(encoding="utf-8"))
                details.append({"file": str(file_path), "passed": valid, "error": error})
                continue

            details.append({"file": str(file_path), "passed": True})

        passed = all(bool(item.get("passed", False)) for item in details) if details else True
        return {"passed": passed, "details": details}

    def _check_structure(self, mutation: Dict[str, Any]) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []
        for info in self._iter_file_infos(mutation):
            staging = Path(str(info.get("staging_path", "")))
            target = Path(str(info.get("target_path", "")))
            if not staging.exists():
                details.append({"file": str(staging), "passed": False, "error": "missing staging file"})
                continue

            size = staging.stat().st_size
            if size <= 100:
                details.append({"file": str(staging), "passed": False, "error": "file too small (<100 bytes)"})
                continue

            if target.name == "SKILL.md":
                content = staging.read_text(encoding="utf-8")
                if not content.lstrip().startswith("---"):
                    details.append({"file": str(staging), "passed": False, "error": "missing frontmatter"})
                    continue

            details.append({"file": str(staging), "passed": True})

        passed = all(bool(item.get("passed", False)) for item in details) if details else True
        return {"passed": passed, "details": details}

    def _check_security(self, mutation: Dict[str, Any]) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []
        for info in self._iter_file_infos(mutation):
            staging = Path(str(info.get("staging_path", "")))
            if not staging.exists():
                details.append({"file": str(staging), "passed": False, "error": "missing staging file"})
                continue

            text = staging.read_text(encoding="utf-8", errors="ignore")
            found: List[str] = []
            lowered = text.lower()
            for pattern in DANGEROUS_PATTERNS:
                if pattern.lower() in lowered:
                    found.append(pattern)

            if found:
                details.append(
                    {
                        "file": str(staging),
                        "passed": False,
                        "error": f"dangerous patterns: {', '.join(found)}",
                    }
                )
            else:
                details.append({"file": str(staging), "passed": True})

        passed = all(bool(item.get("passed", False)) for item in details) if details else True
        return {"passed": passed, "details": details}

    def _check_size(self, mutation: Dict[str, Any]) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []
        total = 0

        for info in self._iter_file_infos(mutation):
            staging = Path(str(info.get("staging_path", "")))
            if not staging.exists():
                details.append({"file": str(staging), "passed": False, "error": "missing staging file"})
                continue

            size = staging.stat().st_size
            total += size
            if size > 500 * 1024:
                details.append({"file": str(staging), "passed": False, "error": "file exceeds 500KB"})
            else:
                details.append({"file": str(staging), "passed": True, "size": size})

        total_passed = total <= 1024 * 1024
        if not total_passed:
            details.append({"file": "<total>", "passed": False, "error": "total mutation exceeds 1MB"})

        passed = total_passed and all(bool(item.get("passed", False)) for item in details)
        return {"passed": passed, "total_bytes": total, "details": details}

    def _check_regression(self, mutation: Dict[str, Any]) -> Dict[str, Any]:
        details: List[Dict[str, Any]] = []

        for info in self._iter_file_infos(mutation):
            staging = Path(str(info.get("staging_path", "")))
            target = Path(str(info.get("target_path", "")))
            if not staging.exists() or not target.suffix == ".py":
                details.append({"file": str(staging), "passed": True})
                continue

            try:
                staged_defs = self._function_defs(staging.read_text(encoding="utf-8"))
                target_defs = self._function_defs(target.read_text(encoding="utf-8")) if target.exists() else set()
                removed = sorted(target_defs - staged_defs)
                if removed:
                    details.append(
                        {
                            "file": str(staging),
                            "passed": False,
                            "error": f"potential regression, removed functions: {', '.join(removed)}",
                        }
                    )
                else:
                    details.append({"file": str(staging), "passed": True})
            except Exception as exc:
                details.append({"file": str(staging), "passed": False, "error": str(exc)})

        passed = all(bool(item.get("passed", False)) for item in details) if details else True
        return {"passed": passed, "details": details}

    def _recommend(self, checks: Dict[str, Dict[str, Any]]) -> str:
        failed = [name for name, result in checks.items() if not result.get("passed", False)]
        if not failed:
            return "approve"
        if "security" in failed:
            return "reject"
        if "syntax" in failed:
            return "fix_syntax_then_retry"
        return f"manual_review_required: {', '.join(failed)}"

    def _save_evaluation(self, evaluation: Dict[str, Any]) -> None:
        mutation_id = str(evaluation.get("mutation_id", "unknown"))
        by_id = self.evaluations_dir / f"{mutation_id}.json"
        self._atomic_write_text(by_id, json.dumps(evaluation, ensure_ascii=False, indent=2))

        today = datetime.now().strftime("%Y-%m-%d")
        by_day = self.evaluations_dir / f"{today}.json"
        if by_day.exists():
            payload = json.loads(by_day.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {"date": today, "evaluations": []}
        else:
            payload = {"date": today, "evaluations": []}

        evaluations = payload.get("evaluations", [])
        if not isinstance(evaluations, list):
            evaluations = []
        evaluations.append(evaluation)
        payload["evaluations"] = evaluations
        self._atomic_write_text(by_day, json.dumps(payload, ensure_ascii=False, indent=2))
        LOGGER.info(f"Evaluation saved for mutation {mutation_id}")

    def _atomic_write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)

    def _function_defs(self, source: str) -> Set[str]:
        tree = ast.parse(source)
        names: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                names.add(node.name)
        return names

    def _basic_yaml_check(self, text: str) -> tuple[bool, str]:
        lines = text.splitlines()
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            if ":" not in stripped:
                return False, f"line {idx} missing ':' separator"
        return True, ""


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent.parent.parent
    evaluator = Evaluator(str(root))
    print(json.dumps({"ok": True, "message": "Use evaluate_by_mutation_id from CLI."}, ensure_ascii=False, indent=2))
