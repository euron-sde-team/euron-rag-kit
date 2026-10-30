# ADR 0002: Immutable pipeline versions that share indexes by fingerprint

## Status

Accepted.

## Context

The point of RAGKit is to compare retrieval configurations with evidence. That only works
if a measured configuration cannot change after it was measured: an evaluation run must
always describe the exact settings that produced its numbers, and production must serve
exactly what was evaluated.

At the same time, most experiments change retrieval knobs (mode, fusion, `top_k`, the
reranker) or the answerer, not chunking or embedding. Rebuilding a whole index for those
would make experiments slow and expensive for no reason.

## Decision

- A pipeline version is an **immutable, numbered configuration** of cleaning, chunking,
  embedding, retrieval defaults and the answerer. Any change is version N+1. Activating a
  version is a separate, audited step.
- Split the configuration into **index settings** (cleaning, chunking, embedding) and
  **serving settings** (retrieval, answer).
- An index is identified by a **fingerprint**: `sha256` of the canonical JSON of the index
  settings (only the chunking fields the chosen strategy uses, the resolved embedding
  provider, model and width, contextual embedding) plus an `INDEXER_VERSION` constant.
- Creating a version reuses the collection's index with the same fingerprint, so it is
  queryable at once; otherwise a new index is built in the background per document.
- `INDEXER_VERSION` is bumped whenever cleaning or chunking code changes its output, so an
  upgrade never mixes chunks from two algorithms in one index.
- Queries and evaluation runs may override serving settings per request; index settings can
  never be overridden.

## Consequences

Positive:

- Every evaluation run and every query log row points at a configuration that still means
  what it meant.
- Retrieval experiments are free: a new version that only changes the reranker is ready
  immediately, and the dashboard says so before it is created.
- The index fingerprint makes index identity explicit and testable.

Trade-offs:

- Old versions accumulate. They are cheap (a row each); indexes no version uses can be
  removed by deleting the versions that use them.
- Unused knobs must stay out of the fingerprint (for example `overlap_tokens` for sentence
  windows), or harmless differences would split indexes; the canonical form handles this.

## Alternatives considered

- **Mutable configurations with history.** Simpler to edit, but a run's numbers could no
  longer be trusted to describe the current configuration.
- **One index per version.** Clear, but makes every retrieval-only experiment rebuild and
  re-embed the whole corpus.
