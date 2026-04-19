"""Smoke test for graph-backed API orchestration without hitting a real LLM.

This monkeypatches the runtime layer so we can confirm the API endpoints are
using the graph runner + checkpoint metadata flow.
"""

from __future__ import annotations

import asyncio

import api.main as main
from agent.storage.memory import InMemoryProjectRepository


main.project_repo = InMemoryProjectRepository()
_calls: dict[str, dict[str, object | None]] = {}


def fake_run_graph(project_id: str, *, initial_state=None, resume_value=None, callback=None):
    _calls[project_id] = {
        "initial_state": initial_state,
        "resume_value": resume_value,
    }
    if callback:
        callback(
            "stage_progress",
            {
                "project_id": project_id,
                "message": "fake run",
                "progress": 42,
            },
        )


def fake_sync_project_with_graph(project: dict):
    call = _calls[project["id"]]
    state = project["state"]
    if call["initial_state"] is not None:
        state.update(
            {
                "current_stage": "parse",
                "extraction": {
                    "project_name": "Demo",
                    "client_name": "Client",
                    "vendor_name": "Vendor",
                    "modules": [],
                    "requirements": [],
                    "integrations": [],
                    "constraints": [],
                    "assumptions": [],
                    "unknowns": [],
                },
                "graph_checkpoint_id": "cp-1",
                "graph_next_nodes": ["review_extraction"],
                "pending_interrupts": [{"stage": "parse", "message": "Review extraction"}],
            }
        )
    elif call["resume_value"] == "approve":
        state.update(
            {
                "current_stage": "clarify",
                "questions": [
                    {
                        "id": "q1",
                        "question": "Need timeline?",
                        "context": "scope",
                        "status": "open",
                        "answer": "",
                        "skip_reason": "",
                    }
                ],
                "graph_checkpoint_id": "cp-2",
                "graph_next_nodes": ["review_clarification"],
                "pending_interrupts": [{"stage": "clarify", "message": "Answer questions"}],
                "stage1_approved": True,
            }
        )
    return project


main.run_graph = fake_run_graph
main.sync_project_with_graph = fake_sync_project_with_graph


async def scenario() -> None:
    created = await main.create_project(main.CreateProjectRequest(name="Demo", transcript="hello"))
    project = main.project_repo.get(created.project_id)
    assert project is not None
    assert project["state"]["graph_checkpoint_id"] == "cp-1"
    assert project["state"]["pending_interrupts"][0]["stage"] == "parse"

    approved = await main.approve_stage1(created.project_id)
    project = main.project_repo.get(created.project_id)
    assert project is not None
    assert approved["next_stage"] == "clarify"
    assert project["state"]["current_stage"] == "clarify"
    assert project["state"]["graph_checkpoint_id"] == "cp-2"
    assert project["state"]["pending_interrupts"][0]["stage"] == "clarify"

    print("graph_api_smoke: ok")


if __name__ == "__main__":
    asyncio.run(scenario())

