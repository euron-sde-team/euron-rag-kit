# ADR 0001: Postgres with pgvector is the only index store

## Status

Accepted.

## Context

RAGKit needs, for every chunk of every pipeline version's index: a dense vector, a
full-text representation, JSON metadata for filters, and the relational context around it
(document, collection, project, index entry status). Hybrid retrieval queries both the vector
and the keyword representation and fuses them; metadata filters apply to both. Index builds
replace a document's chunks atomically while queries keep running.

Running a separate vector database next to Postgres would split that state across two
systems: two consistency models, two backup stories, filters translated twice, and a window
during every rebuild in which the two disagree.

## Decision

- Store chunks in one Postgres table with an untyped `vector` column, an `embedding_dim`
  column and a stored `tsvector`.
- Create one **partial HNSW index per supported width** (384, 768, 1024, 1536) over a cast
  expression, limited to rows of that width. Queries repeat the cast and the width
  predicate as SQL literals so the planner matches the partial index.
- Use pgvector 0.8 **iterative index scans** (`hnsw.iterative_scan = relaxed_order`) so
  filtered vector queries (by index, by metadata) still return enough candidates.
- Keyword search uses Postgres full-text search with a GIN index; metadata filters compile to
  `@>` containment served by a GIN `jsonb_path_ops` index.
- A document's chunks in one index are replaced in a single transaction together with its
  index entry status.

## Consequences

Positive:

- One transactional store: an index entry is `ready` exactly when its chunks are visible.
- One backup, one set of credentials, one network path, managed on AWS by RDS.
- Filters, joins and project scoping are plain SQL, shared by vector and keyword search.
- Collections with different embedding widths live side by side.

Trade-offs:

- Postgres full-text ranking is simpler than a dedicated BM25 engine; the lexical reranker
  and fusion compensate, and the evaluation suite measures the result.
- Very large corpora (hundreds of millions of chunks) would need partitioning by collection
  or a dedicated engine; RAGKit targets team-scale corpora.
- A new embedding width needs a migration that adds its HNSW index.

## Alternatives considered

- **A dedicated vector database** (Qdrant, Weaviate, Milvus). Strong ANN performance, but a
  second stateful system to deploy, secure and keep consistent with Postgres.
- **One typed `vector(n)` column per width.** Wasted columns and a schema change per model
  family; partial indexes on one untyped column give the same plans.
- **Exact search without an index.** Fine for a demo, linear in corpus size.
