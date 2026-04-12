"""Stage 3 node — Scope of Work drafting and revision."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from agent.llm import complete_text
from agent.prompts.sow import DRAFT_SYSTEM, DRAFT_USER, REVISE_SYSTEM, REVISE_USER
from agent.state import PipelineState

logger = logging.getLogger(__name__)


def _format_qa(questions: list[dict]) -> str:
    """Format Q&A into a readable string for the SoW prompt."""
    lines = []
    for q in questions:
        if q["status"] == "answered":
            lines.append(f"Q: {q['question']}\nA: {q['answer']}")
        elif q["status"] == "skipped":
            lines.append(f"Q: {q['question']}\nA: [Skipped — {q.get('skip_reason', 'no reason given')}]")
    return "\n\n".join(lines) if lines else "No clarification questions were answered."


def draft_sow(state: PipelineState) -> dict:
    """Draft the initial Scope of Work from Stage 1 + Stage 2 outputs."""
    logger.info("Drafting Scope of Work...")

    messages = [
        {"role": "system", "content": DRAFT_SYSTEM},
        {
            "role": "user",
            "content": DRAFT_USER.format(
                extraction=json.dumps(state["extraction"], indent=2),
                qa=_format_qa(state["questions"]),
                transcript=state["raw_transcript"],
            ),
        },
    ]

    sow_text = complete_text(messages)

    return {
        "sow": sow_text,
        "sow_version": 1,
        "current_stage": "sow",
        "messages": [
            AIMessage(
                content=(
                    "I've drafted the Scope of Work (v1). Please review it. "
                    "Type your feedback and I'll revise. "
                    "Type 'approve' when you're happy with it."
                )
            )
        ],
    }


def revise_sow(state: PipelineState) -> dict:
    """Revise the SoW based on user feedback."""
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_messages:
        return {}

    feedback = user_messages[-1].content
    current_version = state["sow_version"]

    logger.info("Revising SoW (v%d) with feedback: %s", current_version, feedback[:80])

    messages = [
        {"role": "system", "content": REVISE_SYSTEM},
        {
            "role": "user",
            "content": REVISE_USER.format(
                version=current_version,
                sow=state["sow"],
                feedback=feedback,
            ),
        },
    ]

    revised_sow = complete_text(messages)
    new_version = current_version + 1

    # Extract changelog section from the revised SoW for the revision history
    changelog = ""
    if "## Changelog" in revised_sow:
        changelog = revised_sow.split("## Changelog", 1)[1].strip()

    return {
        "sow": revised_sow,
        "sow_version": new_version,
        "sow_revisions": [{"version": new_version, "feedback": feedback, "changelog": changelog}],
        "messages": [
            AIMessage(
                content=(
                    f"SoW updated to v{new_version}. "
                    "Review the changes and type more feedback, or 'approve' to proceed to sprint planning."
                )
            )
        ],
    }
