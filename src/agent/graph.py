"""LangGraph pipeline — full 5-stage meeting intelligence graph.

Flow:
    Stage 1: parse_transcript → human_review → (correct | approve)
    Stage 2: generate_questions → clarify_review → (answer | done)
    Stage 3: draft_sow → sow_review → (feedback | approve)
    Stage 4: generate_sprint_plan → sprint_review → (adjust | approve)
    Stage 5: sync_to_jira → END
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from agent.config import settings
from agent.nodes.clarify import generate_questions, process_answer
from agent.nodes.jira_sync import (
    create_epics_batch,
    create_issues_batch,
    create_sprints_batch,
    prepare_jira_batch_preview,
    sync_to_jira,
)
from agent.nodes.parse import apply_corrections, parse_transcript
from agent.nodes.sow import draft_sow, revise_sow
from agent.nodes.sprint import adjust_sprint_plan, generate_sprint_plan
from agent.state import PipelineState


# ── Stage 1 human gate ─────────────────────────────────────────────────

def review_extraction(state: PipelineState) -> Command[Literal["apply_corrections", "stage1_done"]]:
    """Pause for human review of the transcript extraction.

    User can:
    - 'approve' - proceed to next stage
    - Provide manual correction text
    """
    user_input = interrupt({
        "stage": "parse",
        "message": (
            "Please review the extraction.\n\n"
            "Options:\n"
            "- Type 'approve' to continue to next stage\n"
            "- Type your own corrections to specify changes"
        ),
        "extraction": state["extraction"],
    })

    input_str = str(user_input).strip().lower()

    # Approve command
    if input_str == "approve":
        return Command(goto="stage1_done")

    # Manual correction
    return Command(
        goto="apply_corrections",
        update={"messages": [HumanMessage(content=str(user_input))]},
    )


def stage1_done(state: PipelineState) -> dict:
    return {"stage1_approved": True, "current_stage": "clarify"}


# ── Stage 2 human gate ─────────────────────────────────────────────────

def review_clarification(state: PipelineState) -> Command[Literal["process_answer", "stage2_done"]]:
    """Pause for human to answer questions or mark clarification done."""
    open_qs = [q for q in state["questions"] if q["status"] == "open"]
    user_input = interrupt({
        "stage": "clarify",
        "message": (
            f"{len(open_qs)} questions remaining. "
            "Reply '<id>: <answer>' to answer, '<id>: skip <reason>' to skip, "
            "or 'done' to proceed."
        ),
        "questions": state["questions"],
    })
    if isinstance(user_input, str) and user_input.strip().lower() == "done":
        return Command(goto="stage2_done")
    return Command(
        goto="process_answer",
        update={"messages": [HumanMessage(content=str(user_input))]},
    )


def stage2_done(state: PipelineState) -> dict:
    return {"stage2_approved": True, "current_stage": "sow"}


# ── Stage 3 human gate ─────────────────────────────────────────────────

def review_sow(state: PipelineState) -> Command[Literal["revise_sow", "stage3_done"]]:
    """Pause for human review of the Scope of Work."""
    version = state["sow_version"]
    # Require at least one feedback round before approving
    has_revision = len(state["sow_revisions"]) > 0
    user_input = interrupt({
        "stage": "sow",
        "message": (
            f"SoW v{version} ready. "
            + ("" if has_revision else "Please provide at least one round of feedback before approving. ")
            + "Type feedback to revise, or 'approve' to proceed."
        ),
        "sow": state["sow"],
        "version": version,
    })
    if (
        isinstance(user_input, str)
        and user_input.strip().lower() == "approve"
        and has_revision
    ):
        return Command(goto="stage3_done")
    return Command(
        goto="revise_sow",
        update={"messages": [HumanMessage(content=str(user_input))]},
    )


def stage3_done(state: PipelineState) -> dict:
    return {"stage3_approved": True, "current_stage": "sprint"}


# ── Stage 4 human gate ─────────────────────────────────────────────────

def review_sprint(state: PipelineState) -> Command[Literal["adjust_sprint_plan", "stage4_done"]]:
    """Pause for human review of the sprint plan."""
    user_input = interrupt({
        "stage": "sprint",
        "message": "Review the sprint plan. Request adjustments or type 'approve' to sync to Jira.",
        "sprints": state["sprints"],
        "tasks": state["tasks"],
        "warnings": state["sprint_warnings"],
    })
    if isinstance(user_input, str) and user_input.strip().lower() == "approve":
        return Command(goto="stage4_done")
    return Command(
        goto="adjust_sprint_plan",
        update={"messages": [HumanMessage(content=str(user_input))]},
    )


def stage4_done(state: PipelineState) -> dict:
    return {"stage4_approved": True, "current_stage": "jira"}


# ── Stage 5 graphized batch flow ───────────────────────────────────────

def preview_jira_epics(state: PipelineState) -> dict:
    return prepare_jira_batch_preview(state, "epics")


def preview_jira_issues(state: PipelineState) -> dict:
    return prepare_jira_batch_preview(state, "issues")


def preview_jira_sprints(state: PipelineState) -> dict:
    return prepare_jira_batch_preview(state, "sprints")


def _review_jira_batch(state: PipelineState, batch: Literal["epics", "issues", "sprints"], goto_node: str):
    cfg = state.get("jira_config") or settings.jira_config_from_env
    preview = state.get("jira_preview") or {}
    user_input = interrupt(
        {
            "stage": "jira",
            "batch": batch,
            "message": f"Preview ready for Jira {batch}. Confirm to continue.",
            "preview": preview,
            "jira_config_required": not bool(cfg),
        }
    )

    if isinstance(user_input, dict) and "domain" in user_input:
        return Command(goto=goto_node, update={"jira_config": user_input})

    if str(user_input).strip().lower() in {batch, f"confirm {batch}", "confirm"} and cfg:
        return Command(goto=goto_node, update={"jira_config": cfg})

    return Command(goto=f"review_jira_{batch}")


def review_jira_epics(state: PipelineState) -> Command[Literal["create_jira_epics", "review_jira_epics"]]:
    return _review_jira_batch(state, "epics", "create_jira_epics")


def review_jira_issues(state: PipelineState) -> Command[Literal["create_jira_issues", "review_jira_issues"]]:
    return _review_jira_batch(state, "issues", "create_jira_issues")


def review_jira_sprints(state: PipelineState) -> Command[Literal["create_jira_sprints", "review_jira_sprints"]]:
    return _review_jira_batch(state, "sprints", "create_jira_sprints")


def stage5_done(state: PipelineState) -> dict:
    return {
        "stage5_done": True,
        "current_stage": "done",
        "messages": [AIMessage(content="Jira batch flow completed.")],
    }


# ── Graph assembly ─────────────────────────────────────────────────────

def build_graph(checkpointer=None):
    builder = StateGraph(PipelineState)

    # Stage 1
    builder.add_node("parse_transcript", parse_transcript)
    builder.add_node("review_extraction", review_extraction)
    builder.add_node("apply_corrections", apply_corrections)
    builder.add_node("stage1_done", stage1_done)

    # Stage 2
    builder.add_node("generate_questions", generate_questions)
    builder.add_node("review_clarification", review_clarification)
    builder.add_node("process_answer", process_answer)
    builder.add_node("stage2_done", stage2_done)

    # Stage 3
    builder.add_node("draft_sow", draft_sow)
    builder.add_node("review_sow", review_sow)
    builder.add_node("revise_sow", revise_sow)
    builder.add_node("stage3_done", stage3_done)

    # Stage 4
    builder.add_node("generate_sprint_plan", generate_sprint_plan)
    builder.add_node("review_sprint", review_sprint)
    builder.add_node("adjust_sprint_plan", adjust_sprint_plan)
    builder.add_node("stage4_done", stage4_done)

    # Stage 5
    builder.add_node("preview_jira_epics", preview_jira_epics)
    builder.add_node("review_jira_epics", review_jira_epics)
    builder.add_node("create_jira_epics", create_epics_batch)
    builder.add_node("preview_jira_issues", preview_jira_issues)
    builder.add_node("review_jira_issues", review_jira_issues)
    builder.add_node("create_jira_issues", create_issues_batch)
    builder.add_node("preview_jira_sprints", preview_jira_sprints)
    builder.add_node("review_jira_sprints", review_jira_sprints)
    builder.add_node("create_jira_sprints", create_sprints_batch)
    builder.add_node("stage5_done", stage5_done)
    builder.add_node("sync_to_jira", sync_to_jira)

    # ── Edges ──

    # Entry
    builder.set_entry_point("parse_transcript")

    # Stage 1 flow: parse → review → (manual correct) → review → stage1_done
    builder.add_edge("parse_transcript", "review_extraction")
    builder.add_edge("apply_corrections", "review_extraction")
    builder.add_edge("stage1_done", "generate_questions")

    # Stage 2 flow
    builder.add_edge("generate_questions", "review_clarification")
    builder.add_edge("process_answer", "review_clarification")
    builder.add_edge("stage2_done", "draft_sow")

    # Stage 3 flow
    builder.add_edge("draft_sow", "review_sow")
    builder.add_edge("revise_sow", "review_sow")
    builder.add_edge("stage3_done", "generate_sprint_plan")

    # Stage 4 flow
    builder.add_edge("generate_sprint_plan", "review_sprint")
    builder.add_edge("adjust_sprint_plan", "review_sprint")
    builder.add_edge("stage4_done", "preview_jira_epics")

    # Stage 5 flow
    builder.add_edge("preview_jira_epics", "review_jira_epics")
    builder.add_edge("preview_jira_issues", "review_jira_issues")
    builder.add_edge("preview_jira_sprints", "review_jira_sprints")
    builder.add_edge("stage5_done", END)
    builder.add_edge("sync_to_jira", END)

    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()


graph = build_graph()
