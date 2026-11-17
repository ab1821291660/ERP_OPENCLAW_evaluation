"""
LangGraph workflow graph definition.

Builds a StateGraph with conditional routing for tool calls.

Flow:
    prepare_context -> plan -> select_tool ──> invoke_tool ──┐
                                    │                         │
                                    └──> synthesize_answer <──┘
                                               │
                                         validate_output -> finish
"""

from langgraph.graph import StateGraph, END

from app.runtime.state import AgentRunState
from app.runtime.nodes import (
    prepare_context,
    plan,
    select_tool,
    invoke_tool,
    synthesize_answer,
    validate_output,
    finish,
)


def build_agent_graph() -> StateGraph:
    builder = StateGraph(AgentRunState)

    builder.add_node("prepare_context", prepare_context)
    builder.add_node("plan", plan)
    builder.add_node("invoke_tool", invoke_tool)
    builder.add_node("synthesize_answer", synthesize_answer)
    builder.add_node("validate_output", validate_output)
    builder.add_node("finish", finish)

    builder.set_entry_point("prepare_context")
    builder.add_edge("prepare_context", "plan")

    builder.add_conditional_edges(
        "plan",
        select_tool,
        {
            "invoke_tool": "invoke_tool",
            "synthesize_answer": "synthesize_answer",
        },
    )
    builder.add_edge("invoke_tool", "synthesize_answer")
    builder.add_edge("synthesize_answer", "validate_output")
    builder.add_edge("validate_output", "finish")
    builder.add_edge("finish", END)

    return builder.compile()


agent_graph = build_agent_graph()
