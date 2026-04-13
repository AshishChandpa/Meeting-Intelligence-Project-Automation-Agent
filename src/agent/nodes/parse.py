"""Stage 1 nodes — Transcript Parsing & Requirement Extraction."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from agent.llm import complete_structured
from agent.prompts.extraction_enhanced import (
    CORRECTION_SYSTEM,
    CORRECTION_USER,
    EXTRACTION_SYSTEM,
    EXTRACTION_USER,
    GAP_ANALYSIS_SYSTEM,
    GAP_ANALYSIS_USER,
)
from agent.state import Extraction, PipelineState

logger = logging.getLogger(__name__)


def parse_transcript(state: PipelineState) -> dict:
    """Parse the raw transcript and extract structured requirements."""
    transcript = state["raw_transcript"]
    if not transcript.strip():
        raise ValueError("No transcript provided.")

    logger.info("Parsing transcript (%d chars)...", len(transcript))

    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM},
        {"role": "user", "content": EXTRACTION_USER.format(transcript=transcript)},
    ]

    validated: Extraction = complete_structured(messages, schema=Extraction)

    return {
        "extraction": validated.model_dump(),
        "current_stage": "parse",
        "messages": [
            AIMessage(
                content=(
                    f"Parsed transcript. Found {len(validated.modules)} modules, "
                    f"{len(validated.requirements)} requirements, "
                    f"{len(validated.integrations)} integrations, "
                    f"{len(validated.unknowns)} unknowns. "
                    "Review and correct, or type 'approve' to continue."
                )
            )
        ],
    }


def apply_corrections(state: PipelineState) -> dict:
    """Apply user's plain-language corrections to the extraction."""
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_messages:
        return {}

    correction = user_messages[-1].content
    current_extraction = state["extraction"]

    logger.info("Applying correction: %s", correction[:100])

    messages = [
        {"role": "system", "content": CORRECTION_SYSTEM},
        {
            "role": "user",
            "content": CORRECTION_USER.format(
                extraction=json.dumps(current_extraction, indent=2),
                correction=correction,
            ),
        },
    ]

    validated: Extraction = complete_structured(messages, schema=Extraction)

    return {
        "extraction": validated.model_dump(),
        "correction_history": [{"correction": correction}],
        "messages": [
            AIMessage(
                content=(
                    f"Applied correction: \"{correction}\". "
                    "Review again or type 'approve' to continue."
                )
            )
        ],
    }


def analyze_gaps(state: PipelineState) -> dict:
    """Analyze the extraction for gaps and generate targeted questions.

    This is called after parse_transcript to identify missing information
    before moving to clarification stage.
    """
    messages = [
        {"role": "system", "content": GAP_ANALYSIS_SYSTEM},
        {
            "role": "user",
            "content": GAP_ANALYSIS_USER.format(
                transcript=state["raw_transcript"],
                extraction=json.dumps(state["extraction"], indent=2),
            ),
        },
    ]

    # Use text completion for gap analysis questions
    from agent.llm import complete_text
    gap_questions = complete_text(messages)

    logger.info("Generated gap analysis questions")

    return {
        "gap_questions": gap_questions,
        "messages": [
            AIMessage(
                content=(
                    "I've identified gaps and questions based on the extraction:\n\n"
                    f"{gap_questions}\n\n"
                    "These questions will be addressed in the clarification stage."
                )
            )
        ],
    }
