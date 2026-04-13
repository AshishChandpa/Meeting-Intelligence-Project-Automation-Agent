"""FastAPI backend wrapper for the LangGraph meeting intelligence pipeline.

This backend manages the pipeline state and handles user interactions at each stage.
Instead of using LangGraph's interrupt() (which requires LangGraph Studio/CLI),
we manage the state transitions manually.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.config import settings
from agent.nodes.parse import apply_corrections, parse_transcript
from agent.nodes.clarify import generate_questions, process_answer
from agent.nodes.sow import draft_sow, revise_sow
from agent.nodes.sprint import generate_sprint_plan, adjust_sprint_plan
from agent.nodes.jira_sync import sync_to_jira
from agent.state import Extraction

logger = logging.getLogger(__name__)


# ── In-memory project storage ─────────────────────────────────────────────

projects: dict[str, dict[str, Any]] = {}


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


class JiraConfigRequest(BaseModel):
    domain: str
    email: str
    api_token: str
    project_key: str


# ── Lifespan management ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown for the FastAPI app."""
    logger.info("Starting Meeting Intelligence API...")
    logger.info("LLM Provider: %s", settings.llm_provider)
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
    if project_id not in projects:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return projects[project_id]


def update_project_state(project_id: str, updates: dict[str, Any]) -> None:
    """Update project state with new values."""
    if project_id in projects:
        projects[project_id]["state"].update(updates)


# ── REST endpoints ───────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "llm_provider": settings.llm_provider,
        "projects_count": len(projects),
    }


@app.post("/api/projects", response_model=CreateProjectResponse)
async def create_project(request: CreateProjectRequest):
    """Create a new project with a transcript and start Stage 1 parsing."""
    import time

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

    # Run Stage 1: Parse transcript
    try:
        parse_state = project["state"].copy()

        # Parse transcript
        result = parse_transcript(parse_state)
        project["state"].update(result)

        projects[project_id] = project

        logger.info("Created project %s and completed parsing", project_id)

        return CreateProjectResponse(
            project_id=project_id,
            name=request.name,
            status="parse",
        )

    except Exception as e:
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
        for p in projects.values()
    ]


