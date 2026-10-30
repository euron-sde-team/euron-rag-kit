# ADR 0003: Judge relevance by expected document and evidence, not chunk ids

## Status

Accepted.

## Context

Retrieval metrics need to know which retrieved passages are relevant to a question. The
common shortcut, labelling relevant chunk ids, breaks exactly where RAGKit is used: every
change of chunking strategy, chunk size or cleaning produces different chunks, so labels made
against one version are meaningless for the next, and versions cannot be compared on one
dataset.

## Decision

- A dataset item names its **expected sources** by the document's stable `external_id`, each
  with an optional **evidence** quote: the words that actually answer the question.
- A retrieved chunk **covers** an expected source when it belongs to that document and, if
  evidence is given, its context contains the evidence: after normalising case, whitespace
  and punctuation, the evidence is a substring, or at least 80% of its stemmed content words
  occur in the chunk.
- A chunk is relevant when it covers at least one expected source. Metrics are defined on
  coverage: hit rate, context recall (expected sources covered), context precision (average
  precision over relevant positions), MRR and nDCG with gain only for newly covered sources,
  so two chunks of the same passage do not count twice.
- Sentence-window chunks are judged on their window (`context`), the same text an answerer
  sees.

## Consequences

Positive:

- One dataset measures every pipeline version, whatever its chunking.
- Labelling is natural for people: "this question is answered by the refunds page, by this
  sentence".
- The judgment is deterministic, explainable and shown per question in the run view.

Trade-offs:

- Evidence quotes must be kept in sync with documents; a run shows uncovered sources so a
  stale quote is easy to spot.
- The 80% term overlap allows paraphrase within a chunk but not across distant chunks; very
  long evidence quotes should be split into separate expected sources.

## Alternatives considered

- **Chunk id labels.** Precise for one version, useless across versions.
- **Document-level relevance only.** Robust, but rewards retrieving any chunk of a long
  document, including the wrong section.
- **A model judging relevance.** Useful as an option, but non-deterministic and costly as a
  default for CI.
