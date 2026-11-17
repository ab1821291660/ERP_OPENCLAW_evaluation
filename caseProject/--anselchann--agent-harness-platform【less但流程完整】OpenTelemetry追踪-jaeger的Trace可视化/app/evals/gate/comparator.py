"""
Comparator - compares baseline vs candidate eval results.

Determines which metrics improved and which regressed.
"""


def compare(baseline: dict, candidate: dict) -> dict:
    """Compare two eval summaries and produce a diff."""
    if not baseline or not candidate:
        return {"baseline": baseline, "candidate": candidate, "diff": {}}

    diff = {}
    for key in set(baseline.keys()) | set(candidate.keys()):
        bv = baseline.get(key, 0)
        cv = candidate.get(key, 0)
        if isinstance(bv, (int, float)) and isinstance(cv, (int, float)):
            diff[key] = {
                "baseline": bv,
                "candidate": cv,
                "delta": cv - bv,
            }
    return {
        "baseline": baseline,
        "candidate": candidate,
        "diff": diff,
        "regressed": any(##===================================
            d.get("delta", 0) < 0
            for k, d in diff.items()
            if k in ("pass_rate", "success_rate")##===================================
        ),
    }
