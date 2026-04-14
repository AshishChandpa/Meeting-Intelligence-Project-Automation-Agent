from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent.nodes.parse import parse_transcript
from agent.nodes.clarify import generate_questions, process_answer
from agent.nodes.sow import draft_sow, revise_sow
from agent.nodes.sprint import generate_sprint_plan, adjust_sprint_plan


def run_for_file(name: str) -> dict:
    state = {
        "raw_transcript": (ROOT / name).read_text(encoding="utf-8"),
        "messages": [],
        "current_stage": "parse",
        "stage1_approved": False,
        "stage2_approved": False,
        "stage3_approved": False,
        "stage4_approved": False,
        "stage5_done": False,
    }

    state.update(parse_transcript(state))
    ex = state.get("extraction", {})

    state["stage1_approved"] = True
    state["current_stage"] = "clarify"
    state.update(generate_questions(state))

    questions = state.get("questions", [])
    if questions:
        qid = questions[0]["id"]
        state["messages"].append(HumanMessage(content=f"{qid}: We will decide this during planning."))
        state.update(process_answer(state))

    state["stage2_approved"] = True
    state["current_stage"] = "sow"
    state.update(draft_sow(state))
    sow_length = len(state.get("sow", ""))

    state["messages"].append(HumanMessage(content="Please add clearer timeline and explicit out-of-scope section."))
    state.update(revise_sow(state))

    state["stage3_approved"] = True
    state["current_stage"] = "sprint"
    state.update(generate_sprint_plan(state))

    state["messages"].append(HumanMessage(content="Move one medium-priority task from Sprint 2 to Sprint 1 if capacity allows."))
    state.update(adjust_sprint_plan(state))

    return {
        "file": name,
        "stage1": {
            "modules": len(ex.get("modules", [])),
            "requirements": len(ex.get("requirements", [])),
            "integrations": len(ex.get("integrations", [])),
            "unknowns": len(ex.get("unknowns", [])),
        },
        "stage2_questions": len(state.get("questions", [])),
        "stage3_sow_chars": sow_length,
        "stage3_version": state.get("sow_version"),
        "stage4_tasks": len(state.get("tasks", [])),
        "stage4_sprints": len(state.get("sprints", [])),
        "stage4_warnings": len(state.get("sprint_warnings", [])),
    }


def main() -> None:
    files = [
        "Software Co _ Smart Money Discovery  Transcript.txt",
        "Eco_Chase_Discovery_Transcript_Anonymised.txt",
    ]
    for file_name in files:
        result = run_for_file(file_name)
        print(result)


if __name__ == "__main__":
    main()

