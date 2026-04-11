"""LangGraph pipeline — the main graph definition.

Currently implements Stage 1 (Parse & Extract) with human-in-the-loop.
Stages 2-5 will be added incrementally.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from agent.nodes.parse import apply_corrections, parse_transcript
from agent.state import PipelineState


def human_review(state: PipelineState) -> Command[Literal["apply_corrections", "parse_complete"]]:
    """Human-in-the-loop review node.

    Pauses the graph and waits for user input.
    The user can either:
    - Provide a correction (routes to apply_corrections)
    - Approve the extraction (routes to parse_complete)
    """
    # interrupt() pauses the graph and waits for user to resume with input
    user_input = interrupt(
        {
            "type": "review",
            "stage": "parse",
            "extraction": state["extraction"],
            "message": (
                "Please review the extraction above.\n"
                "- Type a correction to update (e.g., 'Change Returns module priority to High')\n"
                "- Type 'approve' to accept and move to the next stage"
            ),
        }
    )

    # User's response comes back as the interrupt value
    if isinstance(user_input, str) and user_input.strip().lower() == "approve":
        return Command(goto="parse_complete")
    else:
        # Route to correction — add user message to state
        return Command(
            goto="apply_corrections",
            update={
                "messages": [HumanMessage(content=str(user_input))],
            },
        )


def parse_complete(state: PipelineState) -> dict:
    """Mark Stage 1 as complete."""
    return {
        "stage1_approved": True,
        "current_stage": "clarify",  # Ready for next stage
    }


def build_graph() -> StateGraph:
    """Build and compile the pipeline graph.

    Current flow (Stage 1):

        parse_transcript → human_review ↔ apply_corrections
                                ↓ (approve)
                          parse_complete → END
    """
    builder = StateGraph(PipelineState)

    # ── Add nodes ──
    builder.add_node("parse_transcript", parse_transcript)
    builder.add_node("human_review", human_review)
    builder.add_node("apply_corrections", apply_corrections)
    builder.add_node("parse_complete", parse_complete)

    # ── Wire edges ──
    builder.set_entry_point("parse_transcript")

    # After parsing → go to human review
    builder.add_edge("parse_transcript", "human_review")

    # After corrections → back to human review (loop)
    builder.add_edge("apply_corrections", "human_review")

    # parse_complete → END (for now; later this will → Stage 2)
    builder.add_edge("parse_complete", END)

    return builder.compile()


# The compiled graph — this is what LangGraph CLI/server picks up
graph = build_graph()
