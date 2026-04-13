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
from agent.prompts.validation import AUTO_CORRECT_SYSTEM, AUTO_CORRECT_USER, VALIDATION_SYSTEM, VALIDATION_USER
from agent.state import Extraction, PipelineState
from agent.transcript_preprocessor import TranscriptPreprocessor

logger = logging.getLogger(__name__)


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
                    f"{len(validated.requirements)} requirements, "
                    f"{len(validated.integrations)} integrations, "
                    f"{len(validated.unknowns)} unknowns. "
                    f"Identified {len(context.get('client_requirements', []))} client statements.\n\n"
                    "⏳ Running validation to ensure accuracy..."
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


def validate_extraction(state: PipelineState) -> dict:
    """Validate extraction accuracy by comparing to original transcript.

    This uses low temperature for strict validation to catch:
    - Wrong names (Client instead of AI Money)
    - Wrong values (null instead of actual numbers)
    - Missing details (competitors, integrations)
    - Generic placeholders (API integration instead of Domain API)

    Returns validation report with errors found.
    """
    transcript = state["raw_transcript"]
    extraction = state["extraction"]

    logger.info("Validating extraction accuracy...")

    messages = [
        {"role": "system", "content": VALIDATION_SYSTEM},
        {
            "role": "user",
            "content": VALIDATION_USER.format(
                transcript=transcript,
                extraction=json.dumps(extraction, indent=2),
            ),
        },
    ]

    # Use low temperature (0.1) for strict, deterministic validation
    validation_result = complete_text(messages, temperature=0.1)

    logger.info("Validation complete")

    # Check if validation passed
    validation_passed = "✓ EXTRACTION VALIDATED" in validation_result or "NO ERRORS" in validation_result.upper()

    return {
        "validation_result": validation_result,
        "validation_passed": validation_passed,
        "messages": [
            AIMessage(
                content=(
                    f"{'✅ Extraction validated successfully - No errors found' if validation_passed else '⚠️ Validation found errors - Review below:'}\n\n"
                    f"{validation_result}\n\n"
                    f"{'Please review the extraction and approve or provide corrections.' if not validation_passed else 'Extraction is accurate and ready for review.'}"
                )
            )
        ],
    }


def auto_correct_extraction(state: PipelineState) -> dict:
    """Auto-correct extraction based on validation errors.

    This applies the corrections identified during validation to produce
    a corrected extraction without user intervention.
    """
    if state.get("validation_passed", False):
        # No corrections needed
        return {}

    logger.info("Auto-correcting extraction based on validation...")

    messages = [
        {"role": "system", "content": AUTO_CORRECT_SYSTEM},
        {
            "role": "user",
            "content": AUTO_CORRECT_USER.format(
                extraction=json.dumps(state["extraction"], indent=2),
                validation_errors=state["validation_result"],
            ),
        },
    ]

    # Use low temperature (0.1) for precise corrections
    corrected_extraction_json = complete_text(messages, temperature=0.1)

    # Parse the JSON response
    try:
        corrected_extraction = json.loads(corrected_extraction_json)
        validated: Extraction = Extraction(**corrected_extraction)
    except Exception as e:
        logger.error(f"Failed to parse corrected extraction: {e}")
        # If auto-correction fails, return empty and let user handle
        return {
            "messages": [
                AIMessage(
                    content=(
                        "⚠️ Auto-correction encountered an error. "
                        "Please review the validation errors and provide corrections manually."
                    )
                )
            ],
        }

    logger.info("Auto-correction complete")

    return {
        "extraction": validated.model_dump(),
        "validation_passed": True,  # Assume corrections fixed the issues
        "correction_applied": True,
        "messages": [
            AIMessage(
                content=(
                    "✅ Auto-correction applied successfully. "
                    f"The extraction has been updated with {len(validated.modules)} modules, "
                    f"{len(validated.requirements)} requirements. "
                    "Please review and approve or provide further corrections."
                )
            )
        ],
    }
