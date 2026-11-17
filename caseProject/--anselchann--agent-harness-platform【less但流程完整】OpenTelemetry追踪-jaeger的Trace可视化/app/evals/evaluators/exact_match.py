"""
Exact-match evaluator — checks if candidate output contains expected fields/values.
"""


def evaluate(candidate_output: dict, expected: dict) -> dict:
    must_include = expected.get("must_include", [])
    if not must_include:
        return {"score": 1.0, "evaluator": "exact_match", "passed": True}

    output_text = str(candidate_output).lower()
    hits = [kw for kw in must_include if kw.lower() in output_text]
    misses = [kw for kw in must_include if kw.lower() not in output_text]

    score = len(hits) / len(must_include) if must_include else 1.0
    return {
        "score": round(score, 3),
        "evaluator": "exact_match",
        "passed": score >= 1.0,
        "detail": {"hits": hits, "misses": misses},
    }
