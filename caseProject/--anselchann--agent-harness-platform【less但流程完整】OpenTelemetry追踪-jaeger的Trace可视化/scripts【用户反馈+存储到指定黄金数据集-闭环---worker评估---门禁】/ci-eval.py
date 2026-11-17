#!/usr/bin/env python3
"""
CI Regression Gate — runs eval against a dataset and fails on quality regression.

Usage:
    python scripts/ci-eval.py --dataset customer_support_v1

Environment:
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL — LLM provider config

Exit codes:
    0 — all thresholds passed##===================================##===================================
    1 — regression detected##===================================##===================================
    2 — execution error##===================================##===================================
"""
import argparse
import asyncio
import json
import os
import sys
# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

THRESHOLDS = {
    "pass_rate_min": float(os.getenv("CI_PASS_RATE_MIN", "0.6")),
    "exact_match_min": float(os.getenv("CI_EXACT_MATCH_MIN", "0.6")),
    "rubric_judge_min": float(os.getenv("CI_RUBRIC_JUDGE_MIN", "0.6")),
    "latency_max_ms": float(os.getenv("CI_LATENCY_MAX_MS", "30000")),
}



RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"
def main():
    parser = argparse.ArgumentParser(description="CI Eval Regression Gate")
    parser.add_argument("--dataset", default="customer_support_v1")##===================================
    parser.add_argument("--evaluators", default="exact_match, rubric_judge")##===================================
    parser.add_argument("--baseline", default=None, help="Path to baseline summary JSON")
    parser.add_argument("--output", default=None, help="Write summary JSON to file")
    args = parser.parse_args()
    evaluators = [e.strip() for e in args.evaluators.split(",")]
    try:
        result = asyncio.run(_run_eval(args.dataset,##===================================##===================================
                                       evaluators))
    except Exception as exc:
        print(f"{RED}[ERROR] Eval execution failed: {exc}{RESET}")
        sys.exit(2)
    print("\n=== Eval Results ===")
    print(f"  Dataset:       {result['dataset_name']}")
    print(f"  Total cases:   {result['total_cases']}")
    print(f"  Pass rate:     {result['pass_rate']:.1%}")
    print(f"  Pass/Fail:     {result['pass_count']}/{result['fail_count']}")
    breakdown = result.get("evaluator_breakdown", {})##===================================
    for name, stats in breakdown.items():
        print(f"  {name}:  avg={stats['avg_score']:.3f}")

    # Check thresholds
    failures = []
    pass_rate = result["pass_rate"]
    if pass_rate < THRESHOLDS["pass_rate_min"]:
        failures.append(
            f"pass_rate {pass_rate:.1%} < threshold {THRESHOLDS['pass_rate_min']:.1%}"
        )

    for name, threshold_key in [("exact_match", "exact_match_min"), ("rubric_judge", "rubric_judge_min")]:
        eb = breakdown.get(name, {})
        avg = eb.get("avg_score", 0)
        threshold = THRESHOLDS[threshold_key]
        if avg < threshold:
            failures.append(f"{name} {avg:.3f} < threshold {threshold:.3f}")




    # Baseline comparison
    baseline = None
    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline) as f:
            baseline = json.load(f)
    if baseline:
        from app.evals.gate.comparator import compare##===================================##===================================
        comparison = compare(baseline, result)
        result["comparison"] = comparison
        print("\n=== Baseline Comparison ===")
        for key, d in comparison.get("diff", {}).items():
            print(f"  {key}: {d['baseline']} → {d['candidate']} (Δ={d['delta']:+.3f})")
        if comparison.get("regressed"):
            failures.append("regression vs baseline detected")



    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        print(f"\nSummary written to {args.output}")
    if failures:
        print(f"\n{RED}=== REGRESSION DETECTED ==={RESET}")
        for f in failures:
            print(f"{RED}  ✗ {f}{RESET}")
        sys.exit(1)
    print(f"\n{GREEN}=== All thresholds passed ==={RESET}")
    sys.exit(0)
async def _run_eval(dataset_name: str, evaluators: list[str]) -> dict:
    from app.evals.evaluators.runner import run_eval
    return await run_eval(##===================================##===================================
                            eval_id=f"ci_{__import__('uuid').uuid4().hex[:8]}",
                            dataset_name=dataset_name,##===================================
                            candidate_config={},
                            evaluators=evaluators,##===================================
    )
if __name__ == "__main__":
    main()

