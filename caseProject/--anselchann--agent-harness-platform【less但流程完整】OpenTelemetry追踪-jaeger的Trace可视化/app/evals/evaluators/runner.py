"""
Evaluation Runner - orchestrates eval runs across datasets.

Flow:
1. Load dataset cases
2. For each case, run candidate agent (and optionally baseline)
3. Run evaluators on each output
4. Aggregate scores across all cases
5. Return summary
"""

import logging
from app.evals.dataset.dataset import load_dataset
from app.evals.gate.comparator import compare
from app.schemas.evals import DatasetCase
logger = logging.getLogger(__name__)

EVALUATOR_MAP = {
    "exact_match": "app.evals.evaluators.exact_match",
    "tool_success": "app.evals.evaluators.tool_success",
    "rubric_judge": "app.evals.evaluators.rubric_judge",
}

DEFAULT_EVALUATORS = ["exact_match", "tool_success", "rubric_judge"]


async def run_eval(
    eval_id: str,
    dataset_name: str,
    candidate_config: dict,##===================================
    baseline_config: dict | None = None,##===================================
    evaluators: list[str] | None = None,
) -> dict:
    """Run evaluation against a full dataset and return aggregated summary."""
    cases = load_dataset(dataset_name)##===================================
    evaluator_names = evaluators or DEFAULT_EVALUATORS
    evaluator_names = [e for e in evaluator_names if e in EVALUATOR_MAP]
    results = []
    for case in cases:
        case_result = await _evaluate_case(case, candidate_config, evaluator_names)##单个case
        results.append(case_result)


    # Run baseline if specified
    baseline_results = None
    if baseline_config:
        baseline_results = []
        for case in cases:
            br = await _evaluate_case(case, baseline_config, evaluator_names)##单个case
            baseline_results.append(br)


    summary = _aggregate(results, evaluator_names)##===================================
    baseline_summary = _aggregate(baseline_results, evaluator_names) if baseline_results else None##===================================
    comparison = compare(baseline_summary, summary) if baseline_summary else None##===================================
    return {
        "eval_id": eval_id,
        "dataset_name": dataset_name,
        "evaluators": evaluator_names,
        "total_cases": len(cases),
        "pass_count": summary["pass_count"],
        "fail_count": summary["fail_count"],
        "pass_rate": summary["pass_rate"],
        "evaluator_breakdown": summary["evaluator_breakdown"],##===================================
        "cases": results,
        "comparison": comparison,##===================================
        # failed_cases
    }



async def _evaluate_case(##单个case
    case: DatasetCase,
    config: dict,
    evaluator_names: list[str],
) -> dict:
    """Run agent for a single case and score with all evaluators."""
    from app.runtime.runner import execute_run
    import uuid
    run_id = f"eval_{uuid.uuid4().hex[:8]}"
    try:
        state = await execute_run(##===================================
            run_id=run_id,
            task_type=case.task_type,
            user_input=case.input,
            config=config,
        )
    except Exception as exc:
        return {
            "case_id": case.case_id,
            "output": None,
            "scores": {},
            "passed": False,
            "error": str(exc),
        }
    output = state.get("final_output", {}) or {}##===================================
    # Attach metadata for evaluators
    output["_question"] = case.input.get("question", "")
    output["_tool_calls"] = state.get("tool_calls", [])


    scores = {}##===================================
    all_passed = True##===================================
    for ename in evaluator_names:
        try:
            module_path = EVALUATOR_MAP[ename]
            mod = __import__(module_path, fromlist=["evaluate"])
            result = await _maybe_await(mod.evaluate(output, case.expected))##===================================
            scores[ename] = result
            if not result.get("passed", False):
                all_passed = False
        except Exception as exc:
            logger.exception("Evaluator %s failed for case %s", ename, case.case_id)
            scores[ename] = {"score": 0,   "passed": False,   "error": str(exc)}
            all_passed = False


    return {
        "case_id": case.case_id,
        "output": output,##===================================
        "scores": scores,##===================================
        "passed": all_passed,##===================================
    }
async def _maybe_await(result):
    import inspect
    if inspect.isawaitable(result):
        return await result
    return result



def ________(self):pass
def _aggregate(results: list[dict], evaluator_names: list[str]) -> dict:
    if not results:
        return {"total_cases": 0, "pass_count": 0, "fail_count": 0, "pass_rate": 0, "evaluator_breakdown": {}}


    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed
    ##
    breakdown = {}##各个分项的平均分##===================================
    for ename in evaluator_names:
        scores = []
        for r in results:
            s = r.get("scores", {}).get(ename, {})
            if "score" in s:
                scores.append(s["score"])
        breakdown[ename] = {
            "avg_score": round(sum(scores) / len(scores), 3) if scores else 0,
            "count": len(scores),
        }
    ##
    return {
        "total_cases": total,
        "pass_count": passed,
        "fail_count": failed,
        "pass_rate": round(passed / total, 4) if total > 0 else 0,
        "evaluator_breakdown": breakdown,##===================================
    }
