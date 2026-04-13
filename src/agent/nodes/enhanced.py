"""Enhanced nodes with validation, error recovery, and caching."""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from time import time

from langchain_core.messages import AIMessage
from langgraph.types import Command

from agent.llm import complete_structured
from agent.state import Extraction, PipelineState

logger = logging.getLogger(__name__)

# ── 1. VALIDATION NODE ─────────────────────────────────────────────

def validate_extraction(state: PipelineState) -> Command[str]:
    """Validate extraction quality before human review."""
    extraction = state.get("extraction", {})

    issues = []
    warnings = []

    # Critical issues
    if not extraction.get("modules"):
        issues.append("No modules detected - transcript may be unclear")

    if not extraction.get("project_name"):
        issues.append("No project name detected")

    # Warnings (not blocking)
    unknowns = extraction.get("unknowns", [])
    if len(unknowns) > 5:
        warnings.append(f"High number of unknowns ({len(unknowns)}) - consider clarification")

    low_conf_items = []
    for m in extraction.get("modules", []):
        if m.get("confidence") == "low":
            low_conf_items.append(m.get("name", "unnamed"))

    if low_conf_items:
        warnings.append(f"Low confidence modules: {', '.join(low_conf_items)}")

    if issues:
        logger.error(f"Validation failed: {issues}")
        # Retry with different prompt strategy
        return Command(
            goto="parse_transcript",
            update={
                "parse_retry_reason": "; ".join(issues),
                "parse_retry_count": state.get("parse_retry_count", 0) + 1,
                "validation_errors": issues
            }
        )

    # Add warnings to state for UI display
    result = {"validation_warnings": warnings}

    if state.get("parse_retry_count", 0) > 0:
        result["validation_passed_after_retries"] = True
        logger.info(f"Validation passed after {state['parse_retry_count']} retries")
    else:
        result["validation_passed_after_retries"] = False

    return Command(goto="review_extraction", update=result)


# ── 2. ERROR RECOVERY NODE ───────────────────────────────────────────

def safe_parse_with_fallback(state: PipelineState) -> dict:
    """Parse transcript with automatic fallback on failure."""
    transcript = state["raw_transcript"]
    retry_count = state.get("parse_retry_count", 0)

    # Different strategies based on retry count
    strategies = {
        0: ("detailed", "Full extraction with all fields"),
        1: ("modules_only", "Focus on modules and requirements"),
        2: ("minimal", "Basic extraction - project name and overview"),
    }

    strategy, description = strategies.get(
        retry_count,
        ("minimal", "Last attempt - minimal extraction")
    )

    logger.info(f"Parse attempt {retry_count + 1} using strategy: {strategy}")

    try:
        # Use appropriate prompt for this attempt
        if strategy == "detailed":
            from agent.prompts.extraction import EXTRACTION_SYSTEM, EXTRACTION_USER
            messages = [
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {"role": "user", "content": EXTRACTION_USER.format(transcript=transcript)},
            ]
        elif strategy == "modules_only":
            messages = [
                {
                    "role": "system",
                    "content": "Extract ONLY the modules and high-level requirements. Focus on the main project components."
                },
                {
                    "role": "user",
                    "content": f"Extract from this transcript:\n\n{transcript[:5000]}"  # Truncate for focus
                }
            ]
        else:  # minimal
            messages = [
                {
                    "role": "system",
                    "content": "Extract just the project name and a brief 1-2 sentence overview."
                },
                {
                    "role": "user",
                    "content": f"Transcript:\n{transcript[:2000]}"
                }
            ]

        validated: Extraction = complete_structured(messages, schema=Extraction)

        return {
            "extraction": validated.model_dump(),
            "parse_strategy_used": strategy,
            "parse_success": True,
            "messages": [
                AIMessage(
                    content=f"Successfully extracted using strategy: {description}. "
                    f"Found {len(validated.modules)} modules. "
                    "Please review for accuracy."
                )
            ]
        }

    except Exception as e:
        logger.error(f"Parse attempt {retry_count + 1} failed: {e}")

        if retry_count < 2:
            # Retry with next strategy
            return {
                "parse_retry_count": retry_count + 1,
                "last_error": str(e),
                "messages": [
                    AIMessage(
                        content=f"Extraction attempt {retry_count + 1} failed. "
                        f"Retrying with different strategy..."
                    )
                ]
            }
        else:
            # All retries exhausted
            return {
                "parse_success": False,
                "parse_error": str(e),
                "extraction": {
                    "project_name": "Extraction Failed",
                    "modules": [],
                    "requirements": [],
                    "unknowns": [
                        {
                            "description": "Automatic extraction failed. Please enter details manually.",
                            "source": "system_error"
                        }
                    ]
                },
                "messages": [
                    AIMessage(
                        content="Automatic extraction failed after multiple attempts. "
                        "Please enter project details manually in the next step."
                    )
                ]
            }


