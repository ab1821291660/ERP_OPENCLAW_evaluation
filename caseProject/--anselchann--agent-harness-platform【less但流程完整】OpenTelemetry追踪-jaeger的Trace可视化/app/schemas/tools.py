from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    tool_name: str
    source: str
    description: str = ""
    input_schema: dict = Field(default_factory=dict)
    timeout_seconds: int = 30
    requires_approval: bool = False
    tags: list[str] = Field(default_factory=list)


class ToolPolicy(BaseModel):
    tool_name: str
    enabled: bool = True
    allow_task_types: list[str] = Field(default_factory=list)
    deny_task_types: list[str] = Field(default_factory=list)
    max_calls_per_run: int = 5


class ToolRegisterRequest(BaseModel):
    tool_name: str
    source: str
    description: str = ""
    input_schema: dict = Field(default_factory=dict)
    timeout_seconds: int = 30
    requires_approval: bool = False
    tags: list[str] = Field(default_factory=list)
    policy: ToolPolicy | None = None


class ToolInvokeRequest(BaseModel):
    payload: dict = Field(..., description="Arguments to pass to the tool")


class ToolInvocationRecord(BaseModel):
    run_id: str
    tool_name: str
    request_payload: dict
    response_payload: dict | None = None
    status: str
    latency_ms: int | None = None
    error: dict | None = None
