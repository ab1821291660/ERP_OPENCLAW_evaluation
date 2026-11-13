"""Import explicit, recorded fixture outputs into the local durable queue."""
import argparse
import json
from pathlib import Path
from .gate import read_json, build_report, check_gate, write_json##===================================
from .store import EvaluationStore##===================================
from .capture import capture_completed_run,enqueue_completed_run##===================================
import sys

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enqueue supplied recorded outputs; does not call a model")
    parser.add_argument("--db", type=Path, default=Path("data/evaluation.sqlite3"))
    parser.add_argument("--user-id", default="synthetic-demo")
    # args = parser.parse_args(argv)
    ##
    #
    # parser = argparse.ArgumentParser(description="Score recorded outputs against golden data and reject regressions")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    # parser.add_argument("--dataset", type=Path, default=Path("evals/golden.synthetic.json"))##===================================
    # parser.add_argument("--predictions", type=Path, default=Path("evals/predictions.baseline.json"))##===================================

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--baseline", type=Path)
    ##
    group.add_argument("--write-baseline", type=Path,##从这些记录的输出中明确创建一个经过审查的基线
                       help="Explicitly create a reviewed baseline from these recorded outputs")
    parser.add_argument("--output", type=Path)
    ##
    parser.add_argument("--min-score", type=float, default=0.95)
    parser.add_argument("--max-regression", type=float, default=0.05)
    args = parser.parse_args(argv)
    try:
        baseline = read_json(args.baseline) if args.baseline else None##===================================


        # dataset, predictions = read_json(args.dataset), read_json(args.predictions)
        report = build_report(##===================================
                 read_json(args.dataset), read_json(args.predictions))##===================================


        # if report["missing_predictions"]:
        #     parser.error("cannot enqueue missing predictions")
        failures = check_gate(report,
                              baseline,
                              min_score=args.min_score,
                              max_regression=args.max_regression)
        report.update(passed=not failures, failures=failures)
        if args.output:
            write_json(args.output, report)##===================================
        if args.write_baseline and not failures:##新的基线【通过了评测】
            write_json(args.write_baseline, report)##===================================
        print(json.dumps({"passed": not failures, "overall": report["overall"], "failures": failures}, ensure_ascii=False))
        return int(bool(failures))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Gate configuration error: {exc}", file=sys.stderr)
        return 2




    store = EvaluationStore(args.db)##Enqueue提供记录输出；不调用模型
    ids = []
    for case in dataset["cases"]:
        identity = f"{dataset['version']}:{predictions['version']}:{case['id']}"
        # evaluate(actual, expected)  # Validate the contract before accepting a durable job.#在接受一份持久的工作之前，先验证合同。。。。
        # # evaluate(actual, expected) ##===================================##===================================##===================================##===================================
        ids.append(store.enqueue(user_id=args.user_id,##Enqueue提供记录输出；不调用模型 ##===================================
                                 trace_id=case["id"],##========"id": "margin-decimal",
                                 session_id="synthetic-demo",
                                 actual=predictions["predictions"][case["id"]],##========##========预测结果
                                 expected=case["expected"],##========"expected": {"answer_numeric": "15.00", "absolute_tolerance": "0.01", "task_completed": true,
                                                                                ##"required_tools": {"calculate_margin": ["revenue", "profit"]}}
                                                                                #  "requires_approval": true,
                                                                                #  "forbidden_tools": ["update_order", "delete_order"]
                                                                                #  "max_latency_ms": "500"
                                                                                # "max_tokens": "800"
                                                                                ##
                                                                                ##
                                                                                # "evidence_ids": ["fake-report:page-1", "fake-order:line-2"],
                                                                                # "allowed_evidence_ids": ["fake-report:page-1", "fake-order:line-2", "fake-policy:section-3"],
                                                                                # "task_completed": true

                                   version=predictions["version"], run_id=identity,
                                 input_data=case.get("input")))##========# "input": "Synthetic Co: revenue 1200, profit 180. Calculate profit margin as percent.",
        # ##
        # ##
        # ##或者
        # ids.append(capture_completed_run(##===================================##===================================##===================================##===================================
        #                         store: EvaluationStore,
        #                         *,
        #                         user_id: str,
        #                         session_id: str,
        #                         trace_id: str,##========
        #                         actual: dict[str, Any], ##========##========预测结果
        #                         expected: dict[str, Any], ##========
        #                         version: str,run_id: str | None = None,
        #                         input_data: Any = None))##========
        # ##
        # ##
    print(json.dumps({"enqueued": len(ids), "job_ids": ids, "source": "supplied recorded outputs; no model executed"}))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
