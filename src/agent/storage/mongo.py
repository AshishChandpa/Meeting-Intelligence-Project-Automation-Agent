from __future__ import annotations

from copy import deepcopy
from typing import Any

from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict


class MongoProjectRepository:
    """Mongo-backed project repository with in-memory cache for mutation ergonomics."""

    def __init__(self, uri: str, database: str, collection: str):
        try:
            from pymongo import MongoClient
        except Exception as exc:  # pragma: no cover - depends on local install
            raise RuntimeError(
                "Mongo backend selected but pymongo is not installed. Run: uv sync"
            ) from exc

        self._client = MongoClient(uri)
        self._collection = self._client[database][collection]
        self._projects: dict[str, dict[str, Any]] = {}
        self._load_cache()

    def _serialize_messages(self, state: dict[str, Any]) -> dict[str, Any]:
        serialized = dict(state)
        messages = serialized.get("messages", [])
        if messages and isinstance(messages, list):
            if all(isinstance(msg, BaseMessage) for msg in messages):
                serialized["messages"] = messages_to_dict(messages)
        return serialized

    def _deserialize_messages(self, state: dict[str, Any]) -> dict[str, Any]:
        deserialized = dict(state)
        messages = deserialized.get("messages", [])
        if (
            isinstance(messages, list)
            and messages
            and all(isinstance(item, dict) and "type" in item and "data" in item for item in messages)
        ):
            deserialized["messages"] = messages_from_dict(messages)
        return deserialized

    def _serialize_project(self, project: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(project)
        payload["state"] = self._serialize_messages(payload.get("state", {}))
        payload["_id"] = payload["id"]
        return payload

    def _deserialize_project(self, document: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(document)
        payload.pop("_id", None)
        payload["state"] = self._deserialize_messages(payload.get("state", {}))
        return payload

    def _load_cache(self) -> None:
        for doc in self._collection.find():
            project = self._deserialize_project(doc)
            self._projects[project["id"]] = project

    def get(self, project_id: str) -> dict[str, Any] | None:
        return self._projects.get(project_id)

    def upsert(self, project: dict[str, Any]) -> None:
        self._projects[project["id"]] = project
        serialized = self._serialize_project(project)
        self._collection.replace_one({"_id": project["id"]}, serialized, upsert=True)

    def delete(self, project_id: str) -> bool:
        self._projects.pop(project_id, None)
        result = self._collection.delete_one({"_id": project_id})
        return result.deleted_count > 0

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._projects.values())

    def count(self) -> int:
        return len(self._projects)

