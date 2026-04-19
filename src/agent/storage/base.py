from __future__ import annotations

from typing import Any, Protocol


ProjectRecord = dict[str, Any]


class ProjectRepository(Protocol):
    """Contract for project persistence backends."""

    def get(self, project_id: str) -> ProjectRecord | None:
        ...

    def upsert(self, project: ProjectRecord) -> None:
        ...

    def delete(self, project_id: str) -> bool:
        ...

    def list_all(self) -> list[ProjectRecord]:
        ...

    def count(self) -> int:
        ...

