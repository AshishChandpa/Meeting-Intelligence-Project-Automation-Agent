"""Stage 1 nodes — Transcript Parsing & Requirement Extraction."""

from __future__ import annotations

import json
import logging
import re

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


_GENERIC_NAME_VALUES = {
    "",
    "client",
    "unknown",
    "n/a",
    "na",
    "team member 1",
    "team member 2",
    "team member 3",
    "unidentified speaker",
    "abc corporation",
    "xyz development team",
    "abc company",
    "john doe",
}


def _is_generic_name(value: str | None) -> bool:
    return (value or "").strip().lower() in _GENERIC_NAME_VALUES


def _extract_discovery_header(transcript: str) -> tuple[str, str]:
    """Extract '<vendor> / <client-or-project> Discovery' style hints from transcript header."""
    header = "\n".join(transcript.splitlines()[:8])
    match = re.search(
        r"(?im)^\s*([^\n/]{2,80})\s*/\s*([^\n]{2,120}?)\s+Discovery\b",
        header,
    )
    if not match:
        return "", ""
    return match.group(1).strip(), match.group(2).strip()


def _extract_named_product_hint(transcript: str) -> str:
    """Find explicit product naming lines like 'name ... is my money mate'."""
    patterns = [
        r"(?i)name\s*,?\s*i'?m\s+thinking\s+is\s+([a-z0-9][a-z0-9\s\-]{2,60})",
        r"(?i)name\s+is\s+([a-z0-9][a-z0-9\s\-]{2,60})",
        r"(?i)calling\s+it\s+([a-z0-9][a-z0-9\s\-]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, transcript)
        if match:
            candidate = match.group(1).strip(" .,:;\"'")
            # Filter out accidental long phrase captures.
            if len(candidate.split()) > 6:
                continue
            return candidate
    return ""


def _extract_client_org_hint(transcript: str) -> str:
    """Extract explicit client org mention patterns from transcript text."""
    patterns = [
        r"(?i)our\s+own\s+business\s+([a-z0-9][a-z0-9\s\-]{2,60})",
        r"(?i)clients?\s+for\s+([a-z0-9][a-z0-9\s\-]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, transcript)
        if match:
            candidate = match.group(1).strip(" .,:;\"'")
            candidate = re.split(r"\b(for|with|that|which|who|where)\b", candidate, maxsplit=1)[0].strip()
            # Keep concise org names; discard accidental long captures.
            if 1 <= len(candidate.split()) <= 5:
                return candidate
    return ""


def _value_mentioned_in_transcript(value: str | None, transcript: str) -> bool:
    candidate = (value or "").strip()
    if not candidate:
        return False
    return candidate.lower() in transcript.lower()


def _to_title_case_if_lower(value: str) -> str:
    """Convert all-lowercase multi-word names to title case for cleaner display."""
    cleaned = (value or "").strip()
    if not cleaned:
        return cleaned
    if cleaned == cleaned.lower() and len(cleaned.split()) > 1:
        return " ".join(part.capitalize() for part in cleaned.split())
    return cleaned


def _bootstrap_requirements_from_context(extraction: dict, context: dict | None) -> dict:
    """Build/augment requirement coverage from client statements when output is sparse."""
    requirements = extraction.get("requirements", [])
    existing_count = len(requirements)

    # Only augment when extraction is weak for planning input quality.
    if existing_count >= 8:
        return extraction

    client_reqs = (context or {}).get("client_requirements", [])
    if not client_reqs:
        return extraction

    generated_requirements = list(requirements)
    seen = set()
    for req in requirements:
        key = ((req.get("module") or "").strip().lower(), (req.get("description") or "").strip().lower())
        if key != ("", ""):
            seen.add(key)

    target_count = 10

    for item in client_reqs[:18]:
        if len(generated_requirements) >= target_count:
            break

        text = re.sub(r"^\[[^\]]+\]\s*", "", item).strip()
        if len(text) < 25:
            continue

        lowered = text.lower()
        if any(term in lowered for term in ("cashflow", "loan", "super", "wealth", "debt", "property")):
            module = "Financial Dashboard"
        elif any(term in lowered for term in ("geofence", "location", "tour", "travel", "history", "crime", "map")):
            module = "Location Discovery"
        elif any(term in lowered for term in ("family", "legacy", "dad", "message", "video", "pass away")):
            module = "Family Legacy"
        elif any(term in lowered for term in ("api", "integration", "comparison", "bank", "platform")):
            module = "Integrations & Data"
        else:
            module = "Core Platform"

        key = (module.lower(), text.lower())
        if key in seen:
            continue
        seen.add(key)

        generated_requirements.append(
            {
                "description": text,
                "module": module,
                "type": "Functional",
                "confidence": "low" if existing_count > 0 else "medium",
            }
        )

    if generated_requirements:
        extraction["requirements"] = generated_requirements

    return extraction


def _ensure_modules_from_requirements(extraction: dict) -> dict:
    """Create minimal module entries when the model emits requirements but no modules."""
    modules = extraction.get("modules", [])
    requirements = extraction.get("requirements", [])
    if modules or not requirements:
        return extraction

    seen = set()
    generated_modules = []
    for req in requirements:
        module_name = (req.get("module") or "").strip()
        if not module_name:
            continue
        key = module_name.lower()
        if key in seen:
            continue
        seen.add(key)
        generated_modules.append(
            {
                "name": module_name,
                "description": f"Module covering requirements for {module_name}.",
                "priority": "Medium",
                "deadline": None,
                "confidence": req.get("confidence", "medium"),
            }
        )

    extraction["modules"] = generated_modules
    return extraction


def _bootstrap_integrations_from_transcript(extraction: dict, transcript: str) -> dict:
    """Add integration candidates from transcript when the model misses them."""
    if extraction.get("integrations"):
        return extraction

    lower = transcript.lower()
    candidates = []

    known_systems = [
        (
            "Domain API",
            "Property value and market data",
            ["domain api", "domain or rp data", "domain"],
        ),
        (
            "RP Data API",
            "Property valuation and history",
            ["rp data", "domain or rp data"],
        ),
        (
            "Open Banking API",
            "Bank account and transaction feeds",
            ["open banking", "transaction feeds", "integrate into their accounts"],
        ),
        (
            "Comparison Marketplace API",
            "Rate and product comparison",
            ["comparison tool", "compare the markets", "comparison marketplace"],
        ),
        (
            "Superannuation Data Source",
            "Super balance and insurance details",
            ["superannuation", "data scraping", "super fund"],
        ),
    ]

    for system, purpose, triggers in known_systems:
        if any(trigger in lower for trigger in triggers):
            candidates.append({"system": system, "purpose": purpose, "confidence": "medium"})

    # Generic API mention fallback for sparse transcripts.
    if "api" in lower and not candidates:
        candidates.append(
            {
                "system": "Third-party APIs",
                "purpose": "External data and service integrations mentioned in discovery",
                "confidence": "low",
            }
        )

    if candidates:
        extraction["integrations"] = candidates

    return extraction


def _normalize_core_names(extraction: dict, transcript: str) -> dict:
    """Apply conservative name fixes when local models return placeholders."""
    vendor_hint, right_hint = _extract_discovery_header(transcript)
    product_hint = _extract_named_product_hint(transcript)
    client_org_hint = _extract_client_org_hint(transcript)

    # If right-side header name is explicitly used as a business org, treat it as client.
    right_hint_is_client = bool(
        right_hint
        and re.search(rf"(?i)our\s+own\s+business\s+{re.escape(right_hint)}\b", transcript)
    )

    if (
        _is_generic_name(extraction.get("vendor_name"))
        or (vendor_hint and not _value_mentioned_in_transcript(extraction.get("vendor_name"), transcript))
    ) and vendor_hint:
        extraction["vendor_name"] = vendor_hint

    if (
        _is_generic_name(extraction.get("client_name"))
        or (client_org_hint and not _value_mentioned_in_transcript(extraction.get("client_name"), transcript))
    ) and client_org_hint:
        extraction["client_name"] = client_org_hint
    elif (
        (_is_generic_name(extraction.get("client_name")) or not _value_mentioned_in_transcript(extraction.get("client_name"), transcript))
        and right_hint_is_client
    ):
        extraction["client_name"] = right_hint

    if (
        _is_generic_name(extraction.get("project_name"))
        or (product_hint and not _value_mentioned_in_transcript(extraction.get("project_name"), transcript))
    ) and product_hint:
        extraction["project_name"] = product_hint
    elif (
        (_is_generic_name(extraction.get("project_name")) or not _value_mentioned_in_transcript(extraction.get("project_name"), transcript))
        and right_hint
    ):
        extraction["project_name"] = right_hint

    extraction["project_name"] = _to_title_case_if_lower(extraction.get("project_name", ""))

    # If client is still not transcript-grounded, keep it empty instead of hallucinated names.
    if extraction.get("client_name") and not _value_mentioned_in_transcript(extraction.get("client_name"), transcript):
        extraction["client_name"] = ""

    extraction["client_name"] = _to_title_case_if_lower(extraction.get("client_name", ""))

    # Prefer short, header-based project names for discovery transcripts.
    if right_hint and len(right_hint.split()) <= 4 and "discovery" not in right_hint.lower():
        if _is_generic_name(extraction.get("project_name")) or not _value_mentioned_in_transcript(extraction.get("project_name"), transcript):
            extraction["project_name"] = right_hint

    return extraction


def _build_context_block(context: dict | None) -> str:
    """Create a compact context block that helps smaller local models stay on-track."""
    if not context:
        return "- No preprocessing hints available."

    client_reqs = context.get("client_requirements", [])
    speaker_summary = context.get("speaker_summary", {})
    top_speakers = sorted(
        speaker_summary.items(),
        key=lambda item: item[1].get("segment_count", 0),
        reverse=True,
    )[:5]

    lines = [
        f"- strategy: {context.get('strategy', 'unknown')}",
        f"- detected_client_requirement_snippets: {len(client_reqs)}",
    ]

    for idx, item in enumerate(client_reqs[:10], start=1):
        lines.append(f"  - client_req_{idx}: {item}")

    if top_speakers:
        lines.append("- speaker_activity:")
        for speaker, stats in top_speakers:
            lines.append(
                f"  - {speaker}: {stats.get('segment_count', 0)} segments, "
                f"{stats.get('word_count', 0)} words"
            )

    return "\n".join(lines)


def _build_focused_transcript(segments: list, max_chars: int = 14000) -> str:
    """Compress transcript to high-signal lines for smaller local models."""
    if not segments:
        return ""

    requirement_terms = (
        "app",
        "platform",
        "module",
        "feature",
        "api",
        "integration",
        "timeline",
        "deadline",
        "budget",
        "sprint",
        "should",
        "need",
        "want",
    )

    chosen = []

    # Keep opening context for naming and project framing.
    chosen.extend(segments[:6])

    # Prioritize client statements and requirement-heavy lines.
    for seg in segments:
        content_lower = seg.content.lower()
        is_client = "client" in seg.speaker.lower()
        has_signal = any(term in content_lower for term in requirement_terms)
        if is_client or has_signal:
            chosen.append(seg)

    # Remove duplicates while preserving order.
    deduped = []
    seen = set()
    for seg in chosen:
        key = (seg.timestamp, seg.speaker, seg.content)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(seg)

    lines = []
    char_count = 0
    for seg in deduped:
        block = f"[{seg.timestamp}] {seg.speaker}: {seg.content}".strip()
        new_len = char_count + len(block) + 1
        if new_len > max_chars:
            break
        lines.append(block)
        char_count = new_len

    return "\n".join(lines)


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

    focused_transcript = _build_focused_transcript(segments)

    # Choose strategy based on transcript length
    if len(segments) > 50:  # Long transcript (>25 min approx)
        logger.info("Using topic-based preprocessing for long transcript")
        context = preprocessor.create_extraction_context(transcript, strategy='topic')
        transcript_for_llm = focused_transcript or transcript
    else:
        logger.info("Using direct extraction for shorter transcript")
        context = preprocessor.create_extraction_context(transcript, strategy='full')
        transcript_for_llm = focused_transcript or transcript

    context_block = _build_context_block(context)

    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM},
        {
            "role": "user",
            "content": EXTRACTION_USER.format(
                transcript=transcript_for_llm,
                context_block=context_block,
            ),
        },
    ]

    validated: Extraction = complete_structured(messages, schema=Extraction)

    # Retry once with full transcript if model returns an empty extraction.
    if not validated.modules and not validated.requirements:
        logger.warning("Primary extraction came back empty; retrying with full transcript")
        retry_messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": EXTRACTION_USER.format(
                    transcript=transcript,
                    context_block=context_block,
                ),
            },
        ]
        validated = complete_structured(retry_messages, schema=Extraction)

    # Apply deduplication to remove duplicate requirements
    extraction_dict = validated.model_dump()
    extraction_dict = _normalize_core_names(extraction_dict, transcript)
    extraction_dict = _bootstrap_requirements_from_context(extraction_dict, context)
    extraction_dict = _ensure_modules_from_requirements(extraction_dict)
    extraction_dict = _bootstrap_integrations_from_transcript(extraction_dict, transcript)
    extraction_dict = deduplicate_requirements(extraction_dict)

    # Re-validate the deduplication didn't break schema
    validated = Extraction(**extraction_dict)

    # Store preprocessing context for later use
    context = context or {}
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

