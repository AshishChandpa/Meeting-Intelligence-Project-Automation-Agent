"""LangGraph state schema for the meeting intelligence pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from langgraph.graph import MessagesState


# ── Pydantic models for structured extraction ──────────────────────────

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
    source: str = ""  # what part of transcript referenced it


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


# ── Pipeline state ─────────────────────────────────────────────────────

class PipelineState(MessagesState):
    """Full state carried through the LangGraph pipeline.

    For now, only Stage 1 fields are active.
    We'll add Stage 2-5 fields as we build them.
    """

    # ── Stage tracking ──
    current_stage: str = "parse"  # parse | clarify | sow | sprint | jira | done

    # ── Stage 1: Transcript Parsing ──
    raw_transcript: str = ""
    extraction: dict = Field(default_factory=dict)  # Extraction model as dict
    correction_history: Annotated[list[dict], operator.add] = Field(default_factory=list)
    stage1_approved: bool = False

    # Placeholder fields for future stages (added incrementally)
    # stage2, stage3, etc. will be added when we build those stages
