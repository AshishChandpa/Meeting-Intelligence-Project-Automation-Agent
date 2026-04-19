"""FastAPI backend wrapper for the LangGraph meeting intelligence pipeline.

This backend manages the pipeline state and handles user interactions at each stage.
Instead of using LangGraph's interrupt() (which requires LangGraph Studio/CLI),
we manage the state transitions manually.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.config import settings
from agent.storage.factory import create_project_repository
from agent.nodes.clarify import answer_human_question
from agent.nodes.sow import sow_missing_sections
from agent.nodes.sprint import move_task_between_sprints
from agent.nodes.jira_sync import build_jira_preview, sync_to_jira, sync_to_jira_batch
from agent.runtime import delete_graph_thread, run_graph, sync_project_with_graph, update_graph_state

logger = logging.getLogger(__name__)


# ── Project storage + SSE subscribers ─────────────────────────────────────

project_repo = create_project_repository(settings)
project_event_subscribers: dict[str, list[asyncio.Queue[tuple[str, dict[str, Any]]]]] = {}


# ── Pydantic models for API requests/responses ────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str
    transcript: str


class CreateProjectResponse(BaseModel):
    project_id: str
    name: str
    status: str


class FeedbackRequest(BaseModel):
    feedback: str


class AnswerRequest(BaseModel):
    question_id: str
    answer: str


class SkipRequest(BaseModel):
    question_id: str
    reason: str


class AskRequest(BaseModel):
    question: str


class JiraConfigRequest(BaseModel):
    domain: str
    email: str
    api_token: str
    project_key: str


class MoveTaskRequest(BaseModel):
    task_id: str
    sprint_name: str


class JiraBatchSyncResponse(BaseModel):
    message: str
    batch: Literal["epics", "issues", "sprints"]
    results: list[dict[str, Any]]
    batch_status: dict[str, str]


# ── Lifespan management ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown for the FastAPI app."""
    logger.info("Starting Meeting Intelligence API...")
    logger.info("LLM Provider: %s", settings.llm_provider)
    logger.info("Storage Backend: %s", settings.project_storage_backend)
    yield
    logger.info("Shutting down Meeting Intelligence API...")


# ── FastAPI app ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Meeting Intelligence API",
    description="AI-powered meeting transcript to Jira pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helper functions ─────────────────────────────────────────────────────

def get_project(project_id: str) -> dict[str, Any]:
    """Get a project by ID or raise 404."""
    project = project_repo.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def project_to_response(project: dict[str, Any]) -> dict[str, Any]:
    """Serialize project payload returned by state/read endpoints."""
    state = project["state"]
    return {
        "id": project["id"],
        "name": project["name"],
        "current_stage": state.get("current_stage", "parse"),
        "extraction": state.get("extraction"),
        "questions": state.get("questions", []),
        "sow": state.get("sow", ""),
        "sow_version": state.get("sow_version", 0),
        "sow_revisions": state.get("sow_revisions", []),
        "tasks": state.get("tasks", []),
        "sprints": state.get("sprints", []),
        "sprint_warnings": state.get("sprint_warnings", []),
        "jira_results": state.get("jira_results", []),
        "jira_batch_status": _jira_batch_status(state),
        "graph_checkpoint_id": state.get("graph_checkpoint_id", ""),
        "graph_next_nodes": state.get("graph_next_nodes", []),
        "pending_interrupts": state.get("pending_interrupts", []),
        "last_checkpoint_at": state.get("last_checkpoint_at"),
        "stage1_approved": state.get("stage1_approved", False),
        "stage2_approved": state.get("stage2_approved", False),
        "stage3_approved": state.get("stage3_approved", False),
        "stage4_approved": state.get("stage4_approved", False),
        "stage5_done": state.get("stage5_done", False),
    }


def _format_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


async def publish_project_event(project_id: str, event: str, payload: dict[str, Any]) -> None:
    """Publish an event to active SSE subscribers for a project."""
    subscribers = list(project_event_subscribers.get(project_id, []))
    for queue in subscribers:
        await queue.put((event, payload))


