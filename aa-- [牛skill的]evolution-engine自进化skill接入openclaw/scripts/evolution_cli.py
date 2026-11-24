#!/usr/bin/env python3
"""Evolution Engine CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


EXIT_SUCCESS = 0
EXIT_ARG_ERROR = 1
EXIT_EXEC_ERROR = 2
EXIT_NEEDS_APPROVAL = 3


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("evolution_cli")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = _setup_logger()
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent.parent.parent


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        LOGGER.warning(f"Failed to read JSON from {path}: {exc}")
        return {}


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_json_file(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_failure_traces_from_dir(limit: int = 200) -> List[Dict[str, Any]]:
    trace_dir = WORKSPACE_ROOT / "evolution" / "traces"
    if not trace_dir.exists():
        return []
    records: List[Dict[str, Any]] = []
    for path in sorted(trace_dir.glob("*.json"), reverse=True):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(item, dict) and item.get("success") is False:
            records.append(item)
        if len(records) >= max(1, limit):
            break
    return records


def _parse_list_arg(raw: str) -> List[str]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if str(x).strip()]
    except Exception:
        pass
    return [x.strip() for x in text.split("|") if x.strip()]


def _status() -> Dict[str, Any]:
    evolution_dir = WORKSPACE_ROOT / "evolution"
    today = _today()

    signals_file = evolution_dir / "signals" / f"{today}.json"
    hypotheses_file = evolution_dir / "hypotheses" / f"{today}.json"
    mutations_file = evolution_dir / "mutations" / f"{today}.json"

    signals_data = _safe_read_json(signals_file)
    hypotheses_data = _safe_read_json(hypotheses_file)
    mutations_data = _safe_read_json(mutations_file)

    signals = signals_data.get("signals", []) if isinstance(signals_data, dict) else []
    hypotheses = hypotheses_data.get("hypotheses", []) if isinstance(hypotheses_data, dict) else []
    mutations = mutations_data.get("mutations", []) if isinstance(mutations_data, dict) else []

    pending = 0
    for item in hypotheses:
        if isinstance(item, dict) and item.get("status", "pending") in {"pending", "requires_approval"}:
            pending += 1

    return {
        "ok": True,
        "date": today,
        "workspace_root": str(WORKSPACE_ROOT),
        "recent_signal_count": len(signals),
        "pending_hypothesis_count": pending,
        "today_mutation_count": len(mutations),
    }


def _append_daily_record(subdir: str, payload: Dict[str, Any], key: str) -> None:
    target = WORKSPACE_ROOT / "evolution" / subdir / f"{_today()}.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    data: Dict[str, Any]
    if target.exists():
        data = _safe_read_json(target)
        if not isinstance(data, dict):
            data = {}
    else:
        data = {}

    if key not in data or not isinstance(data.get(key), list):
        data[key] = []

    data[key].append(payload)
    if "date" not in data:
        data["date"] = _today()

    temp_path = target.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, target)


def _run_full_cycle(date: Optional[str] = None) -> Dict[str, Any]:
    from observer import Observer
    from reflector import Reflector
    from mutator import Mutator
    from evaluator import Evaluator
    from selector import Selector

    cycle_date = date or _today()
    observer = Observer(str(WORKSPACE_ROOT))
    reflector = Reflector(str(WORKSPACE_ROOT))
    mutator = Mutator(str(WORKSPACE_ROOT))
    evaluator = Evaluator(str(WORKSPACE_ROOT))
    selector = Selector(str(WORKSPACE_ROOT))

    observed = observer.observe(cycle_date)
    reflected = reflector.reflect(observed)

    _append_daily_record("signals", observed, "signals")
    _append_daily_record("hypotheses", reflected, "hypotheses")

    processed: List[Dict[str, Any]] = []
    approvals_needed: List[Dict[str, Any]] = []

    for hypothesis in reflected.get("hypotheses", []):
        if not hypothesis.get("auto_approve_eligible", False):
            approvals_needed.append(
                {
                    "hypothesis_id": hypothesis.get("id"),
                    "reason": "auto_approve_eligible=false",
                }
            )
            continue

        mutation = mutator.mutate(hypothesis)
        evaluation = evaluator.evaluate(mutation)
        decision = selector.select(evaluation, hypothesis)

        item: Dict[str, Any] = {
            "hypothesis": hypothesis,
            "mutation": mutation,
            "evaluation": evaluation,
            "decision": decision,
        }

        if decision.get("decision") == "auto_approve":
            item["apply"] = selector.apply(mutation)
        else:
            approvals_needed.append(
                {
                    "hypothesis_id": hypothesis.get("id"),
                    "mutation_id": mutation.get("id"),
                    "reason": decision.get("reason"),
                }
            )
        processed.append(item)

    return {
        "ok": True,
        "date": cycle_date,
        "observed_signal_count": len(observed.get("signals", [])),
        "hypothesis_count": len(reflected.get("hypotheses", [])),
        "processed": processed,
        "approvals_needed": approvals_needed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evolution Engine CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    observe_p = sub.add_parser("observe")
    observe_p.add_argument("--date", default=None)

    reflect_p = sub.add_parser("reflect")
    reflect_p.add_argument("--date", default=None)

    detect_signals_p = sub.add_parser("detect-signals")
    detect_signals_p.add_argument("--date", default=None)

    propose_p = sub.add_parser("propose")
    propose_p.add_argument("--signature", required=True)
    propose_p.add_argument("--target", required=True)
    propose_p.add_argument("--change", required=True)
    propose_p.add_argument("--trigger-type", default="manual")
    propose_p.add_argument("--confidence", default="medium", choices=["high", "medium", "low"])
    propose_p.add_argument("--reason", default="manual proposal via CLI")
    propose_p.add_argument("--evidence", action="append", default=[])

    approve_p = sub.add_parser("approve")
    approve_p.add_argument("signature")

    reject_p = sub.add_parser("reject")
    reject_p.add_argument("signature")
    reject_p.add_argument("--reason", default=None)

    list_p = sub.add_parser("list-proposals")
    list_p.add_argument("--status", default="pending", choices=["pending", "approved", "rejected"])

    rule_stats_p = sub.add_parser("rule-stats")
    rule_stats_p.add_argument("--signature", required=True)
    rule_stats_p.add_argument("--window-days", type=int, default=30)

    stale_p = sub.add_parser("stale-rules")
    stale_p.add_argument("--threshold-days", type=int, default=30)

    mutate_p = sub.add_parser("mutate")
    mutate_p.add_argument("--hypothesis-id", required=True)

    evaluate_p = sub.add_parser("evaluate")
    evaluate_p.add_argument("--mutation-id", required=True)

    apply_p = sub.add_parser("apply")
    apply_p.add_argument("--mutation-id", required=True)
    apply_p.add_argument("--force", action="store_true")

    rollback_p = sub.add_parser("rollback")
    rollback_p.add_argument("--version-id", required=True)

    sub.add_parser("status")

    cycle_p = sub.add_parser("run-full-cycle")
    cycle_p.add_argument("--date", default=None)

    build_dataset_p = sub.add_parser("build-dataset")
    build_dataset_p.add_argument("--skill-path", required=True)
    build_dataset_p.add_argument("--num-cases", type=int, default=20)
    build_dataset_p.add_argument("--output", default=None)
    build_dataset_p.add_argument("--seed", type=int, default=42)

    eval_baseline_p = sub.add_parser("eval-baseline")
    eval_baseline_p.add_argument("--skill-path", required=True)
    eval_baseline_p.add_argument("--num-cases", type=int, default=20)
    eval_baseline_p.add_argument("--judge-mode", default="auto", choices=["auto", "rule", "llm"])

    eval_variant_p = sub.add_parser("eval-variant")
    eval_variant_p.add_argument("--skill-path", required=True)
    eval_variant_p.add_argument("--variant-path", required=True)
    eval_variant_p.add_argument("--dataset-path", default=None)
    eval_variant_p.add_argument("--baseline-path", default=None)
    eval_variant_p.add_argument("--judge-mode", default="auto", choices=["auto", "rule", "llm"])

    eval_compare_p = sub.add_parser("eval-compare")
    eval_compare_p.add_argument("--run-a", required=True)
    eval_compare_p.add_argument("--run-b", required=True)

    skill_stats_p = sub.add_parser("skill-stats")
    skill_stats_p.add_argument("--skill-name", required=True)
    skill_stats_p.add_argument("--window-days", type=int, default=7)

    create_skill_p = sub.add_parser("create-skill")
    create_skill_p.add_argument("--task", required=True)
    create_skill_p.add_argument("--steps", required=True, help="JSON list or a|b|c")
    create_skill_p.add_argument("--pitfalls", default="[]", help="JSON list or a|b|c")
    create_skill_p.add_argument("--tools", default="[]", help="JSON list or a|b|c")
    create_skill_p.add_argument("--success-output", default="")

    patch_skill_p = sub.add_parser("patch-skill")
    patch_skill_p.add_argument("--skill-path", required=True)
    patch_skill_p.add_argument("--issue", required=True)
    patch_skill_p.add_argument("--fix", required=True)
    patch_skill_p.add_argument("--trace-id", default=None)

    evolve_skill_p = sub.add_parser("evolve-skill")
    evolve_skill_p.add_argument("--skill-path", required=True)

    sub.add_parser("monitor")
    sub.add_parser("triage")
    sub.add_parser("weekly-review")
    sub.add_parser("daily-check")
    sub.add_parser("cron-setup")

    evolve_prompt_p = sub.add_parser("evolve-prompt")
    evolve_prompt_p.add_argument("--target", required=True, choices=["SOUL.md", "AGENTS.md", "TOOLS.md"])
    evolve_prompt_p.add_argument("--traces-path", default=None)
    evolve_prompt_p.add_argument("--eval-scores-path", default=None)

    test_prompt_p = sub.add_parser("test-prompt")
    test_prompt_p.add_argument("--target", required=True, choices=["SOUL.md", "AGENTS.md", "TOOLS.md"])
    test_prompt_p.add_argument("--variant", required=True)
    test_prompt_p.add_argument("--scenarios-path", default=None)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)

        sys.path.insert(0, str(SCRIPT_DIR))

        if args.command == "status":
            _print_json(_status())
            return EXIT_SUCCESS

        if args.command == "run-full-cycle":
            result = _run_full_cycle(args.date)
            _print_json(result)
            return EXIT_NEEDS_APPROVAL if result.get("approvals_needed") else EXIT_SUCCESS

        if args.command == "build-dataset":
            from dataset_builder import DatasetBuilder

            builder = DatasetBuilder(args.skill_path)
            result = builder.generate_dataset(num_cases=args.num_cases, output_path=args.output, seed=args.seed)
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "eval-baseline":
            from eval_runner import EvalRunner

            runner = EvalRunner(str(WORKSPACE_ROOT))
            result = runner.run_baseline(
                skill_path=args.skill_path,
                num_cases=args.num_cases,
                judge_mode=args.judge_mode,
            )
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "eval-variant":
            from eval_runner import EvalRunner

            runner = EvalRunner(str(WORKSPACE_ROOT))
            result = runner.run_evaluation(
                skill_path=args.skill_path,
                variant_path=args.variant_path,
                dataset_path=args.dataset_path,
                baseline_path=args.baseline_path,
                judge_mode=args.judge_mode,
            )
            _print_json(result)
            gates = result.get("gates", {})
            return EXIT_SUCCESS if gates.get("passed", False) else EXIT_EXEC_ERROR

        if args.command == "eval-compare":
            from eval_runner import EvalRunner

            runner = EvalRunner(str(WORKSPACE_ROOT))
            result = runner.compare_runs(run_a_path=args.run_a, run_b_path=args.run_b)
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "skill-stats":
            from trace_collector import TraceCollector

            collector = TraceCollector(str(WORKSPACE_ROOT))
            result = collector.get_skill_stats(skill_name=args.skill_name, window_days=args.window_days)
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "create-skill":
            from skill_evolver import SkillEvolver

            evolver = SkillEvolver(str(WORKSPACE_ROOT))
            result = evolver.auto_create_skill(
                task_description=args.task,
                steps=_parse_list_arg(args.steps),
                pitfalls=_parse_list_arg(args.pitfalls),
                tools_used=_parse_list_arg(args.tools),
                success_output=args.success_output,
            )
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "patch-skill":
            from skill_evolver import SkillEvolver

            evolver = SkillEvolver(str(WORKSPACE_ROOT))
            result = evolver.auto_patch_skill(
                skill_path=args.skill_path,
                issue=args.issue,
                fix=args.fix,
                trace_id=args.trace_id,
            )
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "evolve-skill":
            from skill_evolver import SkillEvolver

            evolver = SkillEvolver(str(WORKSPACE_ROOT))
            result = evolver.evolve_skill(skill_path=args.skill_path)
            _print_json(result)
            return EXIT_SUCCESS if result.get("decision") == "improved" else EXIT_EXEC_ERROR

        if args.command == "monitor":
            from performance_monitor import PerformanceMonitor

            monitor = PerformanceMonitor(str(WORKSPACE_ROOT))
            result = monitor.collect_metrics()
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "triage":
            from performance_monitor import PerformanceMonitor

            monitor = PerformanceMonitor(str(WORKSPACE_ROOT))
            _print_json({"targets": monitor.auto_triage()})
            return EXIT_SUCCESS

        if args.command == "weekly-review":
            from evolution_scheduler import EvolutionScheduler

            scheduler = EvolutionScheduler(str(WORKSPACE_ROOT))
            result = scheduler.run_weekly_review()
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "daily-check":
            from evolution_scheduler import EvolutionScheduler

            scheduler = EvolutionScheduler(str(WORKSPACE_ROOT))
            result = scheduler.run_daily_check()
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "cron-setup":
            from evolution_scheduler import EvolutionScheduler

            scheduler = EvolutionScheduler(str(WORKSPACE_ROOT))
            _print_json({"cron_setup": scheduler.suggest_cron_setup()})
            return EXIT_SUCCESS

        if args.command == "evolve-prompt":
            from prompt_evolver import PromptEvolver, load_traces_file

            traces: List[Dict[str, Any]]
            if args.traces_path:
                traces = load_traces_file(args.traces_path)
            else:
                traces = _load_failure_traces_from_dir()

            eval_scores: Optional[Dict[str, Any]] = None
            if args.eval_scores_path:
                loaded = _load_json_file(args.eval_scores_path)
                if isinstance(loaded, dict):
                    eval_scores = loaded

            evolver = PromptEvolver(str(WORKSPACE_ROOT))
            analysis = evolver.analyze_failures(
                target_file=args.target,
                traces=traces,
                eval_scores=eval_scores,
            )
            variant = evolver.generate_variant(args.target, analysis)
            result = {
                "ok": True,
                "target_file": args.target,
                "analysis": analysis,
                "variant": variant,
            }
            _print_json(result)
            return EXIT_SUCCESS if variant.get("variant_path") else EXIT_EXEC_ERROR

        if args.command == "test-prompt":
            from prompt_tester import PromptTester, load_scenarios

            scenarios: Optional[List[Dict[str, Any]]] = None
            if args.scenarios_path:
                scenarios = load_scenarios(args.scenarios_path)

            tester = PromptTester(str(WORKSPACE_ROOT))
            result = tester.test_variant(
                target_file=args.target,
                variant_path=args.variant,
                test_scenarios=scenarios,
            )
            _print_json(result)
            return EXIT_EXEC_ERROR if result.get("regression_detected") else EXIT_SUCCESS

        if args.command == "observe":
            from observer import Observer

            observer = Observer(str(WORKSPACE_ROOT))
            observed = observer.observe(args.date)
            _append_daily_record("signals", observed, "signals")
            _print_json(observed)
            return EXIT_SUCCESS

        if args.command == "detect-signals":
            from signal_detector import SignalDetector

            detector = SignalDetector(str(WORKSPACE_ROOT))
            result = detector.detect(args.date)
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "reflect":
            from observer import Observer
            from reflector import Reflector

            observer = Observer(str(WORKSPACE_ROOT))
            signals = observer.observe(args.date)
            reflector = Reflector(str(WORKSPACE_ROOT))
            reflected = reflector.reflect(signals)
            _append_daily_record("hypotheses", reflected, "hypotheses")
            _print_json(reflected)
            return EXIT_SUCCESS

        if args.command == "propose":
            from proposal_manager import ProposalManager

            manager = ProposalManager(str(WORKSPACE_ROOT))
            result = manager.create_proposal(
                signature=args.signature,
                target_file=args.target,
                trigger_type=args.trigger_type,
                evidence=args.evidence,
                proposed_change=args.change,
                confidence=args.confidence,
                reason=args.reason,
            )
            _print_json(result)
            return EXIT_SUCCESS if result.get("ok", False) else EXIT_EXEC_ERROR

        if args.command == "approve":
            from proposal_manager import ProposalManager

            manager = ProposalManager(str(WORKSPACE_ROOT))
            result = manager.approve_proposal(args.signature)
            _print_json(result)
            return EXIT_SUCCESS if result.get("ok", False) else EXIT_EXEC_ERROR

        if args.command == "reject":
            from proposal_manager import ProposalManager

            manager = ProposalManager(str(WORKSPACE_ROOT))
            result = manager.reject_proposal(args.signature, reason=args.reason)
            _print_json(result)
            return EXIT_SUCCESS if result.get("ok", False) else EXIT_EXEC_ERROR

        if args.command == "list-proposals":
            from proposal_manager import ProposalManager

            manager = ProposalManager(str(WORKSPACE_ROOT))
            proposals = manager.list_proposals(status=args.status)
            _print_json({"status": args.status, "count": len(proposals), "proposals": proposals})
            return EXIT_SUCCESS

        if args.command == "rule-stats":
            from rule_tracker import RuleTracker

            tracker = RuleTracker(str(WORKSPACE_ROOT))
            result = tracker.get_rule_stats(signature=args.signature, window_days=args.window_days)
            _print_json(result)
            return EXIT_SUCCESS

        if args.command == "stale-rules":
            from rule_tracker import RuleTracker

            tracker = RuleTracker(str(WORKSPACE_ROOT))
            stale = tracker.scan_stale_rules(threshold_days=args.threshold_days)
            _print_json({"threshold_days": args.threshold_days, "count": len(stale), "rules": stale})
            return EXIT_SUCCESS

        if args.command == "mutate":
            from mutator import Mutator

            mutator = Mutator(str(WORKSPACE_ROOT))
            mutation = mutator.mutate_by_hypothesis_id(args.hypothesis_id)
            _append_daily_record("mutations", mutation, "mutations")
            _print_json(mutation)
            return EXIT_SUCCESS

        if args.command == "evaluate":
            from evaluator import Evaluator

            evaluator = Evaluator(str(WORKSPACE_ROOT))
            evaluation = evaluator.evaluate_by_mutation_id(args.mutation_id)
            _print_json(evaluation)
            return EXIT_SUCCESS if evaluation.get("overall") == "pass" else EXIT_EXEC_ERROR

        if args.command == "apply":
            from selector import Selector

            selector = Selector(str(WORKSPACE_ROOT))
            result = selector.apply_by_mutation_id(args.mutation_id, force=args.force)
            _print_json(result)
            if result.get("decision") == "requires_approval" and not args.force:
                return EXIT_NEEDS_APPROVAL
            return EXIT_SUCCESS if result.get("applied", False) else EXIT_EXEC_ERROR

        if args.command == "rollback":
            from selector import Selector

            selector = Selector(str(WORKSPACE_ROOT))
            result = selector.rollback(args.version_id)
            _print_json(result)
            return EXIT_SUCCESS if result.get("success", False) else EXIT_EXEC_ERROR

        _print_json({"ok": False, "error": f"Unsupported command: {args.command}"})
        return EXIT_ARG_ERROR

    except SystemExit:
        raise
    except Exception as exc:
        LOGGER.exception(f"Execution failed: {exc}")
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_EXEC_ERROR


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        LOGGER.exception(f"Fatal error: {exc}")
        _print_json({"ok": False, "error": str(exc)})
        raise SystemExit(EXIT_EXEC_ERROR)
