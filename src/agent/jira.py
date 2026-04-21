"""Jira REST API service — handles all Atlassian API calls.

Uses httpx for async-compatible sync calls (simple enough for our use case).
No heavy SDK — just direct REST calls against Jira's v3 + Agile APIs.
"""

from __future__ import annotations

import logging
import time
from base64 import b64encode

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubles each retry


class JiraClient:
    """Thin Jira REST client with retry and rate-limit handling."""

    def __init__(self, domain: str, email: str, api_token: str, project_key: str):
        self.base_url = f"https://{domain}/rest/api/3"
        self.agile_url = f"https://{domain}/rest/agile/1.0"
        self.project_key = project_key
        token = b64encode(f"{email}:{api_token}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── Internal helpers ────────────────────────────────────────────────

    def _request(self, method: str, url: str, **kwargs) -> dict:
        """Make an HTTP request with retry + backoff on rate limit."""
        for attempt in range(MAX_RETRIES):
            response = httpx.request(method, url, headers=self.headers, timeout=30, **kwargs)

            if response.status_code == 429:
                wait = RETRY_BACKOFF ** attempt
                logger.warning("Jira rate limit hit. Waiting %ds...", wait)
                time.sleep(wait)
                continue

            # Enhanced error logging for 400/403/404 errors
            if response.status_code >= 400:
                try:
                    error_detail = response.json()
                    error_msg = error_detail.get("errors", [{}])[0].get("message", str(error_detail))
                    logger.error(f"[JIRA API] {method} {url} failed: {response.status_code} - {error_msg}")
                except:
                    logger.error(f"[JIRA API] {method} {url} failed: {response.status_code} - {response.text[:200]}")

            response.raise_for_status()
            return response.json() if response.content else {}

        raise RuntimeError(f"Jira API failed after {MAX_RETRIES} retries: {url}")

    # ── Public API ──────────────────────────────────────────────────────

    def test_connection(self) -> dict:
        """Test credentials and project access. Returns project info or raises."""
        return self._request("GET", f"{self.base_url}/project/{self.project_key}")

    def get_board_id(self) -> int | None:
        """Get the Scrum board ID for this project (needed for sprint creation)."""
        data = self._request("GET", f"{self.agile_url}/board", params={"projectKeyOrId": self.project_key})
        boards = data.get("values", [])
        return boards[0]["id"] if boards else None

    def create_epic(self, title: str, description: str) -> dict:
        """Create an Epic issue. Returns {key, id, url}."""
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
                },
                "issuetype": {"name": "Epic"},
                "customfield_10011": title,  # Epic Name field
            }
        }
        result = self._request("POST", f"{self.base_url}/issue", json=payload)
        return {
            "key": result["key"],
            "id": result["id"],
            "url": f"https://{self.base_url.split('/rest')[0].split('https://')[1]}/browse/{result['key']}",
        }

    def create_issue(self, title: str, description: str, issue_type: str,
                     priority: str, story_points: int, epic_key: str | None = None) -> dict:
        """Create a Story or Task issue linked to an Epic."""
        fields: dict = {
            "project": {"key": self.project_key},
            "summary": title,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
            },
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
        }

        # Only add story points if they have a value
        if story_points and story_points > 0:
            fields["customfield_10016"] = story_points  # Story Points field (may not exist in Kanban)

        if epic_key:
            fields["customfield_10014"] = epic_key  # Epic Link field

        try:
            result = self._request("POST", f"{self.base_url}/issue", json={"fields": fields})
        except Exception as e:
            # If story points field is causing the error, retry without it
            if story_points and "customfield_10016" in str(e):
                logger.warning(f"[JIRA] Story Points field not available, retrying without it")
                del fields["customfield_10016"]
                result = self._request("POST", f"{self.base_url}/issue", json={"fields": fields})
            else:
                raise

        domain = self.base_url.split("/rest")[0].split("https://")[1]
        return {
            "key": result["key"],
            "id": result["id"],
            "url": f"https://{domain}/browse/{result['key']}",
        }

    def create_sprint(self, board_id: int, name: str, goal: str) -> dict:
        """Create a sprint on the board. Returns {id, name}."""
        payload = {"name": name, "goal": goal, "originBoardId": board_id}
        result = self._request("POST", f"{self.agile_url}/sprint", json=payload)
        return {"id": result["id"], "name": result["name"]}

    def add_issues_to_sprint(self, sprint_id: int, issue_ids: list[str]) -> None:
        """Move a batch of issue IDs into a sprint."""
        self._request(
            "POST",
            f"{self.agile_url}/sprint/{sprint_id}/issue",
            json={"issues": issue_ids},
        )
