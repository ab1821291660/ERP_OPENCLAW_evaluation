"""
Sandbox resource limits configuration.
"""

from dataclasses import dataclass


@dataclass
class SandboxLimits:
    timeout_seconds: int = 30
    max_output_bytes: int = 1024 * 1024  # 1 MB
    allowed_working_dir: str = "/tmp"
    max_command_length: int = 1024


default_limits = SandboxLimits()
