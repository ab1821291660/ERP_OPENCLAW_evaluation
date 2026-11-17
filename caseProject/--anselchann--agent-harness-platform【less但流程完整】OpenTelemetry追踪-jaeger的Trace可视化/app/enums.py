from enum import StrEnum


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvalStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolInvocationStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    DENIED = "denied"


class TaskType(StrEnum):
    CUSTOMER_SUPPORT = "customer_support"
    CODE_REVIEW = "code_review"
    DATA_ANALYSIS = "data_analysis"
    GENERAL = "general"
