"""Stage 1 nodes — Transcript Parsing & Requirement Extraction."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from agent.llm import complete_structured, complete_text
from agent.prompts.extraction_enhanced import (
    CORRECTION_SYSTEM,
    CORRECTION_USER,
    EXTRACTION_SYSTEM,
    EXTRACTION_USER,
    GAP_ANALYSIS_SYSTEM,
    GAP_ANALYSIS_USER,
)
from agent.state import Extraction, PipelineState
from agent.transcript_preprocessor import TranscriptPreprocessor

logger = logging.getLogger(__name__)


def deduplicate_requirements(extraction: dict) -> dict:
    """Remove duplicate requirements from extraction.

    This function deduplicates based on:
    1. Exact description match
    2. Same module + similar description (80% similarity threshold)
    3. Same functional intent

    Args:
        extraction: The extraction dict with potential duplicates

    Returns:
        Cleaned extraction dict with unique requirements
    """
    requirements = extraction.get("requirements", [])
    if not requirements:
        return extraction

    seen_descriptions = set()
    unique_requirements = []
    duplicates_removed = 0

    for req in requirements:
        desc = req.get("description", "").strip().lower()

        # Check for exact match
        if desc in seen_descriptions:
            duplicates_removed += 1
            continue

        # Check for similar descriptions in same module
        is_duplicate = False
        req_module = req.get("module", "")
        for seen_req in unique_requirements:
            if (seen_req.get("module", "") == req_module and
                _similarity(desc, seen_req.get("description", "").lower()) > 0.8):
                duplicates_removed += 1
                is_duplicate = True
                break

        if not is_duplicate:
            seen_descriptions.add(desc)
            unique_requirements.append(req)

    if duplicates_removed > 0:
        logger.info(f"Removed {duplicates_removed} duplicate requirements. "
                   f"Original: {len(requirements)}, Unique: {len(unique_requirements)}")

    extraction["requirements"] = unique_requirements
    return extraction


def _similarity(str1: str, str2: str) -> float:
    """Calculate simple similarity ratio between two strings.

    Uses a basic word overlap approach.
    """
    words1 = set(str1.split())
    words2 = set(str2.split())

    if not words1 or not words2:
        return 0.0

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    return len(intersection) / len(union) if union else 0.0


def parse_transcript(state: PipelineState) -> dict:
    """Parse the raw transcript and extract structured requirements."""
    transcript = state["raw_transcript"]
    if not transcript.strip():
        raise ValueError("No transcript provided.")

    logger.info("Parsing transcript (%d chars)...", len(transcript))

    # Preprocess transcript for better extraction
    preprocessor = TranscriptPreprocessor()
    segments = preprocessor.parse_transcript(transcript)

    # Choose strategy based on transcript length
    if len(segments) > 50:  # Long transcript (>25 min approx)
        logger.info("Using topic-based preprocessing for long transcript")
        context = preprocessor.create_extraction_context(transcript, strategy='topic')
        client_requirements = "\n".join(context['client_requirements'][:20])  # First 20
        speaker_summary = json.dumps(context['speaker_summary'], indent=2)
        transcript_for_llm = transcript  # Still pass full, but with context
    else:
        logger.info("Using direct extraction for shorter transcript")
        context = None
        client_requirements = ""
        speaker_summary = ""
        transcript_for_llm = transcript

    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM},
        {"role": "user", "content": EXTRACTION_USER.format(transcript=transcript_for_llm)},
    ]

    validated: Extraction = complete_structured(messages, schema=Extraction)

    # Apply deduplication to remove duplicate requirements
    extraction_dict = validated.model_dump()
    extraction_dict = deduplicate_requirements(extraction_dict)

    # Re-validate the deduplication didn't break schema
    validated = Extraction(**extraction_dict)

    # Store preprocessing context for later use
    return {
        "extraction": validated.model_dump(),
        "preprocessing_context": context or {},
        "current_stage": "parse",
        "messages": [
            AIMessage(
                content=(
                    f"📊 Parsed transcript ({len(segments)} segments). "
                    f"Found {len(validated.modules)} modules, "
                    f"{len(validated.requirements)} unique requirements, "
                    f"{len(validated.integrations)} integrations, "
                    f"{len(validated.unknowns)} unknowns. "
                    f"Identified {len(context.get('client_requirements', []))} client statements.\n\n"
                    "Please review the extraction and provide corrections if needed."
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