@app.get("/api/projects/{project_id}")
async def get_project_state(project_id: str):
    """Get the current state of a project."""
    project = get_project(project_id)
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
        "stage1_approved": state.get("stage1_approved", False),
        "stage2_approved": state.get("stage2_approved", False),
        "stage3_approved": state.get("stage3_approved", False),
        "stage4_approved": state.get("stage4_approved", False),
        "stage5_done": state.get("stage5_done", False),
    }


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project."""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    del projects[project_id]
    return {"message": f"Project {project_id} deleted"}


# ── Stage 1 endpoints ─────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/stage/parse/approve")
async def approve_stage1(project_id: str):
    """Approve Stage 1 extraction and proceed to Stage 2."""
    project = get_project(project_id)

    try:
        # Run Stage 2: Generate questions
        state = project["state"].copy()
        state["stage1_approved"] = True
        state["current_stage"] = "clarify"

        from agent.nodes.clarify import generate_questions
        result = generate_questions(state)

        project["state"].update(result)
        return {"message": "Stage 1 approved", "next_stage": "clarify"}

    except Exception as e:
        logger.exception("Failed to approve Stage 1")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/parse/feedback")
async def submit_stage1_feedback(project_id: str, request: FeedbackRequest):
    """Submit correction feedback for Stage 1 extraction."""
    project = get_project(project_id)

    try:
        # Add feedback to messages and apply correction
        state = project["state"].copy()
        from langchain_core.messages import HumanMessage
        state["messages"].append(HumanMessage(content=request.feedback))

        result = apply_corrections(state)
        project["state"].update(result)
        return {"message": "Correction applied", "extraction": result.get("extraction")}

    except Exception as e:
        logger.exception("Failed to apply correction")
        raise HTTPException(status_code=500, detail=str(e))


# ── Stage 2 endpoints ─────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/stage/clarify/answer")
async def answer_question(project_id: str, request: AnswerRequest):
    """Answer a clarification question in Stage 2."""
    project = get_project(project_id)

    try:
        state = project["state"].copy()
        from langchain_core.messages import HumanMessage

        # Format answer as "q1: <answer>"
        answer_input = f"{request.question_id}: {request.answer}"
        state["messages"].append(HumanMessage(content=answer_input))

        result = process_answer(state)
        project["state"].update(result)
        return {"message": "Answer processed", "questions": result.get("questions", [])}

    except Exception as e:
        logger.exception("Failed to process answer")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/clarify/skip")
async def skip_question(project_id: str, request: SkipRequest):
    """Skip a clarification question in Stage 2."""
    project = get_project(project_id)

    try:
        state = project["state"].copy()
        from langchain_core.messages import HumanMessage

        # Format skip as "q1: skip <reason>"
        skip_input = f"{request.question_id}: skip {request.reason}"
        state["messages"].append(HumanMessage(content=skip_input))

        result = process_answer(state)
        project["state"].update(result)
        return {"message": "Question skipped", "questions": result.get("questions", [])}

    except Exception as e:
        logger.exception("Failed to skip question")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/clarify/done")
async def done_clarification(project_id: str):
    """Mark clarification as complete and proceed to Stage 3."""
    project = get_project(project_id)

    try:
        # Run Stage 3: Draft SoW
        state = project["state"].copy()
        state["stage2_approved"] = True
        state["current_stage"] = "sow"

        result = draft_sow(state)
        project["state"].update(result)
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
        state = project["state"].copy()
        from langchain_core.messages import HumanMessage

        state["messages"].append(HumanMessage(content=request.feedback))
        result = revise_sow(state)
        project["state"].update(result)
        return {"message": "SoW revised", "sow": result.get("sow"), "version": result.get("sow_version")}

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

    try:
        # Run Stage 4: Generate sprint plan
        state = project["state"].copy()
        state["stage3_approved"] = True
        state["current_stage"] = "sprint"

        result = generate_sprint_plan(state)
        project["state"].update(result)
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
        state = project["state"].copy()
        from langchain_core.messages import HumanMessage

        state["messages"].append(HumanMessage(content=request.feedback))
        result = adjust_sprint_plan(state)
        project["state"].update(result)
        return {"message": "Sprint plan adjusted", "sprints": result.get("sprints", [])}

    except Exception as e:
        logger.exception("Failed to adjust sprint plan")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/stage/sprint/approve")
async def approve_sprint_plan(project_id: str):
    """Approve the sprint plan and proceed to Stage 5."""
    project = get_project(project_id)

    try:
        state = project["state"].copy()
        state["stage4_approved"] = True
        state["current_stage"] = "jira"
        project["state"].update(state)
        return {"message": "Sprint plan approved", "next_stage": "jira"}

    except Exception as e:
        logger.exception("Failed to approve sprint plan")
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

    return {"message": "Jira config saved"}


@app.post("/api/projects/{project_id}/jira/test")
async def test_jira_connection(project_id: str):
    """Test Jira connection."""
    project = get_project(project_id)
    jira_config = project.get("jira_config")

    if not jira_config:
        raise HTTPException(status_code=400, detail="Jira config not set")

    try:
        from agent.jira import test_connection

        await test_connection(jira_config)
        return {"message": "Jira connection successful"}

    except Exception as e:
        logger.exception("Jira connection test failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}/jira/preview")
async def get_jira_preview(project_id: str):
    """Get preview of what will be created in Jira."""
    project = get_project(project_id)
    state = project["state"]

    tasks = state.get("tasks", [])
    sprints = state.get("sprints", [])

    return {
        "epics": list({t.get("module") for t in tasks}),
        "issues": len(tasks),
        "sprints": len(sprints),
        "tasks": tasks,
    }


@app.post("/api/projects/{project_id}/jira/sync")
async def sync_to_jira_endpoint(project_id: str):
    """Execute Jira sync."""
    project = get_project(project_id)
    jira_config = project.get("jira_config")

    if not jira_config:
        raise HTTPException(status_code=400, detail="Jira config not set. Please set it first.")

    try:
        # Add Jira config to state and run sync
        state = project["state"].copy()
        state["jira_config"] = jira_config

        result = sync_to_jira(state)
        project["state"].update(result)
        project["state"]["stage5_done"] = True
        return {"message": "Jira sync complete", "results": result.get("jira_results", [])}

    except Exception as e:
        logger.exception("Failed to sync to Jira")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)