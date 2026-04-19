"""Smoke-test long transcript chunk/merge extraction without calling a real LLM.

This validates:
- strategy selection switches to chunked for long transcripts
- chunk outputs are merged and de-duplicated
- sparse merged output falls back to a focused single-pass retry
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import agent.nodes.parse as parse_module
from agent.state import Extraction


def _make_transcript(*, prefix: str, segments: int = 84) -> str:
    lines: list[str] = []
    for index in range(segments):
        minute, second = divmod(index, 60)
        timestamp = f"{minute}:{second:02d}"
        speaker = "Client" if index % 2 == 0 else "Team Member 1"
        lines.append(f"{timestamp} - {speaker}")
        lines.append(
            f"{prefix} segment {index}. We need better onboarding, analytics, integrations, and workflow automation for the platform."
        )
    return "\n".join(lines)


def _success_chunk_response(chunk_no: int) -> Extraction:
    if chunk_no == 1:
        return Extraction(
            project_name="Atlas Platform",
            client_name="Acme Health",
            vendor_name="Build Labs",
            modules=[
                {
                    "name": "Core Platform",
                    "description": "Shared application foundation",
                    "priority": "High",
                    "deadline": None,
                    "confidence": "high",
                }
            ],
            requirements=[
                {
                    "description": "Support client onboarding workflow",
                    "module": "Core Platform",
                    "type": "Functional",
                    "confidence": "high",
                },
                {
                    "description": "Allow document upload during onboarding",
                    "module": "Core Platform",
                    "type": "Functional",
                    "confidence": "high",
                },
                {
                    "description": "Provide role-based access control",
                    "module": "Core Platform",
                    "type": "Functional",
                    "confidence": "medium",
                },
            ],
            integrations=[
                {
                    "system": "QuickBooks",
                    "purpose": "Financial sync",
                    "confidence": "medium",
                }
            ],
            constraints=[],
            assumptions=[],
            unknowns=[],
        )
    if chunk_no == 2:
        return Extraction(
            project_name="Atlas Platform",
            client_name="Acme Health",
            vendor_name="Build Labs",
            modules=[
                {
                    "name": "Core Platform",
                    "description": "Shared platform services",
                    "priority": "High",
                    "deadline": None,
                    "confidence": "medium",
                },
                {
                    "name": "Reporting",
                    "description": "Dashboards and insights",
                    "priority": "Medium",
                    "deadline": None,
                    "confidence": "high",
                },
            ],
            requirements=[
                {
                    "description": "Allow document uploads during onboarding",
                    "module": "Core Platform",
                    "type": "Functional",
                    "confidence": "medium",
                },
                {
                    "description": "Provide reporting dashboards for account activity",
                    "module": "Reporting",
                    "type": "Functional",
                    "confidence": "high",
                },
                {
                    "description": "Export monthly performance reports",
                    "module": "Reporting",
                    "type": "Functional",
                    "confidence": "medium",
                },
            ],
            integrations=[
                {
                    "system": "QuickBooks",
                    "purpose": "Accounting sync",
                    "confidence": "high",
                }
            ],
            constraints=[],
            assumptions=[],
            unknowns=[],
        )
    if chunk_no == 3:
        return Extraction(
            project_name="Atlas Platform",
            client_name="Acme Health",
            vendor_name="Build Labs",
            modules=[
                {
                    "name": "Integrations",
                    "description": "External system connections",
                    "priority": "Medium",
                    "deadline": None,
                    "confidence": "high",
                }
            ],
            requirements=[
                {
                    "description": "Sync invoices to QuickBooks",
                    "module": "Integrations",
                    "type": "Integration",
                    "confidence": "high",
                },
                {
                    "description": "Send notifications for stalled onboarding tasks",
                    "module": "Core Platform",
                    "type": "Functional",
                    "confidence": "medium",
                },
                {
                    "description": "Track audit history for workflow changes",
                    "module": "Core Platform",
                    "type": "Non-Functional",
                    "confidence": "medium",
                },
            ],
            integrations=[
                {
                    "system": "Slack",
                    "purpose": "Operational alerts",
                    "confidence": "medium",
                }
            ],
            constraints=[],
            assumptions=[],
            unknowns=[{"description": "Need confirmation on mobile scope", "source": "chunk-3"}],
        )
    return Extraction()


def _fallback_response() -> Extraction:
    return Extraction(
        project_name="Fallback Platform",
        client_name="SparseCo",
        vendor_name="Build Labs",
        modules=[
            {
                "name": "Core Platform",
                "description": "Primary workflow management",
                "priority": "High",
                "deadline": None,
                "confidence": "high",
            },
            {
                "name": "Reporting",
                "description": "Operational reporting",
                "priority": "Medium",
                "deadline": None,
                "confidence": "medium",
            },
        ],
        requirements=[
            {
                "description": "Capture onboarding applications",
                "module": "Core Platform",
                "type": "Functional",
                "confidence": "high",
            },
            {
                "description": "Route approvals across internal teams",
                "module": "Core Platform",
                "type": "Functional",
                "confidence": "medium",
            },
            {
                "description": "Upload supporting documents",
                "module": "Core Platform",
                "type": "Functional",
                "confidence": "high",
            },
            {
                "description": "Generate dashboard summaries",
                "module": "Reporting",
                "type": "Functional",
                "confidence": "medium",
            },
            {
                "description": "Export reports to CSV",
                "module": "Reporting",
                "type": "Functional",
                "confidence": "medium",
            },
            {
                "description": "Track workflow audit history",
                "module": "Core Platform",
                "type": "Non-Functional",
                "confidence": "medium",
            },
        ],
        integrations=[
            {
                "system": "HubSpot",
                "purpose": "CRM sync",
                "confidence": "medium",
            }
        ],
        constraints=[],
        assumptions=[],
        unknowns=[],
    )


def fake_complete_structured(prompt_messages: list[dict], schema: type[Extraction]) -> Extraction:
    prompt = prompt_messages[-1]["content"]

    if "SparseCo" in prompt:
        if "strategy: focused-fallback" in prompt or "strategy: full-fallback" in prompt:
            return _fallback_response()
        return Extraction()

    chunk_match = re.search(r"chunk_window:\s*(\d+)/(\d+)", prompt)
    if chunk_match:
        return _success_chunk_response(int(chunk_match.group(1)))

    return _fallback_response()


def run() -> None:
    original_complete_structured = parse_module.complete_structured
    parse_module.complete_structured = fake_complete_structured
    try:
        success_result = parse_module.parse_transcript(
            {
                "raw_transcript": _make_transcript(prefix="Acme Health"),
                "messages": [],
            }
        )
        success_context = success_result["preprocessing_context"]
        success_extraction = success_result["extraction"]
        assert success_context["strategy"] == "chunked"
        assert success_context["total_chunks"] > 1
        assert success_context.get("fallback_strategy", "") == ""
        assert len(success_extraction["requirements"]) == 8
        assert len(success_extraction["modules"]) == 3
        assert len(success_extraction["integrations"]) == 2

        fallback_result = parse_module.parse_transcript(
            {
                "raw_transcript": _make_transcript(prefix="SparseCo"),
                "messages": [],
            }
        )
        fallback_context = fallback_result["preprocessing_context"]
        fallback_extraction = fallback_result["extraction"]
        assert fallback_context["strategy"] == "chunked"
        assert fallback_context["fallback_strategy"] == "focused-single-pass"
        assert fallback_extraction["project_name"] == "Fallback Platform"
        assert len(fallback_extraction["requirements"]) == 6

        print("long_transcript_chunking_smoke: ok")
    finally:
        parse_module.complete_structured = original_complete_structured


if __name__ == "__main__":
    run()

