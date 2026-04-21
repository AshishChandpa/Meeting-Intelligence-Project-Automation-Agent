"""LangGraph checkpoint backends for memory and Mongo persistence."""

from __future__ import annotations

import base64
from collections import defaultdict
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from agent.config import Settings


def _encode_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode_bytes(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _encode_typed(value: tuple[str, bytes]) -> dict[str, str]:
    type_name, payload = value
    return {"type": type_name, "payload": _encode_bytes(payload)}


def _decode_typed(value: dict[str, str]) -> tuple[str, bytes]:
    return value["type"], _decode_bytes(value["payload"])


class MongoPersistentCheckpointer(InMemorySaver):
    """Persist LangGraph checkpoints in Mongo while reusing InMemorySaver semantics."""

    def __init__(self, uri: str, database: str, collection: str):
        try:
            from pymongo import MongoClient
        except Exception as exc:  # pragma: no cover - depends on local install
            raise RuntimeError(
                "Mongo checkpoint backend selected but pymongo is not installed. Run: uv sync"
            ) from exc

        super().__init__()
        self._client = MongoClient(uri)
        self._collection = self._client[database][collection]
        self._loaded_threads: set[str] = set()

    def _ensure_thread_loaded(self, thread_id: str) -> None:
        if thread_id in self._loaded_threads:
            return

        document = self._collection.find_one({"_id": thread_id})
        if not document:
            self._loaded_threads.add(thread_id)
            return

        storage_doc = document.get("storage", {})
        for checkpoint_ns, checkpoints in storage_doc.items():
            for checkpoint_id, saved in checkpoints.items():
                self.storage[thread_id][checkpoint_ns][checkpoint_id] = (
                    _decode_typed(saved["checkpoint"]),
                    _decode_typed(saved["metadata"]),
                    saved.get("parent_checkpoint_id"),
                )

        writes_doc = document.get("writes", {})
        for composite_key, entries in writes_doc.items():
            checkpoint_ns, checkpoint_id = composite_key.split("::", 1)
            outer_key = (thread_id, checkpoint_ns, checkpoint_id)
            for entry in entries:
                inner_key = (entry["task_id"], entry["index"])
                self.writes[outer_key][inner_key] = (
                    entry["task_id"],
                    entry["channel"],
                    _decode_typed(entry["value"]),
                    entry.get("task_path", ""),
                )

        blobs_doc = document.get("blobs", [])
        for blob in blobs_doc:
            self.blobs[(thread_id, blob["checkpoint_ns"], blob["channel"], blob["version"])] = _decode_typed(blob["value"])

        self._loaded_threads.add(thread_id)

    def _persist_thread(self, thread_id: str) -> None:
        self._ensure_thread_loaded(thread_id)
        storage_doc: dict[str, dict[str, Any]] = {}
        for checkpoint_ns, checkpoints in list(self.storage.get(thread_id, {}).items()):
            ns_doc: dict[str, Any] = {}
            for checkpoint_id, saved in list(checkpoints.items()):
                checkpoint, metadata, parent_checkpoint_id = saved
                ns_doc[checkpoint_id] = {
                    "checkpoint": _encode_typed(checkpoint),
                    "metadata": _encode_typed(metadata),
                    "parent_checkpoint_id": parent_checkpoint_id,
                }
            storage_doc[checkpoint_ns] = ns_doc

        writes_doc: dict[str, list[dict[str, Any]]] = {}
        for outer_key, entries in list(self.writes.items()):
            current_thread_id, checkpoint_ns, checkpoint_id = outer_key
            if current_thread_id != thread_id:
                continue
            composite_key = f"{checkpoint_ns}::{checkpoint_id}"
            writes_doc[composite_key] = [
                {
                    "task_id": task_id,
                    "index": index,
                    "channel": channel,
                    "value": _encode_typed(value),
                    "task_path": task_path,
                }
                for (task_id, index), (task_id, channel, value, task_path) in list(entries.items())
            ]

        blobs_doc: list[dict[str, Any]] = []
        for key, value in list(self.blobs.items()):
            current_thread_id, checkpoint_ns, channel, version = key
            if current_thread_id != thread_id:
                continue
            blobs_doc.append(
                {
                    "checkpoint_ns": checkpoint_ns,
                    "channel": channel,
                    "version": version,
                    "value": _encode_typed(value),
                }
            )

        self._collection.replace_one(
            {"_id": thread_id},
            {
                "_id": thread_id,
                "storage": storage_doc,
                "writes": writes_doc,
                "blobs": blobs_doc,
            },
            upsert=True,
        )

    def get_tuple(self, config):  # type: ignore[override]
        thread_id: str = config["configurable"]["thread_id"]
        self._ensure_thread_loaded(thread_id)
        return super().get_tuple(config)

    def put(self, config, checkpoint, metadata, new_versions):  # type: ignore[override]
        thread_id: str = config["configurable"]["thread_id"]
        self._ensure_thread_loaded(thread_id)
        result = super().put(config, checkpoint, metadata, new_versions)
        self._persist_thread(thread_id)
        return result

    def put_writes(self, config, writes, task_id, task_path=""):  # type: ignore[override]
        thread_id: str = config["configurable"]["thread_id"]
        self._ensure_thread_loaded(thread_id)
        super().put_writes(config, writes, task_id, task_path)
        self._persist_thread(thread_id)

    def delete_thread(self, thread_id: str) -> None:  # type: ignore[override]
        self.storage.pop(thread_id, None)
        keys_to_remove = [key for key in self.writes if key[0] == thread_id]
        for key in keys_to_remove:
            self.writes.pop(key, None)
        blob_keys = [key for key in self.blobs if key[0] == thread_id]
        for key in blob_keys:
            self.blobs.pop(key, None)
        self._loaded_threads.discard(thread_id)
        self._collection.delete_one({"_id": thread_id})


def create_checkpointer(settings: Settings):
    backend = settings.project_storage_backend.lower()
    if backend == "mongo":
        return MongoPersistentCheckpointer(
            uri=settings.mongodb_uri,
            database=settings.mongodb_database,
            collection=f"{settings.mongodb_collection}_checkpoints",
        )
    return InMemorySaver(factory=defaultdict)

