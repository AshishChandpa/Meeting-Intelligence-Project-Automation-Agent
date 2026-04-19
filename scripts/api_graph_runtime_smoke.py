"""Smoke test for graph-backed API orchestration without hitting a real LLM.

This monkeypatches the runtime layer so we can confirm the API endpoints are
using the graph runner + checkpoint metadata flow.
"""

from __future__ import annotations

import asyncio

import api.main as main
from fastapi import HTTPException
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
    elif call["resume_value"] == "epics":
        state.update(
            {
                "current_stage": "jira",
                "jira_batch_status": {"epics": "done"},
                "jira_last_batch": "epics",
                "jira_last_batch_results": [
                    {
                        "type": "epic",
                        "key": "DEMO-1",
                        "title": "Core Platform",
                        "url": "https://example.atlassian.net/browse/DEMO-1",
                        "status": "created",
                        "error": "",
                    }
                ],
                "pending_interrupts": [{"stage": "jira", "batch": "issues", "message": "Confirm issues"}],
            }
        )
    elif call["resume_value"] == "issues":
        state.update(
            {
                "current_stage": "jira",
                "jira_batch_status": {"epics": "done", "issues": "done"},
                "jira_last_batch": "issues",
                "jira_last_batch_results": [
                    {
                        "type": "issue",
                        "key": "DEMO-2",
                        "title": "Build Core Platform",
                        "url": "https://example.atlassian.net/browse/DEMO-2",
                        "status": "created",
                        "error": "",
                    }
                ],
                "pending_interrupts": [{"stage": "jira", "batch": "sprints", "message": "Confirm sprints"}],
            }
        )
    elif call["resume_value"] == "sprints":
        state.update(
            {
                "current_stage": "done",
                "jira_batch_status": {"epics": "done", "issues": "done", "sprints": "done"},
                "jira_last_batch": "sprints",
                "jira_last_batch_results": [
                    {
                        "type": "sprint",
                        "key": "12",
                        "title": "Sprint 1",
                        "url": "https://example.atlassian.net/jira/software/projects/DEMO/boards",
                        "status": "created",
                        "error": "",
                    }
                ],
                "pending_interrupts": [],
                "stage5_done": True,
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

    jira_project_id = "jira-demo"
    main.project_repo.upsert(
        {
            "id": jira_project_id,
            "name": "Jira Demo",
            "transcript": "hello",
            "created_at": 0,
            "jira_config": {
                "domain": "example.atlassian.net",
                "email": "demo@example.com",
                "api_token": "token",
                "project_key": "DEMO",
            },
            "state": {
                "current_stage": "jira",
                "tasks": [],
                "sprints": [],
                "messages": [],
                "jira_batch_status": {},
                "pending_interrupts": [{"stage": "jira", "batch": "epics", "message": "Confirm epics"}],
            },
        }
    )
    batch_response = await main.sync_to_jira_batch_endpoint(jira_project_id, "epics")
    jira_project = main.project_repo.get(jira_project_id)
    assert jira_project is not None
    assert batch_response.batch == "epics"
    assert jira_project["state"]["jira_batch_status"]["epics"] == "done"
    assert jira_project["state"]["pending_interrupts"][0]["batch"] == "issues"

    # Guardrails: cannot skip directly to issues before the graph asks for them.
    blocked_project_id = "jira-blocked"
    main.project_repo.upsert(
        {
            "id": blocked_project_id,
            "name": "Blocked Jira Demo",
            "transcript": "hello",
            "created_at": 0,
            "jira_config": {
                "domain": "example.atlassian.net",
                "email": "demo@example.com",
                "api_token": "token",
                "project_key": "DEMO",
            },
            "state": {
                "current_stage": "sprint",
                "tasks": [],
                "sprints": [],
                "messages": [],
                "jira_batch_status": {},
                "pending_interrupts": [{"stage": "sprint", "message": "Review sprint plan"}],
            },
        }
    )
    try:
        await main.sync_to_jira_batch_endpoint(blocked_project_id, "epics")
        raise AssertionError("Jira sync should be blocked before Stage 5 review is active")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "awaiting Jira batch confirmation" in exc.detail

    # Full Jira batch progression.
    issues_response = await main.sync_to_jira_batch_endpoint(jira_project_id, "issues")
    jira_project = main.project_repo.get(jira_project_id)
    assert jira_project is not None
    assert issues_response.batch == "issues"
    assert jira_project["state"]["jira_batch_status"]["issues"] == "done"
    assert jira_project["state"]["pending_interrupts"][0]["batch"] == "sprints"

    sprints_response = await main.sync_to_jira_batch_endpoint(jira_project_id, "sprints")
    jira_project = main.project_repo.get(jira_project_id)
    assert jira_project is not None
    assert sprints_response.batch == "sprints"
    assert jira_project["state"]["jira_batch_status"]["sprints"] == "done"
    assert jira_project["state"]["stage5_done"] is True
    assert jira_project["state"]["current_stage"] == "done"

    # Aggregate endpoint should continue from the current pending Jira batch.
    aggregate_project_id = "jira-aggregate"
    main.project_repo.upsert(
        {
            "id": aggregate_project_id,
            "name": "Aggregate Jira Demo",
            "transcript": "hello",
            "created_at": 0,
            "jira_config": {
                "domain": "example.atlassian.net",
                "email": "demo@example.com",
                "api_token": "token",
                "project_key": "DEMO",
            },
            "state": {
                "current_stage": "jira",
                "tasks": [],
                "sprints": [],
                "messages": [],
                "jira_batch_status": {},
                "pending_interrupts": [{"stage": "jira", "batch": "epics", "message": "Confirm epics"}],
            },
        }
    )
    aggregate_response = await main.sync_to_jira_endpoint(aggregate_project_id)
    aggregate_project = main.project_repo.get(aggregate_project_id)
    assert aggregate_project is not None
    assert aggregate_response["message"] == "Jira sync complete"
    assert aggregate_project["state"]["stage5_done"] is True

    print("graph_api_smoke: ok")


if __name__ == "__main__":
    asyncio.run(scenario())

