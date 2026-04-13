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

    # Recalculate sprint totals from task story points
    task_points = {t.id: t.story_points for t in result.tasks}
    sprints_data = []
    warnings = list(result.warnings)

    for sprint in result.sprints:
        total = sum(task_points.get(tid, 0) for tid in sprint.task_ids)
        sprint_dict = sprint.model_dump()
        sprint_dict["total_points"] = total
        sprints_data.append(sprint_dict)
        if total > 40:
            warnings.append(f"{sprint.name} has {total} points (exceeds 40-point limit)")

    tasks_data = [t.model_dump() for t in result.tasks]
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

    task_points = {t.id: t.story_points for t in result.tasks}
    sprints_data = []
    warnings = []

    for sprint in result.sprints:
        total = sum(task_points.get(tid, 0) for tid in sprint.task_ids)
        sprint_dict = sprint.model_dump()
        sprint_dict["total_points"] = total
        sprints_data.append(sprint_dict)
        if total > 40:
            warnings.append(f"{sprint.name} has {total} points (exceeds 40-point limit)")

    return {
        "tasks": [t.model_dump() for t in result.tasks],
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
