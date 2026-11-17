import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    app_name: str = "agent-harness-platform"
    api_prefix: str = "/api/v1"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"


    database_url: str = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./agent_harness.db",
    )

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")




    otel_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    phoenix_endpoint: str = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")

    worker_concurrency: int = int(os.getenv("WORKER_CONCURRENCY", "4"))
    default_timeout_seconds: int = 60




    max_tool_calls_per_run: int = int(os.getenv("MAX_TOOL_CALLS_PER_RUN", "10"))

    mcp_server_dir: str = os.path.join(
        os.path.dirname(__file__), "", "..", "mcp_servers"
    )
settings = Settings()

