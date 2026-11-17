"""
Tool Policy Engine - enforces allow/deny rules and rate limits.

Phase 1: simple check stub.
Phase 2: full allowlist/denylist/timeout/rate-limit enforcement.
"""

from app.schemas.tools import ToolSpec


def check_policy(run_id: str, spec: ToolSpec, payload: dict) -> None:
    """
    Check whether the tool invocation is allowed.

    Raises ToolPolicyDeniedError if the invocation violates policy.
    """
    # Phase 1 stub - all tools allowed
    pass
