from __future__ import annotations

from typing import Any


class InMemoryProjectRepository:
    """Default storage backend, equivalent to prior in-process dict behavior."""

    def __init__(self):
        self._projects: dict[str, dict[str, Any]] = {}

    def get(self, project_id: str) -> dict[str, Any] | None:
        return self._projects.get(project_id)

    def upsert(self, project: dict[str, Any]) -> None:
        self._projects[project["id"]] = project

    def delete(self, project_id: str) -> bool:
        return self._projects.pop(project_id, None) is not None

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._projects.values())

    def count(self) -> int:
        return len(self._projects)

