"""Initial schema: accounts, projects, collections, documents, indexes, chunks, evaluation.

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from ragkit_server.db.types import Embedding

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)
# Frozen here rather than imported: a later width is a new migration with its own index.
HNSW_DIMS = (384, 768, 1024, 1536)
JOB_STATUSES = "status IN ('queued', 'processing', 'ready', 'failed')"


def _id() -> sa.Column[object]:
    return sa.Column("id", UUID, nullable=False)


def _created() -> sa.Column[object]:
    return sa.Column("created_at", TS, nullable=False, server_default=sa.func.now())


def _updated() -> sa.Column[object]:
    return sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now())


def _fk(column: str, table: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], [f"{table}.id"], ondelete=ondelete)


def _jsonb(name: str, default: str) -> sa.Column[object]:
    return sa.Column(
        name, pg.JSONB(), nullable=False, server_default=sa.text(f"'{default}'::jsonb")
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        _id(),
        sa.Column("email", pg.CITEXT(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", TS),
        sa.Column("last_login_at", TS),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "projects",
        _id(),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", UUID),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        _fk("created_by", "users", "SET NULL"),
    )

    op.create_table(
        "memberships",
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
        _fk("project_id", "projects", "CASCADE"),
        _fk("user_id", "users", "CASCADE"),
        sa.CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="role"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "api_keys",
        _id(),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("created_by", UUID),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("last_used_at", TS),
        sa.Column("expires_at", TS),
        sa.Column("revoked_at", TS),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prefix"),
        _fk("project_id", "projects", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
        sa.CheckConstraint("role IN ('editor', 'viewer')", name="role"),
    )
    op.create_index("ix_api_keys_project_id", "api_keys", ["project_id"])

    op.create_table(
        "audit_events",
        _id(),
        sa.Column("project_id", UUID),
        sa.Column("actor_user_id", UUID),
        sa.Column("actor_api_key_id", UUID),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64)),
        _jsonb("details", "{}"),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("project_id", "projects", "CASCADE"),
        _fk("actor_user_id", "users", "SET NULL"),
        _fk("actor_api_key_id", "api_keys", "SET NULL"),
    )
    op.create_index(
        "ix_audit_events_project_id_created_at", "audit_events", ["project_id", "created_at"]
    )

    # The active version's foreign key is added once pipeline_versions exists (a cycle).
    op.create_table(
        "collections",
        _id(),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("active_version_id", UUID),
        sa.Column("corpus_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", UUID),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "slug"),
        _fk("project_id", "projects", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
    )

    op.create_table(
        "documents",
        _id(),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("collection_id", UUID, nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_type", sa.String(8), nullable=False),
        sa.Column("source_uri", sa.String(2048)),
        sa.Column("kind", sa.String(8)),
        sa.Column("mime_type", sa.String(160)),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(64)),
        sa.Column("storage_key", sa.String(400)),
        _jsonb("metadata", "{}"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("section_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", UUID),
        sa.Column("parsed_at", TS),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "external_id"),
        _fk("project_id", "projects", "CASCADE"),
        _fk("collection_id", "collections", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
        sa.CheckConstraint(JOB_STATUSES, name="status"),
        sa.CheckConstraint("source_type IN ('file', 'url', 'text')", name="source_type"),
        sa.CheckConstraint(
            "kind IS NULL OR kind IN ('pdf', 'docx', 'md', 'html', 'txt', 'csv')", name="kind"
        ),
    )
    op.create_index(
        "ix_documents_collection_id_created_at", "documents", ["collection_id", "created_at"]
    )
    # The same bytes uploaded twice to one collection are one document; the same URL too.
    op.create_index(
        "uq_documents_collection_id_sha256",
        "documents",
        ["collection_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("source_type IN ('file', 'text')"),
    )
    op.create_index(
        "uq_documents_collection_id_source_uri",
        "documents",
        ["collection_id", "source_uri"],
        unique=True,
        postgresql_where=sa.text("source_type = 'url'"),
    )
    # Small partial index for the reaper: only unfinished documents are in it.
    op.create_index(
        "ix_documents_unfinished",
        "documents",
        ["updated_at"],
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )

    op.create_table(
        "document_sections",
        _id(),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        _jsonb("blocks", "[]"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal"),
        _fk("document_id", "documents", "CASCADE"),
        sa.CheckConstraint("kind IN ('page', 'section', 'table')", name="kind"),
    )

    op.create_table(
        "indexes",
        _id(),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("collection_id", UUID, nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        _jsonb("config", "{}"),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "fingerprint"),
        _fk("project_id", "projects", "CASCADE"),
        _fk("collection_id", "collections", "CASCADE"),
    )

    op.create_table(
        "index_entries",
        sa.Column("index_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        _updated(),
        sa.PrimaryKeyConstraint("index_id", "document_id"),
        _fk("index_id", "indexes", "CASCADE"),
        _fk("document_id", "documents", "CASCADE"),
        _fk("project_id", "projects", "CASCADE"),
        sa.CheckConstraint(JOB_STATUSES, name="status"),
    )
    op.create_index("ix_index_entries_document_id", "index_entries", ["document_id"])
    op.create_index(
        "ix_index_entries_unfinished",
        "index_entries",
        ["updated_at"],
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )

    op.create_table(
        "pipeline_versions",
        _id(),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("collection_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        _jsonb("config", "{}"),
        sa.Column("index_id", UUID, nullable=False),
        sa.Column("created_by", UUID),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "version"),
        _fk("project_id", "projects", "CASCADE"),
        _fk("collection_id", "collections", "CASCADE"),
        _fk("index_id", "indexes", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
        sa.CheckConstraint("version >= 1", name="version"),
    )
    op.create_index("ix_pipeline_versions_index_id", "pipeline_versions", ["index_id"])
    op.create_foreign_key(
        "fk_collections_active_version_id_pipeline_versions",
        "collections",
        "pipeline_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "chunks",
        _id(),
        sa.Column("index_id", UUID, nullable=False),
        sa.Column("collection_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("section_ordinal", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=False, server_default=""),
        sa.Column("location", sa.String(300), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("context", sa.Text()),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        _jsonb("metadata", "{}"),
        sa.Column("embedding", Embedding(), nullable=False),
        sa.Column("embedding_dim", sa.SmallInteger(), nullable=False),
        sa.Column(
            "tsv",
            pg.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(heading, '') || ' ' || text)", persisted=True
            ),
        ),
        sa.PrimaryKeyConstraint("id"),
        _fk("index_id", "indexes", "CASCADE"),
        _fk("collection_id", "collections", "CASCADE"),
        _fk("document_id", "documents", "CASCADE"),
        sa.CheckConstraint(
            f"embedding_dim IN ({', '.join(str(d) for d in HNSW_DIMS)})", name="embedding_dim"
        ),
        sa.CheckConstraint("vector_dims(embedding) = embedding_dim", name="embedding_width"),
    )
    op.create_index(
        "ix_chunks_index_id_document_id_ordinal", "chunks", ["index_id", "document_id", "ordinal"]
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_collection_id", "chunks", ["collection_id"])
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")
    op.execute("CREATE INDEX ix_chunks_metadata ON chunks USING gin (metadata jsonb_path_ops)")
    # One HNSW index per supported width, each over a cast expression and limited to rows of
    # that width. Queries repeat the same cast and width predicate as SQL literals, so the
    # planner can match the partial index on every execution.
    for dim in HNSW_DIMS:
        op.execute(
            f"CREATE INDEX ix_chunks_embedding_hnsw_{dim} ON chunks USING hnsw "
            f"((embedding::vector({dim})) vector_cosine_ops) WITH (m = 16, ef_construction = 64) "
            f"WHERE embedding_dim = {dim}"
        )

    op.create_table(
        "query_logs",
        _id(),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("collection_id", UUID, nullable=False),
        sa.Column("pipeline_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("rerank", sa.String(16), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("top_score", sa.Float()),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("answerer", sa.String(32)),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("query_text", sa.Text()),
        sa.Column("user_id", UUID),
        sa.Column("api_key_id", UUID),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("project_id", "projects", "CASCADE"),
        _fk("collection_id", "collections", "CASCADE"),
        _fk("user_id", "users", "SET NULL"),
        _fk("api_key_id", "api_keys", "SET NULL"),
        sa.CheckConstraint("kind IN ('query', 'answer')", name="kind"),
    )
    op.create_index(
        "ix_query_logs_project_id_created_at", "query_logs", ["project_id", "created_at"]
    )
    op.create_index(
        "ix_query_logs_collection_id_created_at", "query_logs", ["collection_id", "created_at"]
    )

    op.create_table(
        "datasets",
        _id(),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("collection_id", UUID, nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        _jsonb("gate", "{}"),
        sa.Column("baseline_run_id", UUID),
        sa.Column("created_by", UUID),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "slug"),
        _fk("project_id", "projects", "CASCADE"),
        _fk("collection_id", "collections", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
    )

    op.create_table(
        "dataset_items",
        _id(),
        sa.Column("dataset_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        _jsonb("expected_sources", "[]"),
        sa.Column("expected_answer", sa.Text()),
        sa.Column(
            "tags",
            pg.ARRAY(sa.String(40)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("dataset_id", "datasets", "CASCADE"),
    )
    op.create_index(
        "ix_dataset_items_dataset_id_ordinal", "dataset_items", ["dataset_id", "ordinal"]
    )

    op.create_table(
        "eval_runs",
        _id(),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("dataset_id", UUID, nullable=False),
        sa.Column("collection_id", UUID, nullable=False),
        sa.Column("pipeline_version_id", UUID, nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        _jsonb("config", "{}"),
        sa.Column("k", sa.Integer(), nullable=False),
        sa.Column("grader", sa.String(16), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_items", sa.Integer(), nullable=False, server_default="0"),
        _jsonb("metrics", "{}"),
        sa.Column("error", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", UUID),
        _created(),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        _fk("project_id", "projects", "CASCADE"),
        _fk("dataset_id", "datasets", "CASCADE"),
        _fk("collection_id", "collections", "CASCADE"),
        _fk("pipeline_version_id", "pipeline_versions", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="status"),
        sa.CheckConstraint("grader IN ('deterministic', 'model')", name="grader"),
        sa.CheckConstraint("k BETWEEN 1 AND 50", name="k"),
    )
    op.create_index("ix_eval_runs_project_id_created_at", "eval_runs", ["project_id", "created_at"])
    op.create_index("ix_eval_runs_dataset_id_created_at", "eval_runs", ["dataset_id", "created_at"])
    op.create_index("ix_eval_runs_pipeline_version_id", "eval_runs", ["pipeline_version_id"])
    op.create_index(
        "ix_eval_runs_unfinished",
        "eval_runs",
        ["updated_at"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_foreign_key(
        "fk_datasets_baseline_run_id_eval_runs",
        "datasets",
        "eval_runs",
        ["baseline_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "eval_results",
        _id(),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("item_id", UUID),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            pg.ARRAY(sa.String(40)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        _jsonb("retrieved", "[]"),
        sa.Column("answer", sa.Text()),
        _jsonb("citations", "[]"),
        _jsonb("metrics", "{}"),
        _jsonb("grading", "{}"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retrieval_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "item_id"),
        _fk("run_id", "eval_runs", "CASCADE"),
        _fk("item_id", "dataset_items", "SET NULL"),
    )
    op.create_index("ix_eval_results_run_id_ordinal", "eval_results", ["run_id", "ordinal"])
    op.create_index("ix_eval_results_item_id", "eval_results", ["item_id"])


def downgrade() -> None:
    op.drop_constraint("fk_datasets_baseline_run_id_eval_runs", "datasets", type_="foreignkey")
    op.drop_constraint(
        "fk_collections_active_version_id_pipeline_versions", "collections", type_="foreignkey"
    )
    for table in (
        "eval_results",
        "eval_runs",
        "dataset_items",
        "datasets",
        "query_logs",
        "chunks",
        "pipeline_versions",
        "index_entries",
        "indexes",
        "document_sections",
        "documents",
        "collections",
        "audit_events",
        "api_keys",
        "memberships",
        "projects",
        "users",
    ):
        op.drop_table(table)
