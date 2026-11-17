from datetime import datetime

from pydantic import BaseModel, Field


class EvalRunRequest(BaseModel):
    agent_name: str
    dataset_name: str
    candidate_config: dict = Field(default_factory=dict)
    baseline_config: dict = Field(default_factory=dict)
    evaluators: list[str] = Field(
        default_factory=lambda: ["json_validity", "tool_success", "rubric_judge"]
    )


class EvalRunCreated(BaseModel):
    eval_id: str
    status: str = "queued"


class EvalRunResponse(BaseModel):
    eval_id: str
    dataset_name: str
    status: str
    summary: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatasetCase(BaseModel):
    case_id: str
    task_type: str
    input: dict
    expected: dict
    metadata: dict = Field(default_factory=dict)