# ── 3. CACHING NODE ──────────────────────────────────────────────────

@lru_cache(maxsize=50)
def cached_extraction_hash(transcript_hash: str, schema_name: str = "Extraction"):
    """Cache extraction results by transcript hash."""
    return None  # Cache hit marker

def compute_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()

def parse_with_cache(state: PipelineState) -> dict:
    """Parse transcript with intelligent caching."""
    transcript = state["raw_transcript"]
    transcript_hash = compute_hash(transcript)

    # Check cache
    if cached_extraction_hash(transcript_hash):
        logger.info("Cache hit - using cached extraction")
        return {
            "extraction": cached_extraction_hash(transcript_hash),
            "cached": True,
            "messages": [
                AIMessage(
                    content="Loaded from cache (this transcript was parsed before). "
                    "Please review for accuracy."
                )
            ]
        }

    # Cache miss - do actual parsing
    logger.info(f"Cache miss - parsing transcript ({len(transcript)} chars)")

    # ... (use existing parse_transcript logic)
    # After getting result:
    # result = parse_transcript(state)
    # cache it for next time
    # cached_extraction_hash(transcript_hash)

    # For now, delegate to existing node
    from agent.nodes.parse import parse_transcript
    return parse_transcript(state)


# ── 4. METRICS NODE ───────────────────────────────────────────────────

def track_metrics(node_func):
    """Decorator to track node execution metrics."""
    def wrapper(state: PipelineState):
        start = time()
        node_name = node_func.__name__

        # Get LLM call count from state
        llm_calls_before = state.get("metrics", {}).get("total_llm_calls", 0)

        # Run the actual node
        result = node_func(state)

        # Calculate metrics
        duration = time() - start

        # Update metrics
        metrics = result.get("metrics", {})
        metrics.update({
            "node": node_name,
            "duration_ms": int(duration * 1000),
            "timestamp": int(time()),
            "llm_calls": llm_calls_before + 1,
        })

        result["metrics"] = metrics
        result["total_llm_calls"] = metrics["llm_calls"]

        # Log if slow
        if duration > 10:
            logger.warning(f"Node {node_name} took {duration:.2f}s")

        return result
    return wrapper


# ── 5. PROGRESS STREAMING (for future SSE implementation) ───────────────

async def parse_with_progress(state: PipelineState):
    """Parse with progress updates for streaming."""
    from agent.prompts.extraction import EXTRACTION_SYSTEM, EXTRACTION_USER

    transcript = state["raw_transcript"]

    # Emit progress events
    yield {
        "event": "parse_start",
        "message": "Starting transcript analysis...",
        "progress": 0,
    }

    # Simulate streaming (replace with actual streaming LLM call)
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM},
        {"role": "user", "content": EXTRACTION_USER.format(transcript=transcript)},
    ]

    yield {
        "event": "parse_llm_call",
        "message": "Extracting structured data...",
        "progress": 50,
    }

    validated: Extraction = complete_structured(messages, schema=Extraction)

    yield {
        "event": "parse_complete",
        "message": f"Extracted {len(validated.modules)} modules, {len(validated.requirements)} requirements",
        "progress": 100,
    }

    yield {
        "extraction": validated.model_dump(),
        "current_stage": "parse",
        "messages": [
            AIMessage(content=f"Parsed transcript. Found {len(validated.modules)} modules.")
        ]
    }
