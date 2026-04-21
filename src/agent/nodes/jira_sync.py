"""Stage 5 node — Jira Sync.

Creates Epics → Issues → Sprints in Jira with full error reporting.
Expects jira_config to be set in state before this node runs.
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command

from agent.jira import JiraClient
from agent.state import JiraConfig, JiraResult, PipelineState

logger = logging.getLogger(__name__)

JiraBatch = Literal["epics", "issues", "sprints"]


def _batch_state(results: list[dict]) -> Literal["done", "failed"]:
    return "failed" if any(result.get("status") == "failed" for result in results) else "done"


def prepare_jira_batch_preview(state: PipelineState, batch: JiraBatch) -> dict:
    """Prepare Stage 5 preview payload and indicate the next Jira batch awaiting confirmation."""
    preview = build_jira_preview(state)
    batch_labels = {
        "epics": "Epics",
        "issues": "Issues",
        "sprints": "Sprints",
    }
    counts = {
        "epics": len(preview["epics"]),
        "issues": len(preview["issues"]),
        "sprints": len(preview["sprints"]),
    }
    return {
        "current_stage": "jira",
        "jira_preview": preview,
        "jira_pending_batch": batch,
        "messages": [
            AIMessage(
                content=(
                    f"Stage 5 ready: review {batch_labels[batch]} preview and confirm batch creation. "
                    f"Counts → epics: {counts['epics']}, issues: {counts['issues']}, sprints: {counts['sprints']}."
                )
            )
        ],
    }


def create_jira_batch(state: PipelineState, batch: JiraBatch) -> dict:
    """Create a single Jira batch and retain batch-local metadata for API responses."""
    result = sync_to_jira_batch(state, batch)
    batch_status = result.get("jira_batch_status", {}).get(batch, state.get("jira_batch_status", {}).get(batch, "failed"))
    return {
        **result,
        "jira_last_batch": batch,
        "jira_last_batch_results": result.get("jira_results", []),
        "jira_pending_batch": "",
        "current_stage": "done" if batch == "sprints" and batch_status == "done" else "jira",
    }


def create_epics_batch(state: PipelineState) -> Command[Literal["preview_jira_issues", "review_jira_epics"]]:
    result = create_jira_batch(state, "epics")
    goto = "preview_jira_issues" if result.get("jira_batch_status", {}).get("epics") == "done" else "review_jira_epics"
    return Command(goto=goto, update=result)


def create_issues_batch(state: PipelineState) -> Command[Literal["preview_jira_sprints", "review_jira_issues"]]:
    result = create_jira_batch(state, "issues")
    goto = "preview_jira_sprints" if result.get("jira_batch_status", {}).get("issues") == "done" else "review_jira_issues"
    return Command(goto=goto, update=result)


def create_sprints_batch(state: PipelineState) -> Command[Literal["stage5_done", "review_jira_sprints"]]:
    result = create_jira_batch(state, "sprints")
    goto = "stage5_done" if result.get("jira_batch_status", {}).get("sprints") == "done" else "review_jira_sprints"
    return Command(goto=goto, update=result)


def build_jira_preview(state: PipelineState) -> dict:
    """Build a deterministic preview payload for Stage 5 confirmation UI."""
    tasks = state.get("tasks", [])
    sprints = state.get("sprints", [])
    modules = sorted({task.get("module", "") for task in tasks if task.get("module")})
    return {
        "epics": [{"module": module, "title": module} for module in modules],
        "issues": [
            {
                "task_id": task.get("id", ""),
                "title": task.get("title", ""),
                "module": task.get("module", ""),
                "type": task.get("type", "Story"),
            }
            for task in tasks
        ],
        "sprints": [
            {
                "name": sprint.get("name", ""),
                "goal": sprint.get("goal", ""),
                "task_ids": sprint.get("task_ids", []),
            }
            for sprint in sprints
        ],
    }


def sync_to_jira_batch(state: PipelineState, batch: JiraBatch) -> dict:
    """Sync exactly one Jira batch so UI can gate each step with explicit confirmation."""
    cfg_dict = state.get("jira_config")
    if not cfg_dict:
        return {
            "messages": [AIMessage(content="No Jira configuration found. Please set your Jira credentials first.")]
        }

    cfg = JiraConfig.model_validate(cfg_dict)
    client = JiraClient(
        domain=cfg.domain,
        email=cfg.email,
        api_token=cfg.api_token,
        project_key=cfg.project_key,
    )
    domain_base = f"https://{cfg.domain}"
    tasks = state.get("tasks", [])
    sprints = state.get("sprints", [])
    results: list[dict] = []

    try:
        client.test_connection()
    except Exception as e:
        return {
            "messages": [AIMessage(content=f"Jira connection failed: {e}")],
        }

    epic_key_by_module: dict[str, str] = dict(state.get("jira_epic_key_by_module", {}))
    jira_id_by_task: dict[str, str] = dict(state.get("jira_issue_id_by_task", {}))

    if batch == "epics":
        modules = sorted({task.get("module", "") for task in tasks if task.get("module")})
        logger.info(f"[JIRA SYNC] Creating {len(modules)} epics for modules: {modules}")
        for module_name in modules:
            if module_name in epic_key_by_module:
                logger.info(f"[JIRA SYNC] Skipping epic '{module_name}' - already exists with key {epic_key_by_module[module_name]}")
                continue
            try:
                logger.info(f"[JIRA SYNC] Creating epic: {module_name}")
                epic = client.create_epic(
                    title=module_name,
                    description=f"Epic for {module_name} module",
                )
                epic_key_by_module[module_name] = epic["key"]
                results.append(
                    JiraResult(
                        type="epic",
                        key=epic["key"],
                        title=module_name,
                        url=f"{domain_base}/browse/{epic['key']}",
                        status="created",
                    ).model_dump()
                )
            except Exception as e:
                results.append(
                    JiraResult(
                        type="epic",
                        key="",
                        title=module_name,
                        url="",
                        status="failed",
                        error=str(e),
                    ).model_dump()
                )
                logger.error(f"[JIRA SYNC] Failed to create epic '{module_name}': {e}")

        batch_status = _batch_state(results)
        return {
            "jira_results": results,
            "jira_epic_key_by_module": epic_key_by_module,
            "jira_batch_status": {**state.get("jira_batch_status", {}), "epics": batch_status},
            "messages": [AIMessage(content=f"Epics batch {batch_status}: {len(results)} attempted")],
        }

    if batch == "issues":
        logger.info(f"[JIRA SYNC] Creating {len(tasks)} issues")
        for task in tasks:
            task_id = task.get("id", "")
            if task_id in jira_id_by_task:
                logger.info(f"[JIRA SYNC] Skipping issue '{task.get('title')}' - already exists")
                continue
            epic_key = epic_key_by_module.get(task.get("module", ""))
            try:
                logger.info(f"[JIRA SYNC] Creating issue: {task['title']} (type: {task.get('type')}, epic: {epic_key})")
                issue = client.create_issue(
                    title=task["title"],
                    description=task["description"],
                    issue_type=task["type"] if task["type"] != "Epic" else "Story",
                    priority=task["priority"],
                    story_points=task["story_points"],
                    epic_key=epic_key,
                )
                jira_id_by_task[task_id] = issue["id"]
                results.append(
                    JiraResult(
                        type="issue",
                        key=issue["key"],
                        title=task["title"],
                        url=f"{domain_base}/browse/{issue['key']}",
                        status="created",
                    ).model_dump()
                )
            except Exception as e:
                results.append(
                    JiraResult(
                        type="issue",
                        key="",
                        title=task.get("title", ""),
                        url="",
                        status="failed",
                        error=str(e),
                    ).model_dump()
                )
                logger.error(f"[JIRA SYNC] Failed to create issue '{task.get('title')}': {e}")

        batch_status = _batch_state(results)
        return {
            "jira_results": results,
            "jira_issue_id_by_task": jira_id_by_task,
            "jira_batch_status": {**state.get("jira_batch_status", {}), "issues": batch_status},
            "messages": [AIMessage(content=f"Issues batch {batch_status}: {len(results)} attempted")],
        }

    board_id = state.get("jira_board_id")
    if board_id is None:
        board_id = client.get_board_id()

    if board_id is None:
        results.append(
            JiraResult(
                type="sprint",
                key="",
                title="Board not found",
                url="",
                status="failed",
                error="No Scrum board found for this project. Create one in Jira first.",
            ).model_dump()
        )
        return {
            "jira_results": results,
            "jira_batch_status": {**state.get("jira_batch_status", {}), "sprints": "failed"},
            "messages": [AIMessage(content="Sprints batch failed: no Scrum board found")],
        }

    for sprint in sprints:
        try:
            jira_sprint = client.create_sprint(
                board_id=board_id,
                name=sprint["name"],
                goal=sprint.get("goal", ""),
            )
            issue_ids = [
                jira_id_by_task[tid]
                for tid in sprint.get("task_ids", [])
                if tid in jira_id_by_task
            ]
            if issue_ids:
                client.add_issues_to_sprint(jira_sprint["id"], issue_ids)

            results.append(
                JiraResult(
                    type="sprint",
                    key=str(jira_sprint["id"]),
                    title=sprint["name"],
                    url=f"{domain_base}/jira/software/projects/{cfg.project_key}/boards",
                    status="created",
                ).model_dump()
            )
        except Exception as e:
            results.append(
                JiraResult(
                    type="sprint",
                    key="",
                    title=sprint.get("name", ""),
                    url="",
                    status="failed",
                    error=str(e),
                ).model_dump()
            )

    batch_status = _batch_state(results)
    return {
        "jira_results": results,
        "jira_board_id": board_id,
        "jira_batch_status": {**state.get("jira_batch_status", {}), "sprints": batch_status},
        "messages": [AIMessage(content=f"Sprints batch {batch_status}: {len(results)} attempted")],
    }


def sync_to_jira(state: PipelineState) -> dict:
    """Push the approved sprint plan to Jira.

    Flow:
        1. Test connection
        2. Create one Epic per module
        3. Create Issues for each task, linked to their Epic
        4. Create Sprints and assign issues
    """
    aggregate_results: list[dict] = []
    working_state: dict = dict(state)

    batches: tuple[JiraBatch, JiraBatch, JiraBatch] = ("epics", "issues", "sprints")
    for batch in batches:
        batch_result = sync_to_jira_batch(working_state, batch)
        for key, value in batch_result.items():
            if key == "jira_results":
                aggregate_results.extend(value)
            else:
                working_state[key] = value

    created = sum(1 for r in aggregate_results if r["status"] == "created")
    failed = sum(1 for r in aggregate_results if r["status"] == "failed")
    summary = f"✅ Jira sync complete: {created} items created"
    if failed:
        summary += f", ⚠️ {failed} failed (check results for details)"

    return {
        "jira_results": aggregate_results,
        "jira_epic_key_by_module": working_state.get("jira_epic_key_by_module", {}),
        "jira_issue_id_by_task": working_state.get("jira_issue_id_by_task", {}),
        "jira_board_id": working_state.get("jira_board_id"),
        "jira_batch_status": working_state.get("jira_batch_status", {}),
        "stage5_done": True,
        "current_stage": "done",
        "messages": [AIMessage(content=summary)],
    }
