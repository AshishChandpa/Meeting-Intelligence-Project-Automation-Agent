"""Stage 1 nodes — Transcript Parsing & Requirement Extraction."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from agent.config import settings
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

    # Only augment when extraction is very weak (bootstrap threshold from settings).
    bootstrap_trigger = settings.extraction_sparse_requirement_threshold
    if existing_count >= max(bootstrap_trigger, 6):
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

    if context.get("chunk_window"):
        lines.append(f"- chunk_window: {context['chunk_window']}")
    if context.get("chunk_time_range"):
        lines.append(f"- chunk_time_range: {context['chunk_time_range']}")
    if context.get("chunk_segment_count"):
        lines.append(f"- chunk_segment_count: {context['chunk_segment_count']}")
    if context.get("chunk_topics"):
        lines.append(f"- chunk_topics: {', '.join(context['chunk_topics'][:6])}")
    if context.get("chunk_speakers"):
        lines.append(f"- chunk_speakers: {', '.join(context['chunk_speakers'][:6])}")
    if context.get("total_chunks"):
        lines.append(f"- total_chunks: {context['total_chunks']}")

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


_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _normalize_key(value: str | None) -> str:
    """Normalize a string for fuzzy comparison: lowercase, collapse whitespace/punctuation, strip common plural forms."""
    text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower())).strip()
    # Strip simple English plural/verb suffixes from words ≥ 4 chars so
    # "upload" and "uploads", "document" and "documents" hash to the same key.
    words = []
    for word in text.split():
        if len(word) >= 5 and word.endswith("s"):
            words.append(word[:-1])
        elif len(word) >= 6 and word.endswith("ing"):
            words.append(word[:-3])
        else:
            words.append(word)
    return " ".join(words)


def _confidence_rank(value: str | None) -> int:
    return _CONFIDENCE_RANK.get((value or "").strip().lower(), -1)


def _prefer_richer_item(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    existing_score = sum(1 for value in existing.values() if value not in (None, "", [], {}))
    candidate_score = sum(1 for value in candidate.values() if value not in (None, "", [], {}))
    if _confidence_rank(candidate.get("confidence")) > _confidence_rank(existing.get("confidence")):
        return candidate
    if candidate_score > existing_score:
        return candidate
    return existing


def _merge_named_records(records: list[dict], key_field: str, *, merge_fields: list[str] | None = None) -> list[dict]:
    merge_fields = merge_fields or []
    merged: dict[str, dict[str, Any]] = {}

    for record in records:
        key = _normalize_key(record.get(key_field, ""))
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(record)
            continue

        chosen = _prefer_richer_item(merged[key], record)
        other = record if chosen is merged[key] else merged[key]
        merged[key] = dict(chosen)
        for field in merge_fields:
            if not merged[key].get(field) and other.get(field):
                merged[key][field] = other[field]

    return list(merged.values())


def _deduplicate_simple_records(records: list[dict], text_field: str, *, similarity_threshold: float = 0.82) -> list[dict]:
    unique: list[dict] = []
    for record in records:
        text = (record.get(text_field) or "").strip()
        if not text:
            continue
        normalized = _normalize_key(text)
        duplicate_index: int | None = None
        for index, existing in enumerate(unique):
            existing_text = existing.get(text_field, "")
            existing_normalized = _normalize_key(existing_text)
            if normalized == existing_normalized or _similarity(normalized, existing_normalized) >= similarity_threshold:
                duplicate_index = index
                break

        if duplicate_index is None:
            unique.append(dict(record))
            continue

        unique[duplicate_index] = _prefer_richer_item(unique[duplicate_index], record)

    return unique


def _merge_chunk_extractions(chunk_extractions: list[dict], transcript: str) -> dict:
    merged: dict[str, Any] = {
        "project_name": "",
        "client_name": "",
        "vendor_name": "",
        "modules": [],
        "requirements": [],
        "integrations": [],
        "constraints": [],
        "assumptions": [],
        "unknowns": [],
    }

    for extraction in chunk_extractions:
        if not merged["project_name"] and extraction.get("project_name"):
            merged["project_name"] = extraction.get("project_name", "")
        if not merged["client_name"] and extraction.get("client_name"):
            merged["client_name"] = extraction.get("client_name", "")
        if not merged["vendor_name"] and extraction.get("vendor_name"):
            merged["vendor_name"] = extraction.get("vendor_name", "")

        merged["modules"].extend(extraction.get("modules", []))
        merged["requirements"].extend(extraction.get("requirements", []))
        merged["integrations"].extend(extraction.get("integrations", []))
        merged["constraints"].extend(extraction.get("constraints", []))
        merged["assumptions"].extend(extraction.get("assumptions", []))
        merged["unknowns"].extend(extraction.get("unknowns", []))

    merged["modules"] = _merge_named_records(
        merged["modules"],
        "name",
        merge_fields=["description", "deadline", "priority", "confidence"],
    )
    merged["integrations"] = _merge_named_records(
        merged["integrations"],
        "system",
        merge_fields=["purpose", "confidence"],
    )
    merged["constraints"] = _deduplicate_simple_records(merged["constraints"], "description")
    merged["assumptions"] = _deduplicate_simple_records(merged["assumptions"], "description")
    merged["unknowns"] = _deduplicate_simple_records(merged["unknowns"], "description")
    merged = _normalize_core_names(merged, transcript)
    merged = deduplicate_requirements(merged)
    return merged


def _finalize_extraction(extraction_dict: dict, transcript: str, context: dict | None) -> dict:
    extraction_dict = _normalize_core_names(extraction_dict, transcript)
    extraction_dict = _bootstrap_requirements_from_context(extraction_dict, context)
    extraction_dict = _ensure_modules_from_requirements(extraction_dict)
    extraction_dict = _bootstrap_integrations_from_transcript(extraction_dict, transcript)
    extraction_dict = deduplicate_requirements(extraction_dict)
    extraction_dict["constraints"] = _deduplicate_simple_records(extraction_dict.get("constraints", []), "description")
    extraction_dict["assumptions"] = _deduplicate_simple_records(extraction_dict.get("assumptions", []), "description")
    extraction_dict["unknowns"] = _deduplicate_simple_records(extraction_dict.get("unknowns", []), "description")
    extraction_dict["modules"] = _merge_named_records(
        extraction_dict.get("modules", []),
        "name",
        merge_fields=["description", "deadline", "priority", "confidence"],
    )
    extraction_dict["integrations"] = _merge_named_records(
        extraction_dict.get("integrations", []),
        "system",
        merge_fields=["purpose", "confidence"],
    )
    return Extraction(**extraction_dict).model_dump()


def _build_extraction_messages(transcript_excerpt: str, context_block: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM},
        {
            "role": "user",
            "content": EXTRACTION_USER.format(
                transcript=transcript_excerpt,
                context_block=context_block,
            ),
        },
    ]


def _run_structured_extraction(transcript_excerpt: str, context_block: str) -> Extraction:
    return complete_structured(_build_extraction_messages(transcript_excerpt, context_block), schema=Extraction)


def _extraction_is_sparse(extraction_dict: dict, context: dict | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    requirement_count = len(extraction_dict.get("requirements", []))
    module_count = len(extraction_dict.get("modules", []))
    client_requirement_hints = len((context or {}).get("client_requirements", []))

    if requirement_count == 0 and module_count == 0:
        reasons.append("no modules or requirements extracted")
    if client_requirement_hints >= 6 and requirement_count < settings.extraction_sparse_requirement_threshold:
        reasons.append(
            f"requirements below threshold ({requirement_count} < {settings.extraction_sparse_requirement_threshold}) despite strong client-signal hints"
        )
    if requirement_count >= 3 and module_count < settings.extraction_sparse_module_threshold:
        reasons.append(
            f"modules below threshold ({module_count} < {settings.extraction_sparse_module_threshold})"
        )

    return bool(reasons), reasons


def _extract_single_pass(transcript_excerpt: str, context: dict | None) -> Extraction:
    context_block = _build_context_block(context)
    return _run_structured_extraction(transcript_excerpt, context_block)


def _extract_chunked(transcript: str, chunks: list[dict], base_context: dict | None) -> tuple[dict, list[dict]]:
    chunk_results: list[dict] = []
    chunk_metadata: list[dict] = []

    total_chunks = len(chunks)
    for chunk in chunks:
        chunk_context = {
            **(base_context or {}),
            "strategy": "chunked",
            "chunk_window": f"{chunk['chunk_id']}/{total_chunks}",
            "chunk_time_range": chunk["time_range"],
            "chunk_topics": chunk.get("topics", []),
            "chunk_speakers": chunk.get("speakers", []),
            "chunk_segment_count": chunk.get("segment_count", 0),
            "chunk_total": total_chunks,
        }
        validated = _extract_single_pass(chunk["text"], chunk_context)
        extraction_dict = validated.model_dump()
        chunk_results.append(extraction_dict)
        chunk_metadata.append(
            {
                "chunk_id": chunk["chunk_id"],
                "time_range": chunk["time_range"],
                "segment_count": chunk.get("segment_count", 0),
                "topics": chunk.get("topics", []),
                "module_count": len(extraction_dict.get("modules", [])),
                "requirement_count": len(extraction_dict.get("requirements", [])),
                "integration_count": len(extraction_dict.get("integrations", [])),
            }
        )

    merged = _merge_chunk_extractions(chunk_results, transcript)
    return merged, chunk_metadata


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

    unique_requirements = []
    duplicates_removed = 0

    for req in requirements:
        desc = req.get("description", "").strip()
        desc_key = _normalize_key(desc)
        req_module_key = _normalize_key(req.get("module", ""))
        if not desc_key:
            continue

        duplicate_index: int | None = None
        for index, seen_req in enumerate(unique_requirements):
            seen_desc_key = _normalize_key(seen_req.get("description", ""))
            seen_module_key = _normalize_key(seen_req.get("module", ""))
            same_module = req_module_key == seen_module_key or not req_module_key or not seen_module_key
            if desc_key == seen_desc_key or (same_module and _similarity(desc_key, seen_desc_key) >= 0.78):
                duplicates_removed += 1
                duplicate_index = index
                break

        if duplicate_index is None:
            unique_requirements.append(req)
        else:
            unique_requirements[duplicate_index] = _prefer_richer_item(unique_requirements[duplicate_index], req)

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

    strategy_info = preprocessor.choose_strategy(
        transcript,
        segments,
        topic_char_threshold=settings.extraction_topic_char_threshold,
        topic_segment_threshold=settings.extraction_topic_segment_threshold,
        chunk_char_threshold=settings.extraction_chunk_char_threshold,
        chunk_segment_threshold=settings.extraction_chunk_segment_threshold,
        chunk_word_threshold=settings.extraction_chunk_word_threshold,
    )
    strategy = strategy_info["strategy"]
    focused_transcript = _build_focused_transcript(
        segments,
        max_chars=settings.extraction_focused_max_chars,
    )
    base_context = preprocessor.create_extraction_context(
        transcript,
        strategy=strategy,
        chunk_size=settings.extraction_chunk_size,
        overlap=settings.extraction_chunk_overlap,
    )
    base_context.update(
        {
            "segment_count": len(segments),
            "char_count": len(transcript),
            "word_count": len(transcript.split()),
            "strategy_reason": strategy_info.get("reason", ""),
            "thresholds": strategy_info.get("thresholds", {}),
            "fallback_strategy": "",
            "fallback_reason": "",
            "chunk_runs": [],
        }
    )

    logger.info(
        "Using %s extraction strategy (%s). segments=%d chars=%d words=%d",
        strategy,
        strategy_info.get("reason", ""),
        len(segments),
        len(transcript),
        len(transcript.split()),
    )

    extraction_dict: dict[str, Any]
    if strategy == "chunked":
        chunks = preprocessor.create_chunked_prompts(
            segments,
            chunk_size=settings.extraction_chunk_size,
            overlap=settings.extraction_chunk_overlap,
        )
        extraction_dict, chunk_metadata = _extract_chunked(transcript, chunks, base_context)
        base_context["chunk_runs"] = chunk_metadata
        base_context["total_chunks"] = len(chunks)
    else:
        transcript_for_llm = focused_transcript or transcript
        validated = _extract_single_pass(transcript_for_llm, base_context)
        extraction_dict = validated.model_dump()
        base_context["focused_chars"] = len(transcript_for_llm)

    extraction_dict = _finalize_extraction(extraction_dict, transcript, base_context)
    sparse, sparse_reasons = _extraction_is_sparse(extraction_dict, base_context)

    if sparse:
        logger.warning("Extraction considered sparse after %s strategy: %s", strategy, "; ".join(sparse_reasons))
        fallback_context = dict(base_context)
        fallback_context["strategy"] = "focused-fallback"
        fallback_context["fallback_reason"] = "; ".join(sparse_reasons)
        fallback_input = focused_transcript or transcript
        fallback_validated = _extract_single_pass(fallback_input, fallback_context)
        fallback_extraction = _finalize_extraction(fallback_validated.model_dump(), transcript, fallback_context)
        fallback_sparse, fallback_reasons = _extraction_is_sparse(fallback_extraction, fallback_context)

        if not fallback_sparse:
            extraction_dict = fallback_extraction
            base_context["fallback_strategy"] = "focused-single-pass"
            base_context["fallback_reason"] = "; ".join(sparse_reasons)
        elif len(transcript) <= settings.extraction_full_retry_char_limit:
            full_retry_context = dict(base_context)
            full_retry_context["strategy"] = "full-fallback"
            full_retry_context["fallback_reason"] = "; ".join(fallback_reasons or sparse_reasons)
            full_retry_validated = _extract_single_pass(transcript, full_retry_context)
            extraction_dict = _finalize_extraction(full_retry_validated.model_dump(), transcript, full_retry_context)
            base_context["fallback_strategy"] = "full-single-pass"
            base_context["fallback_reason"] = "; ".join(fallback_reasons or sparse_reasons)
        else:
            base_context["fallback_strategy"] = "focused-single-pass"
            base_context["fallback_reason"] = "; ".join(fallback_reasons or sparse_reasons)
            extraction_dict = fallback_extraction

    validated = Extraction(**extraction_dict)

    # Store preprocessing context for later use
    context = base_context or {}
    return {
        "extraction": validated.model_dump(),
        "preprocessing_context": context or {},
        "current_stage": "parse",
        "messages": [
            AIMessage(
                content=(
                    f"📊 Parsed transcript ({len(segments)} segments, strategy: {context.get('strategy', strategy)}). "
                    f"Found {len(validated.modules)} modules, "
                    f"{len(validated.requirements)} unique requirements, "
                    f"{len(validated.integrations)} integrations, "
                    f"{len(validated.unknowns)} unknowns. "
                    f"Identified {len(context.get('client_requirements', []))} client statements."
                    + (
                        f" Used fallback: {context.get('fallback_strategy')}."
                        if context.get('fallback_strategy')
                        else ""
                    )
                    + "\n\n"
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

