"""Stage 5 node — Jira Sync.

Creates Epics → Issues → Sprints in Jira with full error reporting.
Expects jira_config to be set in state before this node runs.
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage

from agent.jira import JiraClient
from agent.state import JiraConfig, JiraResult, PipelineState

logger = logging.getLogger(__name__)


def sync_to_jira(state: PipelineState) -> dict:
    """Push the approved sprint plan to Jira.

    Flow:
        1. Test connection
        2. Create one Epic per module
        3. Create Issues for each task, linked to their Epic
        4. Create Sprints and assign issues
    """
    cfg_dict = state["jira_config"]
    if not cfg_dict:
        return {
            "messages": [AIMessage(content="❌ No Jira configuration found. Please set your Jira credentials first.")]
        }

    cfg = JiraConfig.model_validate(cfg_dict)
    client = JiraClient(
        domain=cfg.domain,
        email=cfg.email,
        api_token=cfg.api_token,
        project_key=cfg.project_key,
    )
    domain_base = f"https://{cfg.domain}"
    results: list[dict] = []

    # ── 1. Test connection ──────────────────────────────────────────────
    try:
        client.test_connection()
        logger.info("Jira connection OK")
    except Exception as e:
        return {
            "messages": [AIMessage(content=f"❌ Jira connection failed: {e}\nCheck your domain, email, and API token.")]
        }

    # ── 2. Create Epics (one per module) ───────────────────────────────
    tasks = state["tasks"]
    sprints = state["sprints"]

    # Gather unique modules from tasks
    modules = list({t["module"] for t in tasks})
    epic_key_by_module: dict[str, str] = {}

    for module_name in modules:
        try:
            epic = client.create_epic(
                title=module_name,
                description=f"Epic for {module_name} module",
            )
            epic_key_by_module[module_name] = epic["key"]
            results.append(JiraResult(
                type="epic",
                key=epic["key"],
                title=module_name,
                url=f"{domain_base}/browse/{epic['key']}",
                status="created",
            ).model_dump())
            logger.info("Created Epic: %s → %s", module_name, epic["key"])
        except Exception as e:
            results.append(JiraResult(
                type="epic", key="", title=module_name, url="",
                status="failed", error=str(e),
            ).model_dump())
            logger.error("Failed to create Epic for %s: %s", module_name, e)

    # ── 3. Create Issues ────────────────────────────────────────────────
    jira_id_by_task: dict[str, str] = {}  # task id → jira issue id

    for task in tasks:
        epic_key = epic_key_by_module.get(task["module"])
        try:
            issue = client.create_issue(
                title=task["title"],
                description=task["description"],
                issue_type=task["type"] if task["type"] != "Epic" else "Story",
                priority=task["priority"],
                story_points=task["story_points"],
                epic_key=epic_key,
            )
            jira_id_by_task[task["id"]] = issue["id"]
            results.append(JiraResult(
                type="issue",
                key=issue["key"],
                title=task["title"],
                url=f"{domain_base}/browse/{issue['key']}",
                status="created",
            ).model_dump())
            logger.info("Created issue: %s → %s", task["title"][:40], issue["key"])
        except Exception as e:
            results.append(JiraResult(
                type="issue", key="", title=task["title"], url="",
                status="failed", error=str(e),
            ).model_dump())
            logger.error("Failed to create issue '%s': %s", task["title"][:40], e)

    # ── 4. Create Sprints and assign issues ────────────────────────────
    board_id = client.get_board_id()
    if board_id is None:
        results.append(JiraResult(
            type="sprint", key="", title="Board not found", url="",
            status="failed", error="No Scrum board found for this project. Create one in Jira first.",
        ).model_dump())
    else:
        for sprint in sprints:
            try:
                jira_sprint = client.create_sprint(
                    board_id=board_id,
                    name=sprint["name"],
                    goal=sprint.get("goal", ""),
                )
                # Collect jira issue IDs for tasks in this sprint
                issue_ids = [
                    jira_id_by_task[tid]
                    for tid in sprint["task_ids"]
                    if tid in jira_id_by_task
                ]
                if issue_ids:
                    client.add_issues_to_sprint(jira_sprint["id"], issue_ids)

                results.append(JiraResult(
                    type="sprint",
                    key=str(jira_sprint["id"]),
                    title=sprint["name"],
                    url=f"{domain_base}/jira/software/projects/{cfg.project_key}/boards",
                    status="created",
                ).model_dump())
                logger.info("Created sprint: %s with %d issues", sprint["name"], len(issue_ids))
            except Exception as e:
                results.append(JiraResult(
                    type="sprint", key="", title=sprint["name"], url="",
                    status="failed", error=str(e),
                ).model_dump())
                logger.error("Failed to create sprint '%s': %s", sprint["name"], e)

    # ── Summary ─────────────────────────────────────────────────────────
    created = sum(1 for r in results if r["status"] == "created")
    failed = sum(1 for r in results if r["status"] == "failed")
    summary = f"✅ Jira sync complete: {created} items created"
    if failed:
        summary += f", ⚠️ {failed} failed (check results for details)"

    return {
        "jira_results": results,
        "stage5_done": True,
        "current_stage": "done",
        "messages": [AIMessage(content=summary)],
    }
