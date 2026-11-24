#!/usr/bin/env python3
"""Evaluation runner orchestrating dataset, scoring, and gates."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dataset_builder import DatasetBuilder
from gate_system import GateSystem
from llm_judge import LLMJudge


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent.parent.parent


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


class EvalRunner:
    """Evaluation runner."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.eval_dir = self.workspace_root / "evolution" / "eval"
        self.datasets_dir = self.eval_dir / "datasets"
        self.baselines_dir = self.eval_dir / "baselines"
        self.runs_dir = self.eval_dir / "runs"
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_baseline(
        self,
        skill_path: str,
        num_cases: int = 20,
        judge_mode: str = "auto",
    ) -> Dict[str, Any]:
        skill_file = Path(skill_path).resolve()
        skill_name = skill_file.parent.name

        dataset_path = self.datasets_dir / f"{skill_name}.json"
        builder = DatasetBuilder(str(skill_file))
        dataset = builder.generate_dataset(num_cases=num_cases, output_path=str(dataset_path))

        skill_content = skill_file.read_text(encoding="utf-8")
        outputs = self._simulate_outputs(skill_content, dataset.get("cases", []))

        judge = LLMJudge(mode=judge_mode)
        scores = judge.score_batch(cases=dataset.get("cases", []), outputs=outputs)

        baseline_record = {
            "skill_name": skill_name,
            "skill_path": str(skill_file),
            "dataset_path": str(dataset_path),
            "num_cases": len(dataset.get("cases", [])),
            "judge_mode": judge.mode,
            "total_score": scores.get("total_score", 0.0),
            "dimensions": scores.get("dimensions", {}),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

        baseline_path = self.baselines_dir / f"{skill_name}_baseline.json"
        _atomic_write_json(baseline_path, baseline_record)

        run_payload = {
            "run_type": "baseline",
            "skill_name": skill_name,
            "skill_path": str(skill_file),
            "dataset": dataset,
            "outputs": outputs,
            "scores": scores,
            "saved_baseline": str(baseline_path),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        run_path = self.runs_dir / f"baseline_{skill_name}_{self._ts()}.json"
        _atomic_write_json(run_path, run_payload)

        return {
            "skill_name": skill_name,
            "total_score": baseline_record["total_score"],
            "dimensions": baseline_record["dimensions"],
            "num_cases": baseline_record["num_cases"],
            "judge_mode": judge.mode,
            "saved_to": str(baseline_path),
            "run_saved_to": str(run_path),
        }

    def run_evaluation(
        self,
        skill_path: str,
        variant_path: str,
        dataset_path: Optional[str] = None,
        baseline_path: Optional[str] = None,
        judge_mode: str = "auto",
    ) -> Dict[str, Any]:
        skill_file = Path(skill_path).resolve()
        variant_file = Path(variant_path).resolve()
        skill_name = skill_file.parent.name

        baseline_file = Path(baseline_path).resolve() if baseline_path else self.baselines_dir / f"{skill_name}_baseline.json"
        baseline_record = json.loads(baseline_file.read_text(encoding="utf-8")) if baseline_file.exists() else {}

        if dataset_path:
            ds_path = Path(dataset_path).resolve()
            dataset = json.loads(ds_path.read_text(encoding="utf-8"))
        elif baseline_record.get("dataset_path"):
            ds_path = Path(str(baseline_record["dataset_path"])).resolve()
            dataset = json.loads(ds_path.read_text(encoding="utf-8"))
        else:
            ds_path = self.datasets_dir / f"{skill_name}.json"
            dataset = DatasetBuilder(str(skill_file)).generate_dataset(num_cases=20, output_path=str(ds_path))

        variant_content = variant_file.read_text(encoding="utf-8")
        baseline_content = skill_file.read_text(encoding="utf-8")

        outputs = self._simulate_outputs(variant_content, dataset.get("cases", []))
        judge = LLMJudge(mode=judge_mode)
        variant_scores = judge.score_batch(cases=dataset.get("cases", []), outputs=outputs, baseline_scores=baseline_record)

        gate = GateSystem()
        gates = gate.run_all_gates(
            variant_content=variant_content,
            baseline_content=baseline_content,
            variant_scores=variant_scores,
            baseline_scores=baseline_record,
            target_type=self._target_type_for(variant_file),
        )

        run_payload = {
            "run_type": "variant",
            "skill_name": skill_name,
            "skill_path": str(skill_file),
            "variant_path": str(variant_file),
            "dataset_path": str(ds_path),
            "judge_mode": judge.mode,
            "scores": variant_scores,
            "gates": gates,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        run_path = self.runs_dir / f"variant_{skill_name}_{self._ts()}.json"
        _atomic_write_json(run_path, run_payload)

        return {
            "skill_name": skill_name,
            "variant_path": str(variant_file),
            "total_score": variant_scores.get("total_score", 0.0),
            "dimensions": variant_scores.get("dimensions", {}),
            "gates": gates,
            "judge_mode": judge.mode,
            "saved_to": str(run_path),
        }

    def compare_runs(self, run_a_path: str, run_b_path: str) -> Dict[str, Any]:
        run_a = json.loads(Path(run_a_path).read_text(encoding="utf-8"))
        run_b = json.loads(Path(run_b_path).read_text(encoding="utf-8"))

        score_a = float(run_a.get("scores", {}).get("total_score", 0.0))
        score_b = float(run_b.get("scores", {}).get("total_score", 0.0))

        dims_a = run_a.get("scores", {}).get("dimensions", {})
        dims_b = run_b.get("scores", {}).get("dimensions", {})

        dim_delta: Dict[str, float] = {}
        for key in sorted(set(dims_a) | set(dims_b)):
            dim_delta[key] = round(float(dims_b.get(key, 0.0)) - float(dims_a.get(key, 0.0)), 4)

        return {
            "run_a": str(Path(run_a_path).resolve()),
            "run_b": str(Path(run_b_path).resolve()),
            "total_score_a": round(score_a, 4),
            "total_score_b": round(score_b, 4),
            "delta_total": round(score_b - score_a, 4),
            "dimension_deltas": dim_delta,
        }

    def _simulate_outputs(self, skill_content: str, cases: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        outputs: List[Dict[str, str]] = []
        for case in cases:
            case_id = str(case.get("id", ""))
            task_input = str(case.get("task_input", ""))
            output = self._simulate_execution(skill_content, task_input)
            outputs.append({"id": case_id, "output": output})
        return outputs

    def _simulate_execution(self, skill_content: str, task_input: str) -> str:
        procedure_lines: List[str] = []
        for raw in skill_content.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            if line.startswith("```"):
                continue
            if len(line) <= 120:
                procedure_lines.append(line)
            if len(procedure_lines) >= 3:
                break

        procedure_text = " | ".join(procedure_lines) if procedure_lines else "Follow skill guidance and produce safe output."
        return (
            f"Task: {task_input}\n"
            f"Execution plan: {procedure_text}\n"
            "Result: Provide concise response aligned with skill instructions and safety boundaries."
        )

    def _target_type_for(self, path: Path) -> str:
        if path.suffix.lower() == ".py":
            return "python"
        return "skill"

    def _ts(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluation runner")
    sub = parser.add_subparsers(dest="command", required=True)

    baseline = sub.add_parser("baseline")
    baseline.add_argument("--skill-path", required=True)
    baseline.add_argument("--num-cases", type=int, default=20)
    baseline.add_argument("--judge-mode", default="auto", choices=["auto", "rule", "llm"])

    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--skill-path", required=True)
    evaluate.add_argument("--variant-path", required=True)
    evaluate.add_argument("--dataset-path", default=None)
    evaluate.add_argument("--baseline-path", default=None)
    evaluate.add_argument("--judge-mode", default="auto", choices=["auto", "rule", "llm"])

    compare = sub.add_parser("compare")
    compare.add_argument("--run-a", required=True)
    compare.add_argument("--run-b", required=True)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    runner = EvalRunner(str(WORKSPACE_ROOT))

    if args.command == "baseline":
        result = runner.run_baseline(skill_path=args.skill_path, num_cases=args.num_cases, judge_mode=args.judge_mode)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "evaluate":
        result = runner.run_evaluation(
            skill_path=args.skill_path,
            variant_path=args.variant_path,
            dataset_path=args.dataset_path,
            baseline_path=args.baseline_path,
            judge_mode=args.judge_mode,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    result = runner.compare_runs(run_a_path=args.run_a, run_b_path=args.run_b)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