async def publish_project_state(project_id: str) -> None:
    project = project_repo.get(project_id)
    if not project:
        return
    project_repo.upsert(project)
    await publish_project_event(project_id, "project_state", project_to_response(project))


def update_project_state(project_id: str, updates: dict[str, Any]) -> None:
    """Update project state with new values."""
    project = project_repo.get(project_id)
    if project is None:
        return
    project["state"].update(updates)
    project_repo.upsert(project)


def _schedule_project_event(
    loop: asyncio.AbstractEventLoop,
    project_id: str,
    event: str,
    payload: dict[str, Any],
) -> None:
    enriched = {**payload, "timestamp": payload.get("timestamp", time.time())}
    loop.call_soon_threadsafe(
        lambda: asyncio.create_task(publish_project_event(project_id, event, enriched))
    )


async def _run_graph_for_project(
    project: dict[str, Any],
    *,
    initial_state: dict[str, Any] | None = None,
    resume_value: Any | None = None,
) -> dict[str, Any]:
    project_id = project["id"]
    loop = asyncio.get_running_loop()

    def callback(event: str, payload: dict[str, Any]) -> None:
        _schedule_project_event(loop, project_id, event, payload)

    try:
        await asyncio.to_thread(
            run_graph,
            project_id,
            initial_state=initial_state,
            resume_value=resume_value,
            callback=callback,
        )
        sync_project_with_graph(project)
        project_repo.upsert(project)
        return project
    except Exception:
        _schedule_project_event(
            loop,
            project_id,
            "graph_error",
            {"message": "Workflow execution failed."},
        )
        raise


def _sync_manual_graph_state(project_id: str, values: dict[str, Any], *, as_node: str | None = None) -> None:
    try:
        runtime_meta = update_graph_state(project_id, values, as_node=as_node)
    except Exception:
        logger.debug("Graph state sync skipped for %s", project_id, exc_info=True)
        return
    update_project_state(project_id, runtime_meta)


def _jira_batch_status(state: dict[str, Any]) -> dict[str, str]:
    return dict(state.get("jira_batch_status", {}))


def _is_batch_allowed(state: dict[str, Any], batch: str) -> tuple[bool, str]:
    status = _jira_batch_status(state)
    if batch == "epics":
        return True, ""
    if batch == "issues":
        if status.get("epics") != "done":
            return False, "Please complete Epics sync first"
        return True, ""
    if batch == "sprints":
        if status.get("issues") != "done":
            return False, "Please complete Issues sync first"
        return True, ""
    return False, "Invalid batch"


# ── REST endpoints ───────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "llm_provider": settings.llm_provider,
        "projects_count": project_repo.count(),
        "storage_backend": settings.project_storage_backend,
    }


@app.post("/api/projects", response_model=CreateProjectResponse)
async def create_project(request: CreateProjectRequest):
    """Create a new project with a transcript and start Stage 1 parsing."""
    project_id = str(uuid.uuid4())

    # Initialize project state
    project = {
        "id": project_id,
        "name": request.name,
        "transcript": request.transcript,
        "created_at": time.time(),
        "state": {
            "raw_transcript": request.transcript,
            "current_stage": "parse",
            "messages": [],
            "stage1_approved": False,
            "stage2_approved": False,
            "stage3_approved": False,
            "stage4_approved": False,
            "stage5_done": False,
        },
        "jira_config": None,
    }

    project_repo.upsert(project)
    await publish_project_event(project_id, "stage_started", {"stage": "parse"})

    try:
        await _run_graph_for_project(project, initial_state=project["state"].copy())
        await publish_project_event(project_id, "stage_completed", {"stage": "parse"})
        await publish_project_state(project_id)

        logger.info("Created project %s and completed parsing", project_id)

        return CreateProjectResponse(
            project_id=project_id,
            name=request.name,
            status="parse",
        )

    except Exception as e:
        project_repo.delete(project_id)
        logger.exception("Failed to create project")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects")
async def list_projects():
    """List all projects."""
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "current_stage": p["state"].get("current_stage", "unknown"),
            "created_at": p.get("created_at"),
        }
        for p in project_repo.list_all()
    ]


