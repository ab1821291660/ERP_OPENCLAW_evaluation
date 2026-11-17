"""
Sandbox Policy - command allowlist and safety constraints.
"""

from app.exceptions import SandboxPolicyViolation

DEFAULT_ALLOWED_COMMANDS = {
    "ls", "cat", "head", "tail", "wc", "grep", "find",
    "echo", "date", "whoami", "pwd", "env",
    "git", "python3", "python",
}


def check_command(command: list[str]) -> None:
    """Check if a command is allowed by sandbox policy."""
    if not command:
        raise SandboxPolicyViolation("", "empty command")

    base = command[0].split("/")[-1]
    if base not in DEFAULT_ALLOWED_COMMANDS:
        raise SandboxPolicyViolation(
            " ".join(command), f"'{base}' not in allowlist"
        )
