"""Stage 3 node — Scope of Work drafting and revision."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from agent.llm import complete_text
from agent.prompts.sow_enhanced import (
    DRAFT_SYSTEM,
    DRAFT_USER,
    GAP_DETECTION_SYSTEM,
    GAP_DETECTION_USER,
    REVISE_SYSTEM,
    REVISE_USER,
)
from agent.state import PipelineState

logger = logging.getLogger(__name__)


REQUIRED_SOW_SECTIONS = [
    "## Executive Summary",
    "## In-Scope Items",
    "## Out-of-Scope Items",
    "## Modules & Deliverables",
    "## Integrations",
    "## Constraints & Assumptions",
    "## Open Items",
    "## Timeline Overview",
]


def sow_missing_sections(sow: str) -> list[str]:
    missing = []
    normalized = sow or ""
    for heading in REQUIRED_SOW_SECTIONS:
        if heading not in normalized:
            missing.append(heading)
    return missing


def _ensure_sow_sections(sow: str) -> str:
    """Append placeholder sections if LLM misses required SoW headings."""
    text = sow or ""
    missing = sow_missing_sections(text)
    if not missing:
        return text

    additions = []
    for heading in missing:
        additions.append(f"{heading}\n- TO BE CONFIRMED")

    suffix = "\n\n" + "\n\n".join(additions)
    return text.rstrip() + suffix


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
    sow_text = _ensure_sow_sections(sow_text)

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
    revised_sow = _ensure_sow_sections(revised_sow)
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


def detect_sow_gaps(state: PipelineState) -> dict:
    """Detect gaps in the Scope of Work document.

    This analyzes the SoW for missing information, vague requirements,
    unclear scope, and assumptions that should be flagged.
    """
    messages = [
        {"role": "system", "content": GAP_DETECTION_SYSTEM},
        {
            "role": "user",
            "content": GAP_DETECTION_USER.format(
                sow=state["sow"],
                extraction=json.dumps(state["extraction"], indent=2),
            ),
        },
    ]

    gap_findings = complete_text(messages)

    logger.info("Detected SoW gaps")

    return {
        "sow_gaps": gap_findings,
        "messages": [
            AIMessage(
                content=(
                    "I've analyzed the Scope of Work for gaps and areas that need clarification:\n\n"
                    f"{gap_findings}\n\n"
                    "Please review these gaps and address them before approving the SoW."
                )
            )
        ],
    }
