"""LangGraph state schema for the full meeting intelligence pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from langgraph.graph import MessagesState


# ── Stage 1: Extraction models ─────────────────────────────────────────

class Module(BaseModel):
    name: str
    description: str
    priority: Literal["High", "Medium", "Low"]
    deadline: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"


class Requirement(BaseModel):
    description: str
    module: str
    type: Literal["Functional", "Non-Functional", "Integration"]
    confidence: Literal["high", "medium", "low"] = "medium"


class Integration(BaseModel):
    system: str
    purpose: str
    confidence: Literal["high", "medium", "low"] = "medium"


class Constraint(BaseModel):
    description: str
    confidence: Literal["high", "medium", "low"] = "medium"


class Assumption(BaseModel):
    description: str
    confidence: Literal["high", "medium", "low"] = "low"


class Unknown(BaseModel):
    description: str
    source: str = ""


class Extraction(BaseModel):
    """Structured output from Stage 1 transcript parsing."""
    project_name: str = ""
    client_name: str = ""
    vendor_name: str = ""
    modules: list[Module] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    integrations: list[Integration] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)


# ── Stage 2: Clarification models ─────────────────────────────────────

class ClarificationQuestion(BaseModel):
    id: str                        # e.g. "q1"
    question: str
    context: str                   # why this is being asked / transcript ref
    status: Literal["open", "answered", "skipped"] = "open"
    answer: str = ""
    skip_reason: str = ""


class ClarificationQuestions(BaseModel):
    """Structured output: list of clarification questions."""
    questions: list[ClarificationQuestion] = Field(default_factory=list)


# ── Stage 3: Scope of Work models ─────────────────────────────────────

class SoWRevision(BaseModel):
    version: int
    feedback: str
    changelog: str                 # bullet summary of what changed


# ── Stage 4: Sprint planning models ───────────────────────────────────

class Task(BaseModel):
    id: str                        # e.g. "t1"
    title: str
    description: str
    module: str
    type: Literal["Epic", "Story", "Task"]
    priority: Literal["High", "Medium", "Low"]
    story_points: Literal[1, 2, 3, 5, 8, 13]
    dependencies: list[str] = Field(default_factory=list)   # task ids
    acceptance_criteria: list[str] = Field(default_factory=list)


class Sprint(BaseModel):
    name: str                      # e.g. "Sprint 1 — Returns Core"
    goal: str
    task_ids: list[str] = Field(default_factory=list)
    total_points: int = 0


class SprintPlan(BaseModel):
    """Structured output from Stage 4."""
    tasks: list[Task] = Field(default_factory=list)
    sprints: list[Sprint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)  # e.g. sprint over 40pts


# ── Stage 5: Jira models ───────────────────────────────────────────────

class JiraConfig(BaseModel):
    domain: str       # e.g. "mycompany.atlassian.net"
    email: str
    api_token: str
    project_key: str  # e.g. "PROJ"


class JiraResult(BaseModel):
    type: str         # "epic" | "issue" | "sprint"
    key: str          # e.g. "PROJ-1"
    title: str
    url: str
    status: Literal["created", "failed"] = "created"
    error: str = ""


# ── Pipeline state ─────────────────────────────────────────────────────

class PipelineState(MessagesState):
    """Full state carried through the LangGraph pipeline."""

    # ── Stage tracking ──
    current_stage: str = "parse"   # parse | clarify | sow | sprint | jira | done
    graph_checkpoint_id: str = ""
    graph_next_nodes: list[str] = Field(default_factory=list)
    pending_interrupts: list[dict] = Field(default_factory=list)
    last_checkpoint_at: float | None = None

    # ── Stage 1: Transcript Parsing ──
    raw_transcript: str = ""
    extraction: dict = Field(default_factory=dict)
    correction_history: Annotated[list[dict], operator.add] = Field(default_factory=list)
    gap_questions: str = ""         # gap analysis from enhanced extraction
    preprocessing_context: dict = Field(default_factory=dict)  # preprocessed transcript structure
    stage1_approved: bool = False

    # ── Stage 2: Clarification Loop ──
    questions: list[dict] = Field(default_factory=list)   # list[ClarificationQuestion]
    human_questions: str = ""       # categorized questions for human review
    stage2_approved: bool = False

    # ── Stage 3: Scope of Work ──
    sow: str = ""                  # markdown text
    sow_version: int = 0
    sow_revisions: Annotated[list[dict], operator.add] = Field(default_factory=list)
    sow_gaps: str = ""             # gap detection from enhanced SoW
    stage3_approved: bool = False

    # ── Stage 4: Sprint Planning ──
    tasks: list[dict] = Field(default_factory=list)       # list[Task]
    sprints: list[dict] = Field(default_factory=list)     # list[Sprint]
    sprint_warnings: list[str] = Field(default_factory=list)
    task_questions: str = ""        # questions about task details
    sprint_questions: str = ""      # questions about sprint organization
    risk_findings: str = ""         # risk assessment results
    stage4_approved: bool = False

    # ── Stage 5: Jira ──
    jira_config: dict = Field(default_factory=dict)       # JiraConfig
    jira_preview: dict = Field(default_factory=dict)
    jira_pending_batch: str = ""
    jira_last_batch: str = ""
    jira_last_batch_results: list[dict] = Field(default_factory=list)
    jira_results: Annotated[list[dict], operator.add] = Field(default_factory=list)
    # Track staged Jira sync progress/state for batch-confirmed creation flow.
    jira_batch_status: dict[str, str] = Field(default_factory=dict)      # epics|issues|sprints -> pending|done|failed
    jira_epic_key_by_module: dict[str, str] = Field(default_factory=dict)
    jira_issue_id_by_task: dict[str, str] = Field(default_factory=dict)
    jira_board_id: int | None = None
    stage5_done: bool = False
