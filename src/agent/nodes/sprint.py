"""Stage 4 node — Task Breakdown & Sprint Planning."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from agent.llm import complete_structured, complete_text
from agent.prompts.sprint_enhanced import (
    ADJUST_SYSTEM,
    ADJUST_USER,
    RISK_IDENTIFICATION_SYSTEM,
    RISK_IDENTIFICATION_USER,
    SPRINT_QUESTIONS_SYSTEM,
    SPRINT_QUESTIONS_USER,
    SPRINT_SYSTEM,
    SPRINT_USER,
    TASK_QUESTIONS_SYSTEM,
    TASK_QUESTIONS_USER,
)
from agent.state import PipelineState, SprintPlan

logger = logging.getLogger(__name__)


def _validate_sprint_plan(tasks: list[dict], sprints: list[dict], base_warnings: list[str] | None = None) -> list[str]:
    """Validate capacity, dependency order, and task assignment consistency."""
    warnings = list(base_warnings or [])

    task_ids = {t["id"] for t in tasks}
    task_by_id = {t["id"]: t for t in tasks}
    sprint_index_by_task: dict[str, int] = {}
    seen_assignments: dict[str, int] = {}

    for idx, sprint in enumerate(sprints):
        if sprint.get("total_points", 0) > 40:
            warnings.append(f"{sprint['name']} has {sprint['total_points']} points (exceeds 40-point limit)")
        for task_id in sprint.get("task_ids", []):
            seen_assignments[task_id] = seen_assignments.get(task_id, 0) + 1
            sprint_index_by_task[task_id] = idx

    for task_id, count in seen_assignments.items():
        if count > 1:
            warnings.append(f"Task {task_id} appears in multiple sprints ({count} times)")

    unassigned = sorted(tid for tid in task_ids if tid not in sprint_index_by_task)
    if unassigned:
        warnings.append(f"Unassigned tasks: {', '.join(unassigned)}")

    for task in tasks:
        current_task_id = task["id"]
        current_sprint_idx = sprint_index_by_task.get(current_task_id)
        if current_sprint_idx is None:
            continue
        for dep_id in task.get("dependencies", []):
            if dep_id not in task_ids:
                warnings.append(f"Task {current_task_id} depends on missing task {dep_id}")
                continue
            dep_sprint_idx = sprint_index_by_task.get(dep_id)
            if dep_sprint_idx is None:
                warnings.append(f"Task {current_task_id} depends on unassigned task {dep_id}")
                continue
            if dep_sprint_idx > current_sprint_idx:
                warnings.append(
                    f"Dependency order issue: {current_task_id} is scheduled before dependency {dep_id}"
                )

    # Transcript-specific requirement: returns module should be in sprint 1 when present.
    if sprints:
        sprint_1_task_ids = set(sprints[0].get("task_ids", []))
        returns_tasks = [t["id"] for t in tasks if "return" in (t.get("module", "") + " " + t.get("title", "")).lower()]
        for task_id in returns_tasks:
            if task_id not in sprint_1_task_ids:
                warnings.append(f"Returns-related task {task_id} is not in Sprint 1")

    # Deduplicate while preserving order.
    deduped = []
    seen = set()
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        deduped.append(warning)
    return deduped


def _recalculate_sprint_totals(tasks: list[dict], sprints: list[dict]) -> list[dict]:
    task_points = {t["id"]: t.get("story_points", 0) for t in tasks}
    updated = []
    for sprint in sprints:
        copied = dict(sprint)
        copied["total_points"] = sum(task_points.get(tid, 0) for tid in copied.get("task_ids", []))
        updated.append(copied)
    return updated


def move_task_between_sprints(tasks: list[dict], sprints: list[dict], task_id: str, target_sprint_name: str) -> tuple[list[dict], list[str]]:
    """Move a task to a target sprint and return updated sprints + validation warnings."""
    if task_id not in {t["id"] for t in tasks}:
        raise ValueError(f"Task '{task_id}' not found")

    target_index = next((i for i, s in enumerate(sprints) if s.get("name") == target_sprint_name), None)
    if target_index is None:
        raise ValueError(f"Sprint '{target_sprint_name}' not found")

    updated_sprints = []
    for i, sprint in enumerate(sprints):
        task_ids = [tid for tid in sprint.get("task_ids", []) if tid != task_id]
        if i == target_index:
            task_ids.append(task_id)
        copied = dict(sprint)
        copied["task_ids"] = task_ids
        updated_sprints.append(copied)

    updated_sprints = _recalculate_sprint_totals(tasks, updated_sprints)
    warnings = _validate_sprint_plan(tasks, updated_sprints)
    return updated_sprints, warnings


def generate_sprint_plan(state: PipelineState) -> dict:
    """Generate tasks and sprint plan from the approved SoW."""
    logger.info("Generating sprint plan...")

    messages = [
        {"role": "system", "content": SPRINT_SYSTEM},
        {
            "role": "user",
            "content": SPRINT_USER.format(
                sow=state["sow"],
                extraction=json.dumps(state["extraction"], indent=2),
            ),
        },
    ]

    result: SprintPlan = complete_structured(messages, schema=SprintPlan)

    sprints_data = _recalculate_sprint_totals(
        [t.model_dump() for t in result.tasks],
        [s.model_dump() for s in result.sprints],
    )
    tasks_data = [t.model_dump() for t in result.tasks]
    warnings = _validate_sprint_plan(tasks_data, sprints_data, base_warnings=list(result.warnings))
    total_tasks = len(tasks_data)
    total_sprints = len(sprints_data)

    return {
        "tasks": tasks_data,
        "sprints": sprints_data,
        "sprint_warnings": warnings,
        "current_stage": "sprint",
        "messages": [
            AIMessage(
                content=(
                    f"Sprint plan ready: {total_tasks} tasks across {total_sprints} sprints. "
                    + (f"⚠️ Warnings: {'; '.join(warnings)}" if warnings else "No capacity issues.")
                    + " Review the plan, request adjustments, or type 'approve' to sync to Jira."
                )
            )
        ],
    }


def adjust_sprint_plan(state: PipelineState) -> dict:
    """Apply user-requested adjustments to the sprint plan."""
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_messages:
        return {}

    change = user_messages[-1].content
    logger.info("Adjusting sprint plan: %s", change[:80])

    messages = [
        {"role": "system", "content": ADJUST_SYSTEM},
        {
            "role": "user",
            "content": ADJUST_USER.format(
                tasks=json.dumps(state["tasks"], indent=2),
                sprints=json.dumps(state["sprints"], indent=2),
                change=change,
            ),
        },
    ]

    result: SprintPlan = complete_structured(messages, schema=SprintPlan)

    tasks_data = [t.model_dump() for t in result.tasks]
    sprints_data = _recalculate_sprint_totals(tasks_data, [s.model_dump() for s in result.sprints])
    warnings = _validate_sprint_plan(tasks_data, sprints_data)

    return {
        "tasks": tasks_data,
        "sprints": sprints_data,
        "sprint_warnings": warnings,
        "messages": [
            AIMessage(
                content=(
                    f"Plan updated: \"{change}\". "
                    + (f"⚠️ {'; '.join(warnings)}" if warnings else "")
                    + " Type more changes or 'approve' to proceed."
                )
            )
        ],
    }


def generate_task_questions(state: PipelineState) -> dict:
    """Generate questions about tasks that lack sufficient detail.

    This reviews the task breakdown and identifies tasks that need more
    information for accurate estimation.
    """
    messages = [
        {"role": "system", "content": TASK_QUESTIONS_SYSTEM},
        {
            "role": "user",
            "content": TASK_QUESTIONS_USER.format(
                tasks=json.dumps(state["tasks"], indent=2),
                sprints=json.dumps(state["sprints"], indent=2),
            ),
        },
    ]

    task_questions = complete_text(messages)

    logger.info("Generated task detail questions")

    return {
        "task_questions": task_questions,
        "messages": [
            AIMessage(
                content=(
                    "I've identified tasks that need more detail for accurate estimation:\n\n"
                    f"{task_questions}\n\n"
                    "Please provide clarification on these tasks to improve the sprint plan."
                )
            )
        ],
    }


def generate_sprint_questions(state: PipelineState) -> dict:
    """Generate questions about sprint organization and planning.

    This reviews the sprint structure for organizational issues,
    capacity planning, and sequencing concerns.
    """
    messages = [
        {"role": "system", "content": SPRINT_QUESTIONS_SYSTEM},
        {
            "role": "user",
            "content": SPRINT_QUESTIONS_USER.format(
                sprints=json.dumps(state["sprints"], indent=2),
                tasks=json.dumps(state["tasks"], indent=2),
            ),
        },
    ]

    sprint_questions = complete_text(messages)

    logger.info("Generated sprint planning questions")

    return {
        "sprint_questions": sprint_questions,
        "messages": [
            AIMessage(
                content=(
                    "I've reviewed the sprint organization and identified potential improvements:\n\n"
                    f"{sprint_questions}\n\n"
                    "Please consider these questions to optimize the sprint structure."
                )
            )
        ],
    }


def identify_risks(state: PipelineState) -> dict:
    """Identify risks across the sprint plan.

    This analyzes the tasks and sprints for technical, schedule, scope,
    and resource risks, generating mitigation questions.
    """
    messages = [
        {"role": "system", "content": RISK_IDENTIFICATION_SYSTEM},
        {
            "role": "user",
            "content": RISK_IDENTIFICATION_USER.format(
                tasks=json.dumps(state["tasks"], indent=2),
                sprints=json.dumps(state["sprints"], indent=2),
                sow=state["sow"],
            ),
        },
    ]

    risk_findings = complete_text(messages)

    logger.info("Identified sprint plan risks")

    return {
        "risk_findings": risk_findings,
        "messages": [
            AIMessage(
                content=(
                    "I've conducted a risk assessment on the sprint plan:\n\n"
                    f"{risk_findings}\n\n"
                    "Please review these risks and provide mitigation strategies where needed."
                )
            )
        ],
    }
