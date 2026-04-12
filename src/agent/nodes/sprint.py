"""Stage 4 node — Task Breakdown & Sprint Planning."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from agent.llm import complete_structured
from agent.prompts.sprint import ADJUST_SYSTEM, ADJUST_USER, SPRINT_SYSTEM, SPRINT_USER
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
