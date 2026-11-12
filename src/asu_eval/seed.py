"""Import explicit, recorded fixture outputs into the local durable queue."""
import argparse
import json
from pathlib import Path
from .gate import build_report, read_json##===================================
from .store import EvaluationStore##===================================
from .capture import capture_completed_run,enqueue_completed_run##===================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enqueue supplied recorded outputs; does not call a model")
    parser.add_argument("--db", type=Path, default=Path("data/evaluation.sqlite3"))
    parser.add_argument("--dataset", type=Path, default=Path("evals/golden.synthetic.json"))##===================================
    parser.add_argument("--predictions", type=Path, default=Path("evals/predictions.baseline.json"))##===================================
    parser.add_argument("--user-id", default="synthetic-demo")
    args = parser.parse_args(argv)
    dataset, predictions = read_json(args.dataset), read_json(args.predictions)
    report = build_report(dataset, predictions)##===================================
    if report["missing_predictions"]:
        parser.error("cannot enqueue missing predictions")


    store = EvaluationStore(args.db)
    ids = []
    for case in dataset["cases"]:
        identity = f"{dataset['version']}:{predictions['version']}:{case['id']}"
        # evaluate(actual, expected)  # Validate the contract before accepting a durable job.#在接受一份持久的工作之前，先验证合同。。。。
        # # evaluate(actual, expected) ##===================================##===================================##===================================##===================================
        ids.append(store.enqueue(user_id=args.user_id, ##===================================
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
