"""
Tool success evaluator — checks if required tools were called and succeeded.
"""


def evaluate(candidate_output: dict, expected: dict) -> dict:
    tool_calls = candidate_output.get("_tool_calls", [])
    if not tool_calls:
        return {
            "score": 0.0,
            "evaluator": "tool_success",
            "passed": False,
            "detail": {"reason": "No tool calls recorded"},
        }


    successes = sum(1 for tc in tool_calls if not tc.get("result", {}).get("error"))
    total = len(tool_calls)
    score = successes / total if total > 0 else 0

    return {
        "score": round(score, 3),
        "evaluator": "tool_success",
        "passed": score >= 1.0,
        "detail": {"successes": successes, "total": total},
    }
