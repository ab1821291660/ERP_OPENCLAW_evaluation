"""
Async worker entry point.

Phase 1: stub that would consume tasks from Redis/Celery.
Phase 2: connects to runtime runner and executes agent workflows.
"""


def main():
    print("[worker] Agent Harness worker starting...")
    print("[worker] Phase 1 stub - no tasks consumed yet.")


if __name__ == "__main__":
    main()