@app.get("/api/projects/{project_id}")
async def get_project_state(project_id: str):
    """Get the current state of a project."""
    project = get_project(project_id)
    return project_to_response(project)


@app.get("/api/projects/{project_id}/stream")
async def stream_project_state(project_id: str):
    """Server-Sent Events stream for real-time project state updates."""
    project = get_project(project_id)
    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
    subscribers = project_event_subscribers.setdefault(project_id, [])
    subscribers.append(queue)

    async def event_generator():
        try:
            # Initial snapshot so UI can hydrate immediately.
            yield _format_sse("project_state", project_to_response(project))
            while True:
                try:
                    event_name, payload = await asyncio.wait_for(queue.get(), timeout=20)
                    yield _format_sse(event_name, payload)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            active = project_event_subscribers.get(project_id, [])
            if queue in active:
                active.remove(queue)
            if not active:
                project_event_subscribers.pop(project_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project."""
    if not project_repo.delete(project_id):
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    delete_graph_thread(project_id)
    project_event_subscribers.pop(project_id, None)
    return {"message": f"Project {project_id} deleted"}


# ── Stage 1 endpoints ─────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/stage/parse/approve")
async def approve_stage1(project_id: str):
    """Approve Stage 1 extraction and proceed to Stage 2."""
    project = get_project(project_id)

    try:
        await publish_project_event(project_id, "stage_started", {"stage": "clarify"})
        await _run_graph_for_project(project, resume_value="approve")
        await publish_project_event(project_id, "stage_completed", {"stage": "clarify"})
        await publish_project_state(project_id)
        return {"message": "Stage 1 approved", "next_stage": "clarify"}

    except Exception as e:
        logger.exception("Failed to approve Stage 1")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/parse/feedback")
async def submit_stage1_feedback(project_id: str, request: FeedbackRequest):
    """Submit correction feedback for Stage 1 extraction."""
    project = get_project(project_id)

    try:
        await _run_graph_for_project(project, resume_value=request.feedback)
        await publish_project_state(project_id)
        return {"message": "Correction applied", "extraction": project["state"].get("extraction")}

    except Exception as e:
        logger.exception("Failed to apply correction")
        raise HTTPException(status_code=500, detail=str(e))


# ── Stage 2 endpoints ─────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/stage/clarify/answer")
async def answer_question(project_id: str, request: AnswerRequest):
    """Answer a clarification question in Stage 2."""
    project = get_project(project_id)

    try:
        answer_input = f"{request.question_id}: {request.answer}"
        await _run_graph_for_project(project, resume_value=answer_input)
        await publish_project_state(project_id)
        return {"message": "Answer processed", "questions": project["state"].get("questions", [])}

    except Exception as e:
        logger.exception("Failed to process answer")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/clarify/skip")
async def skip_question(project_id: str, request: SkipRequest):
    """Skip a clarification question in Stage 2."""
    project = get_project(project_id)

    try:
        skip_input = f"{request.question_id}: skip {request.reason}"
        await _run_graph_for_project(project, resume_value=skip_input)
        await publish_project_state(project_id)
        return {"message": "Question skipped", "questions": project["state"].get("questions", [])}

    except Exception as e:
        logger.exception("Failed to skip question")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/clarify/ask")
async def ask_question(project_id: str, request: AskRequest):
    """Ask a user-initiated clarification/planning question in Stage 2."""
    project = get_project(project_id)

    try:
        state = project["state"].copy()
        result = answer_human_question(state, request.question)
        project["state"].update(result)
        _sync_manual_graph_state(project_id, {"questions": project["state"].get("questions", [])})
        await publish_project_state(project_id)
        answer_text = ""
        if result.get("messages"):
            answer_text = getattr(result["messages"][0], "content", "") or ""
        return {
            "message": "Question answered",
            "answer": answer_text,
            "questions": result.get("questions", []),
        }

    except Exception as e:
        logger.exception("Failed to answer user question")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/clarify/done")
async def done_clarification(project_id: str):
    """Mark clarification as complete and proceed to Stage 3."""
    project = get_project(project_id)

    try:
        await publish_project_event(project_id, "stage_started", {"stage": "sow"})
        await _run_graph_for_project(project, resume_value="done")
        await publish_project_event(project_id, "stage_completed", {"stage": "sow"})
        await publish_project_state(project_id)
        return {"message": "Clarification complete", "next_stage": "sow"}

    except Exception as e:
        logger.exception("Failed to complete clarification")
        raise HTTPException(status_code=500, detail=str(e))


# ── Stage 3 endpoints ─────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/stage/sow/feedback")
async def submit_sow_feedback(project_id: str, request: FeedbackRequest):
    """Submit feedback for Stage 3 SoW revision."""
    project = get_project(project_id)

    try:
        await _run_graph_for_project(project, resume_value=request.feedback)
        await publish_project_state(project_id)
        return {
            "message": "SoW revised",
            "sow": project["state"].get("sow"),
            "version": project["state"].get("sow_version"),
        }

    except Exception as e:
        logger.exception("Failed to revise SoW")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/sow/approve")
async def approve_sow(project_id: str):
    """Approve the SoW and proceed to Stage 4."""
    project = get_project(project_id)

    # Check if at least one feedback round has been done
    if len(project["state"].get("sow_revisions", [])) == 0:
        raise HTTPException(
            status_code=400,
            detail="Please provide at least one round of feedback before approving",
        )

    missing_sections = sow_missing_sections(project["state"].get("sow", ""))
    if missing_sections:
        raise HTTPException(
            status_code=400,
            detail=f"SoW is missing required sections: {', '.join(missing_sections)}",
        )

    try:
        await publish_project_event(project_id, "stage_started", {"stage": "sprint"})
        await _run_graph_for_project(project, resume_value="approve")
        await publish_project_event(project_id, "stage_completed", {"stage": "sprint"})
        await publish_project_state(project_id)
        return {"message": "SoW approved", "next_stage": "sprint"}

    except Exception as e:
        logger.exception("Failed to approve SoW")
        raise HTTPException(status_code=500, detail=str(e))


# ── Stage 4 endpoints ─────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/stage/sprint/feedback")
async def submit_sprint_feedback(project_id: str, request: FeedbackRequest):
    """Submit adjustment feedback for Stage 4 sprint plan."""
    project = get_project(project_id)

    try:
        await _run_graph_for_project(project, resume_value=request.feedback)
        await publish_project_state(project_id)
        return {"message": "Sprint plan adjusted", "sprints": project["state"].get("sprints", [])}

    except Exception as e:
        logger.exception("Failed to adjust sprint plan")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/sprint/approve")
async def approve_sprint_plan(project_id: str):
    """Approve the sprint plan and proceed to Stage 5."""
    project = get_project(project_id)

    try:
        await _run_graph_for_project(project, resume_value="approve")
        await publish_project_state(project_id)
        return {"message": "Sprint plan approved", "next_stage": "jira"}

    except Exception as e:
        logger.exception("Failed to approve sprint plan")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/sprint/move-task")
async def move_task(project_id: str, request: MoveTaskRequest):
    """Move a task to a different sprint before approval."""
    project = get_project(project_id)

    try:
        state = project["state"]
        updated_sprints, warnings = move_task_between_sprints(
            tasks=state.get("tasks", []),
            sprints=state.get("sprints", []),
            task_id=request.task_id,
            target_sprint_name=request.sprint_name,
        )
        state["sprints"] = updated_sprints
        state["sprint_warnings"] = warnings
        _sync_manual_graph_state(
            project_id,
            {
                "sprints": updated_sprints,
                "sprint_warnings": warnings,
            },
        )
        await publish_project_state(project_id)
        return {"message": "Task moved", "sprints": updated_sprints, "warnings": warnings}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to move task")
        raise HTTPException(status_code=500, detail=str(e))


# ── Stage 5 endpoints ─────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/jira/config")
async def set_jira_config(project_id: str, request: JiraConfigRequest):
    """Set Jira configuration for a project."""
    project = get_project(project_id)

    project["jira_config"] = {
        "domain": request.domain,
        "email": request.email,
        "api_token": request.api_token,
        "project_key": request.project_key,
    }
    # Reset previous Jira sync progress when config/project changes.
    project["state"]["jira_results"] = []
    project["state"]["jira_batch_status"] = {}
    project["state"]["jira_epic_key_by_module"] = {}
    project["state"]["jira_issue_id_by_task"] = {}
    project["state"].pop("jira_board_id", None)
    _sync_manual_graph_state(
        project_id,
        {
            "jira_config": project["jira_config"],
            "jira_results": [],
            "jira_batch_status": {},
            "jira_epic_key_by_module": {},
            "jira_issue_id_by_task": {},
            "jira_board_id": None,
        },
    )

    await publish_project_event(project_id, "jira_config_saved", {"project_id": project_id})
    await publish_project_state(project_id)

    return {"message": "Jira config saved"}


@app.post("/api/projects/{project_id}/jira/test")
async def test_jira_connection(project_id: str):
    """Test Jira connection."""
    project = get_project(project_id)
    jira_config = project.get("jira_config")

    if not jira_config:
        raise HTTPException(status_code=400, detail="Jira config not set")

    try:
        from agent.jira import JiraClient

        client = JiraClient(
            domain=jira_config["domain"],
            email=jira_config["email"],
            api_token=jira_config["api_token"],
            project_key=jira_config["project_key"],
        )
        client.test_connection()
        return {"message": "Jira connection successful"}

    except Exception as e:
        logger.exception("Jira connection test failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}/jira/preview")
async def get_jira_preview(project_id: str):
    """Get preview of what will be created in Jira."""
    project = get_project(project_id)
    state = project["state"]

    preview = build_jira_preview(state)
    return {
        **preview,
        "counts": {
            "epics": len(preview["epics"]),
            "issues": len(preview["issues"]),
            "sprints": len(preview["sprints"]),
        },
        "batch_status": _jira_batch_status(state),
    }


@app.post("/api/projects/{project_id}/jira/sync/{batch}", response_model=JiraBatchSyncResponse)
async def sync_to_jira_batch_endpoint(project_id: str, batch: Literal["epics", "issues", "sprints"]):
    """Sync one Jira batch only (epics -> issues -> sprints)."""
    project = get_project(project_id)
    jira_config = project.get("jira_config")

    if not jira_config:
        raise HTTPException(status_code=400, detail="Jira config not set. Please set it first.")

    allowed, message = _is_batch_allowed(project["state"], batch)
    if not allowed:
        raise HTTPException(status_code=400, detail=message)

    try:
        state = project["state"].copy()
        state["jira_config"] = jira_config
        result = sync_to_jira_batch(state, batch)
        project["state"].update(result)
        _sync_manual_graph_state(project_id, result)

        if batch == "sprints" and project["state"].get("jira_batch_status", {}).get("sprints") == "done":
            project["state"]["stage5_done"] = True
            project["state"]["current_stage"] = "done"
            _sync_manual_graph_state(project_id, {"stage5_done": True, "current_stage": "done"})
            await publish_project_event(project_id, "stage_completed", {"stage": "done"})

        await publish_project_state(project_id)
        return JiraBatchSyncResponse(
            message=f"{batch.title()} batch synced",
            batch=batch,
            results=result.get("jira_results", []),
            batch_status=_jira_batch_status(project["state"]),
        )

    except Exception as e:
        logger.exception("Failed to sync Jira batch '%s'", batch)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/jira/sync")
async def sync_to_jira_endpoint(project_id: str):
    """Execute Jira sync."""
    project = get_project(project_id)
    jira_config = project.get("jira_config")

    if not jira_config:
        raise HTTPException(status_code=400, detail="Jira config not set. Please set it first.")

    try:
        await publish_project_event(project_id, "stage_started", {"stage": "done"})
        # Add Jira config to state and run sync
        state = project["state"].copy()
        state["jira_config"] = jira_config

        result = sync_to_jira(state)
        project["state"].update(result)
        project["state"]["stage5_done"] = True
        _sync_manual_graph_state(project_id, result)
        await publish_project_event(project_id, "stage_completed", {"stage": "done"})
        await publish_project_state(project_id)
        return {"message": "Jira sync complete", "results": result.get("jira_results", [])}

    except Exception as e:
        logger.exception("Failed to sync to Jira")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)