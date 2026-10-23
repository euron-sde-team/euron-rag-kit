"""Collections: create (with pipeline version 1), list with counts, update and delete."""

from __future__ import annotations

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from ragkit_server.core.errors import ConflictError, NotFoundError
from ragkit_server.core.logging import get_logger
from ragkit_server.ingestion.sniff import slugify
from ragkit_server.models import Collection, Project
from ragkit_server.repositories.collections import CollectionRepository, CollectionStats
from ragkit_server.repositories.documents import DocumentRepository
from ragkit_server.schemas.collections import CollectionCreate, CollectionOut, CollectionUpdate
from ragkit_server.schemas.pipeline import PipelineConfig
from ragkit_server.services import audit
from ragkit_server.services.container import Container
from ragkit_server.services.pipelines import PipelineService
from ragkit_server.services.principal import Principal

log = get_logger("ragkit.collections")


def collection_out(stats: CollectionStats) -> CollectionOut:
    c = stats.collection
    return CollectionOut(
        id=c.id,
        slug=c.slug,
        name=c.name,
        description=c.description,
        active_version=stats.active_version,
        version_count=stats.version_count,
        document_count=stats.document_count,
        ready_documents=stats.ready_documents,
        chunk_count=stats.chunk_count,
        corpus_version=c.corpus_version,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


class CollectionService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.collections = CollectionRepository(session)

    async def get(self, project: Project, ref: str) -> Collection:
        collection = await self.collections.get(project.id, ref)
        if collection is None:
            raise NotFoundError("Collection not found.")
        return collection

    async def list(self, project: Project) -> list[CollectionOut]:
        return [collection_out(s) for s in await self.collections.with_stats(project.id)]

    async def describe(self, project: Project, collection: Collection) -> CollectionOut:
        stats = await self.collections.with_stats(project.id, [collection.id])
        return collection_out(stats[0])

    async def create(
        self, project: Project, principal: Principal, body: CollectionCreate
    ) -> Collection:
        config = body.pipeline or PipelineConfig()
        pipelines = PipelineService(self.c, self.session)
        pipelines.resolve_spec(config)  # refuse an unusable model before creating anything
        if body.slug:
            if await self.collections.slug_taken(project.id, body.slug):
                raise ConflictError("A collection with that slug already exists.")
            slug = body.slug
        else:
            base = slugify(body.name, limit=48, fallback="collection")
            slug = base
            while await self.collections.slug_taken(project.id, slug):
                slug = f"{base}-{secrets.token_hex(2)}"
        collection = await self.collections.add(
            Collection(
                project_id=project.id,
                slug=slug,
                name=body.name.strip(),
                description=body.description.strip(),
                created_by=principal.user_id,
            )
        )
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="collection.created",
            target_type="collection",
            target_id=collection.id,
            details={"slug": slug},
        )
        await self.session.flush()
        await pipelines.create(
            project,
            collection,
            principal,
            name="Initial pipeline",
            description="Created with the collection.",
            config=config,
            activate=True,
        )
        return collection

    async def update(
        self, project: Project, collection: Collection, principal: Principal, body: CollectionUpdate
    ) -> Collection:
        changes = body.model_dump(exclude_none=True)
        for field, value in changes.items():
            setattr(collection, field, value.strip())
        if changes:
            await audit.record(
                self.session,
                project_id=project.id,
                principal=principal,
                action="collection.updated",
                target_type="collection",
                target_id=collection.id,
                details={"fields": sorted(changes)},
            )
            await self.session.commit()
        return collection

    async def delete(self, project: Project, collection: Collection, principal: Principal) -> None:
        keys = await DocumentRepository(self.session).storage_keys(collection.id)
        await self.session.delete(collection)
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="collection.deleted",
            target_type="collection",
            target_id=collection.id,
            details={"slug": collection.slug},
        )
        await self.session.commit()
        for key in keys:
            try:
                await self.c.storage.delete(key)
            except Exception:
                log.warning("storage_delete_failed", key=key)
