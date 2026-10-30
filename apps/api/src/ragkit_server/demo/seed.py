"""`make demo`: a lived-in project, built through the same services as any real use.

Acme Payments (fictional) runs two retrieval pipelines: the developer docs behind a docs
assistant, and support playbooks behind a support copilot. The seed uploads the corpus
(files to S3, playbooks through the JSON text loader), creates three pipeline versions of
the docs collection, imports three evaluation datasets, runs seven evaluations and replays
two weeks of query traffic. Every chunk, vector, score and metric is computed by the real
pipeline; the only liberty taken is time: runs and queries are spread over the past two
weeks so the dashboards have a shape on a brand-new stack.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import anyio
from sqlalchemy import func, select, update

from ragkit_server.core.config import Settings
from ragkit_server.core.logging import get_logger
from ragkit_server.core.security import hash_password
from ragkit_server.integrations.queue import InlineQueue, Job
from ragkit_server.models import (
    Collection,
    Document,
    EvalResult,
    EvalRun,
    IndexEntry,
    Project,
    QueryLog,
    User,
)
from ragkit_server.models.enums import UNFINISHED, JobStatus, Role, RunStatus
from ragkit_server.repositories.projects import ProjectRepository
from ragkit_server.repositories.users import UserRepository
from ragkit_server.schemas.collections import CollectionCreate
from ragkit_server.schemas.documents import TextSource
from ragkit_server.schemas.evaluation import DatasetCreate, GateSettings, ItemIn, RunCreate
from ragkit_server.schemas.pipeline import PipelineConfig, RetrievalOverrides
from ragkit_server.schemas.retrieval import AnswerRequest, QueryRequest
from ragkit_server.services.api_keys import ApiKeyService
from ragkit_server.services.collections import CollectionService
from ragkit_server.services.container import Container, build_container
from ragkit_server.services.documents import DocumentService, IncomingFile
from ragkit_server.services.evaluation import EvaluationService
from ragkit_server.services.ingestion import IngestionService
from ragkit_server.services.pipelines import PipelineService
from ragkit_server.services.principal import Principal
from ragkit_server.services.projects import ProjectService
from ragkit_server.services.retrieval import RetrievalService

log = get_logger("ragkit.demo")
PROJECT_SLUG = "acme-payments"


@dataclass(frozen=True)
class Person:
    email: str
    name: str
    role: Role
    admin: bool = False


PEOPLE = (
    Person("priya.raman@acme-payments.example", "Priya Raman", Role.OWNER, admin=True),
    Person("daniel.okafor@acme-payments.example", "Daniel Okafor", Role.EDITOR),
    Person("sofia.lindqvist@acme-payments.example", "Sofia Lindqvist", Role.VIEWER),
)

DOC_METADATA: dict[str, dict[str, Any]] = {
    "getting-started.md": {"section": "guides", "audience": "developers", "updated": "2026-09-02"},
    "authentication.md": {"section": "guides", "audience": "developers", "updated": "2026-08-14"},
    "idempotency.md": {"section": "guides", "audience": "developers", "updated": "2026-03-10"},
    "rate-limits.md": {"section": "reference", "audience": "developers", "updated": "2026-07-21"},
    "errors.md": {"section": "reference", "audience": "developers", "updated": "2026-06-02"},
    "webhooks.md": {"section": "guides", "audience": "developers", "updated": "2026-09-15"},
    "payments-api.md": {"section": "reference", "audience": "developers", "updated": "2026-09-15"},
    "refunds-and-disputes.md": {"section": "guides", "audience": "admins", "updated": "2026-05-30"},
    "python-sdk.md": {"section": "reference", "audience": "developers", "updated": "2026-03-10"},
    "testing.md": {"section": "guides", "audience": "developers", "updated": "2026-08-01"},
    "connect-platforms.md": {"section": "guides", "audience": "admins", "updated": "2026-07-05"},
    "payouts.html": {"section": "guides", "audience": "admins", "updated": "2026-06-02"},
    "pricing.csv": {"section": "policies", "audience": "admins", "updated": "2026-01-15"},
    "release-notes-2026.txt": {
        "section": "changelog",
        "audience": "developers",
        "updated": "2026-09-15",
    },
    "Service Level Agreement.pdf": {
        "section": "policies",
        "audience": "admins",
        "updated": "2026-02-01",
    },
    "Security and Compliance Overview.docx": {
        "section": "policies",
        "audience": "admins",
        "updated": "2026-04-20",
    },
}
PLAYBOOK_METADATA = {"team": "support", "audience": "agents"}

CLEAN = {"strip_boilerplate": True, "drop_duplicate_blocks": True}
DOCS_VERSIONS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "Baseline: fixed windows, vector only",
        "The first attempt: 128-token windows without overlap and dense retrieval only.",
        {
            "chunking": {"strategy": "fixed", "chunk_tokens": 128, "overlap_tokens": 0},
            "embedding": {"model": "bge-small-en-v1.5", "contextual": False},
            "retrieval": {"mode": "vector", "top_k": 5, "candidates": 40, "rerank": "none"},
        },
    ),
    (
        "Structure-aware hybrid with reranking",
        "Chunks that follow headings, contextual embeddings, RRF hybrid retrieval and a "
        "cross-encoder over the top 20 candidates.",
        {
            "cleaning": CLEAN,
            "chunking": {"strategy": "recursive", "chunk_tokens": 256, "overlap_tokens": 32},
            "embedding": {"model": "bge-small-en-v1.5", "contextual": True},
            "retrieval": {
                "mode": "hybrid",
                "fusion": "rrf",
                "top_k": 5,
                "candidates": 40,
                "rerank": "cross-encoder",
                "rerank_candidates": 20,
            },
        },
    ),
    (
        "Sentence windows",
        "Two-sentence retrieval units, each carrying two sentences of context on either side.",
        {
            "cleaning": CLEAN,
            "chunking": {
                "strategy": "sentence_window",
                "sentences_per_chunk": 2,
                "window_sentences": 2,
            },
            "embedding": {"model": "bge-small-en-v1.5", "contextual": True},
            "retrieval": {
                "mode": "hybrid",
                "fusion": "rrf",
                "top_k": 5,
                "candidates": 40,
                "rerank": "cross-encoder",
                "rerank_candidates": 20,
            },
        },
    ),
]
PLAYBOOK_CONFIG: dict[str, Any] = {
    "chunking": {"strategy": "recursive", "chunk_tokens": 200, "overlap_tokens": 30},
    "retrieval": {"mode": "hybrid", "rerank": "lexical", "top_k": 4},
}

DATASETS = (
    (
        "support-golden",
        "Support golden set",
        "developer-docs",
        "support-golden.jsonl",
        "Questions developers ask the docs assistant, with the passage that answers each one.",
        {"min": {"hit_rate": 0.85, "context_recall": 0.8}, "max_drop": 0.03},
    ),
    (
        "smoke",
        "Smoke test",
        "developer-docs",
        "smoke.jsonl",
        "Eight questions CI runs on every pull request that touches the docs pipeline.",
        {"min": {"hit_rate": 0.9}, "max_drop": 0.05},
    ),
    (
        "playbook-checks",
        "Playbook checks",
        "support-playbooks",
        "playbooks.jsonl",
        "Policy questions the support copilot must get right.",
        {"min": {"hit_rate": 0.8}},
    ),
)

# (dataset, version, retrieval overrides, label, days ago). The v2 golden run is the baseline.
RUNS: tuple[tuple[str, int, dict[str, Any] | None, str | None, float], ...] = (
    ("support-golden", 1, None, None, 9.2),
    ("support-golden", 2, {"rerank": "none"}, "v2 hybrid without reranking (ablation)", 6.1),
    ("support-golden", 2, {"mode": "keyword", "rerank": "none"}, "v2 keyword only (ablation)", 5.8),
    ("support-golden", 3, None, None, 3.4),
    ("support-golden", 2, None, None, 2.2),
    ("smoke", 2, None, None, 0.9),
    ("playbook-checks", 1, None, None, 0.6),
)
BASELINE_RUN = 4  # index into RUNS

QUERIES = (
    "how do I verify webhook signatures",
    "what is the rate limit in live mode",
    "idempotency key expiry",
    "ACME-4011",
    "refund window",
    "how long do refunds take to show up",
    "instant payout fee",
    "test card for insufficient funds",
    "how to rotate api keys without downtime",
    "webhook retries how long",
    "dispute fee",
    "minimum charge amount usd",
    "manual capture expiry",
    "SLA uptime commitment",
    "service credits for downtime",
    "is acme pci compliant",
    "data retention transaction records",
    "python sdk retries",
    "v1 charges deprecation date",
    "statement descriptor length",
    "how do marketplaces take a fee",
    "payout failed what happens",
    "first payout new account",
    "429 rate_limited retry after",
    "error object fields",
    "3d secure liability shift",
)
PLAYBOOK_QUERIES = (
    "when do I page on-call",
    "severity 2 definition",
    "refund older than 180 days",
    "status page update frequency",
    "kyc documents needed",
    "payouts paused until verified",
)
FILTERED = (
    ({"section": "guides"}, "webhook signing secret"),
    ({"section": "reference"}, "list endpoints page size"),
    ({"audience": "admins"}, "payout schedule weekly"),
    ({"section": "sandbox"}, "test clock"),  # no such section: a zero-hit query
)


@dataclass
class Seeded:
    project: Project | None = None
    collections: dict[str, Collection] = field(default_factory=dict)
    keys: list[tuple[str, str]] = field(default_factory=list)


async def _person(container: Container, person: Person, password: str) -> User:
    async with container.db.session() as session:
        users = UserRepository(session)
        user = await users.by_email(person.email)
        if user is None:
            user = await users.add(
                User(
                    email=person.email,
                    name=person.name,
                    password_hash=await anyio.to_thread.run_sync(hash_password, password),
                    is_admin=person.admin,
                )
            )
            await session.commit()
        return user


async def _wait(container: Container, label: str, timeout_s: int = 1800) -> None:
    """Until no document, index entry or evaluation run is unfinished."""
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        if isinstance(container.queue, InlineQueue):
            await container.queue.drain()
        async with container.db.session() as session:
            documents = await session.scalar(
                select(func.count()).where(Document.status.in_(list(UNFINISHED)))
            )
            entries = await session.scalar(
                select(func.count()).where(IndexEntry.status.in_(list(UNFINISHED)))
            )
            runs = await session.scalar(
                select(func.count()).where(
                    EvalRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING])
                )
            )
        if not (documents or entries or runs):
            return
        status = f"  {label}: {documents} document(s), {entries} index entr(ies), {runs} run(s)"
        if status != last:
            print(status, flush=True)
            last = status
        await asyncio.sleep(2)
    raise TimeoutError(f"{label} did not finish in time; check `make logs SERVICE=worker`")


def _items(path: Path) -> list[ItemIn]:
    return [
        ItemIn.model_validate(json.loads(line))
        for line in path.read_text().splitlines()
        if line.strip()
    ]


async def _seed(container: Container, samples: Path, password: str, seeded: Seeded) -> None:
    people = {p.email: await _person(container, p, password) for p in PEOPLE}
    priya, daniel, sofia = (people[p.email] for p in PEOPLE)
    owner = Principal(user=priya)
    editor = Principal(user=daniel)

    async with container.db.session() as session:
        project = await ProjectService(container, session).create(
            owner,
            "Acme Payments",
            "Retrieval pipelines for the developer docs assistant and the support copilot.",
        )
        repo = ProjectRepository(session)
        await repo.add_member(project.id, daniel.id, Role.EDITOR)
        await repo.add_member(project.id, sofia.id, Role.VIEWER)
        await session.commit()
        seeded.project = project

    # Collections: version 1 of each comes with the collection.
    async with container.db.session() as session:
        service = CollectionService(container, session)
        docs = await service.create(
            project,
            editor,
            CollectionCreate(
                name="Developer docs",
                slug="developer-docs",
                description="Guides, API reference, policies and release notes behind the "
                "public docs assistant.",
                pipeline=PipelineConfig.model_validate(DOCS_VERSIONS[0][2]),
            ),
        )
        playbooks = await service.create(
            project,
            editor,
            CollectionCreate(
                name="Support playbooks",
                slug="support-playbooks",
                description="Internal playbooks the support copilot answers from.",
                pipeline=PipelineConfig.model_validate(PLAYBOOK_CONFIG),
            ),
        )
        seeded.collections = {"developer-docs": docs, "support-playbooks": playbooks}

    # Rename version 1 of the docs collection to say what it is.
    async with container.db.session() as session:
        pipelines = PipelineService(container, session)
        version = await pipelines.version(docs, 1)
        version.name, version.description = DOCS_VERSIONS[0][0], DOCS_VERSIONS[0][1]
        await session.commit()

    corpus = samples / "corpus"
    async with container.db.session() as session:
        documents = DocumentService(container, session)
        for path in sorted((corpus / "developer-docs").iterdir()):
            if path.name not in DOC_METADATA:
                continue
            await documents.upload(
                project,
                docs,
                editor,
                [IncomingFile(path.name, path.read_bytes())],
                DOC_METADATA[path.name],
            )
        items = []
        for path in sorted((corpus / "support-playbooks").glob("*.md")):
            text = path.read_text()
            title = text.splitlines()[0].lstrip("# ").strip()
            items.append(
                TextSource(
                    title=title,
                    text=text,
                    format="markdown",
                    external_id=path.stem,
                    metadata=PLAYBOOK_METADATA,
                )
            )
        await documents.import_sources(project, playbooks, editor, items)
    await _wait(container, "indexing version 1")

    async with container.db.session() as session:
        pipelines = PipelineService(container, session)
        for name, description, config in DOCS_VERSIONS[1:]:
            await pipelines.create(
                project,
                docs,
                editor,
                name=name,
                description=description,
                config=PipelineConfig.model_validate(config),
                activate=name.startswith("Structure-aware"),
            )
    await _wait(container, "indexing versions 2 and 3")

    datasets_dir = samples / "datasets"
    async with container.db.session() as session:
        evaluation = EvaluationService(container, session)
        for slug, name, collection, filename, description, gate in DATASETS:
            await evaluation.create_dataset(
                project,
                editor,
                DatasetCreate(
                    name=name,
                    slug=slug,
                    collection=collection,
                    description=description,
                    gate=GateSettings.model_validate(gate),
                    items=_items(datasets_dir / filename),
                ),
            )

    run_ids: list[uuid.UUID] = []
    for dataset, number, overrides, label, _ in RUNS:
        async with container.db.session() as session:
            created = await EvaluationService(container, session).create_run(
                project,
                editor,
                RunCreate(
                    dataset=dataset,
                    pipeline_version=number,
                    label=label,
                    retrieval=RetrievalOverrides.model_validate(overrides) if overrides else None,
                ),
            )
            run_ids.append(created.id)
    await _wait(container, "evaluation runs")

    async with container.db.session() as session:
        evaluation = EvaluationService(container, session)
        await evaluation.set_baseline(
            project, await evaluation.run(project, run_ids[BASELINE_RUN]), owner
        )
        now = datetime.now(UTC)
        for run_id, (_, _, _, _, days_ago) in zip(run_ids, RUNS, strict=True):
            finished = await session.get(EvalRun, run_id)
            if finished is None or finished.started_at is None or finished.finished_at is None:
                continue
            took = finished.finished_at - finished.started_at
            started = now - timedelta(days=days_ago)
            await session.execute(
                update(EvalRun)
                .where(EvalRun.id == run_id)
                .values(
                    created_at=started - timedelta(seconds=4),
                    started_at=started,
                    finished_at=started + took,
                )
            )
            await session.execute(
                update(EvalResult).where(EvalResult.run_id == run_id).values(created_at=started)
            )
        await session.commit()

    async with container.db.session() as session:
        _, key = await ApiKeyService(container, session).create(
            project, owner, "Docs assistant (production)", "viewer", None
        )
        seeded.keys.append(("Docs assistant (production), viewer", key))
        _, ci_key = await ApiKeyService(container, session).create(
            project, owner, "CI evaluation gate", "editor", 90
        )
        seeded.keys.append(("CI evaluation gate, editor", ci_key))


async def _replay_traffic(
    container: Container, project: Project, collections: dict[str, Collection]
) -> None:
    """Two weeks of queries, served by the real retrieval path, then spread over time."""
    rng = random.Random(2026)
    plans: list[tuple[int, str, QueryRequest | AnswerRequest]] = []
    for day in range(14):
        volume = rng.randint(9, 16) + (4 if day in (2, 3, 9) else 0)
        for _ in range(volume):
            text = rng.choice(QUERIES)
            if rng.random() < 0.25:
                plans.append((day, "developer-docs", AnswerRequest(query=text)))
            else:
                plans.append((day, "developer-docs", QueryRequest(query=text)))
        plans.extend(
            (day, "support-playbooks", QueryRequest(query=rng.choice(PLAYBOOK_QUERIES)))
            for _ in range(rng.randint(2, 5))
        )
        if day % 3 == 0:
            filters, text = FILTERED[(day // 3) % len(FILTERED)]
            plans.append((day, "developer-docs", QueryRequest(query=text, filters=filters)))
    # The traffic comes from the production docs assistant's API key, as it would live.
    async with container.db.session() as session:
        keys = await ApiKeyService(container, session).for_project(project.id)
        production = next((k for k in keys if k.name.startswith("Docs assistant")), None)
    principal = Principal(api_key=production) if production else Principal()
    print(f"  replaying {len(plans)} queries", flush=True)
    async with container.db.session() as session:
        retrieval = RetrievalService(container, session)
        for _, slug, request in plans:
            collection = await session.get(Collection, collections[slug].id)
            if collection is None:
                continue
            if isinstance(request, AnswerRequest):
                await retrieval.answer(project, collection, request, principal)
            else:
                await retrieval.query(project, collection, request, principal)
    now = datetime.now(UTC)
    async with container.db.session() as session:
        rows = list(
            (
                await session.execute(
                    select(QueryLog.id)
                    .where(QueryLog.project_id == project.id)
                    .order_by(QueryLog.created_at)
                )
            ).scalars()
        )
        for log_id, (day, _, _) in zip(rows, plans, strict=False):
            when = now - timedelta(
                days=13 - day, hours=rng.uniform(0, 10), minutes=rng.uniform(0, 59)
            )
            await session.execute(
                update(QueryLog).where(QueryLog.id == log_id).values(created_at=when)
            )
        await session.commit()


async def run(settings: Settings, samples: Path, password: str, *, traffic: bool = True) -> None:
    container = build_container(settings)
    if isinstance(container.queue, InlineQueue):
        container.queue.bind(IngestionService(container).handle)
    try:
        async with container.db.session() as session:
            existing = await ProjectRepository(session).by_slug(PROJECT_SLUG)
        if existing is not None:
            print("The demo project already exists; nothing to seed.")
            _print_logins(settings, password, [])
            return
        await container.warm_up()
        seeded = Seeded()
        await _seed(container, samples, password, seeded)
        if traffic and seeded.project is not None:
            await _replay_traffic(container, seeded.project, seeded.collections)
        _print_logins(settings, password, seeded.keys)
    finally:
        await container.close()


def _print_logins(settings: Settings, password: str, keys: list[tuple[str, str]]) -> None:
    print("\nDemo ready. Sign in at", settings.web_url)
    for person in PEOPLE:
        print(f"  {person.email:<40} {person.role.value:<7} password: {password}")
    for label, key in keys:
        print(f"\n  API key ({label}): {key}")
    if keys:
        endpoint = f"{settings.api_url}/api/v1/projects/{PROJECT_SLUG}/collections/developer-docs"
        print("\n  Try it:")
        print(f"  curl -s {endpoint}/query \\")
        print(f"    -H 'authorization: Bearer {keys[0][1]}' -H 'content-type: application/json' \\")
        print('    -d \'{"query": "How do I verify webhook signatures?"}\'')


async def reindex(settings: Settings, collection_slug: str | None) -> int:
    """Parse every document again; each parse re-queues the document in every index."""
    container = build_container(settings)
    if isinstance(container.queue, InlineQueue):
        container.queue.bind(IngestionService(container).handle)
    try:
        async with container.db.session() as session:
            query = select(Document.id, Document.project_id)
            if collection_slug:
                query = query.join(Collection, Collection.id == Document.collection_id).where(
                    Collection.slug == collection_slug
                )
            rows = (await session.execute(query)).all()
            if rows:
                await session.execute(
                    update(Document)
                    .where(Document.id.in_([row.id for row in rows]))
                    .values(status=JobStatus.QUEUED, attempts=0, error=None)
                )
                await session.commit()
        for row in rows:
            await container.queue.enqueue(Job.parse(row.project_id, row.id))
        if isinstance(container.queue, InlineQueue):
            await container.queue.drain()
        return len(rows)
    finally:
        await container.close()
