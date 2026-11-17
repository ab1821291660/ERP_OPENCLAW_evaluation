from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentRunState(TypedDict):
    run_id: str
    task_type: str
    user_input: dict
    context: dict
    messages: Annotated[list[BaseMessage], add_messages]
    tool_calls: list
    intermediate_results: list
    final_output: dict | None
    status: str
    error: dict | None
