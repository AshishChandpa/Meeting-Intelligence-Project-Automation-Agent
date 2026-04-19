from __future__ import annotations

from agent.config import Settings
from agent.storage.base import ProjectRepository
from agent.storage.memory import InMemoryProjectRepository
from agent.storage.mongo import MongoProjectRepository


def create_project_repository(settings: Settings) -> ProjectRepository:
    backend = settings.project_storage_backend.lower()
    if backend == "mongo":
        return MongoProjectRepository(
            uri=settings.mongodb_uri,
            database=settings.mongodb_database,
            collection=settings.mongodb_collection,
        )
    return InMemoryProjectRepository()

