"""Quick extraction evaluator for the two assessment transcripts.

Usage:
    uv run python scripts/evaluate_extraction.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent.nodes.parse import parse_transcript

TRANSCRIPTS = [
    ROOT / "Software Co _ Smart Money Discovery  Transcript.txt",
    ROOT / "Eco_Chase_Discovery_Transcript_Anonymised.txt",
]


def summarize(path: Path) -> dict:
    state = {"raw_transcript": path.read_text(encoding="utf-8"), "messages": []}
    result = parse_transcript(state)
    extraction = result["extraction"]
    context = result.get("preprocessing_context", {})

    return {
        "file": path.name,
        "strategy": context.get("strategy", "unknown"),
        "fallback_strategy": context.get("fallback_strategy", ""),
        "total_chunks": context.get("total_chunks", 0),
        "project_name": extraction.get("project_name", ""),
        "client_name": extraction.get("client_name", ""),
        "vendor_name": extraction.get("vendor_name", ""),
        "counts": {
            "modules": len(extraction.get("modules", [])),
            "requirements": len(extraction.get("requirements", [])),
            "integrations": len(extraction.get("integrations", [])),
            "constraints": len(extraction.get("constraints", [])),
            "assumptions": len(extraction.get("assumptions", [])),
            "unknowns": len(extraction.get("unknowns", [])),
        },
        "first_modules": [m.get("name", "") for m in extraction.get("modules", [])[:6]],
        "first_unknowns": [u.get("description", "") for u in extraction.get("unknowns", [])[:5]],
    }


def main() -> None:
    rows = [summarize(path) for path in TRANSCRIPTS]
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()

