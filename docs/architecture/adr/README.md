# Architecture Decision Records

Each record captures one significant decision: the context that forced it, what was decided,
what it costs, and what else was considered. Records are immutable once accepted; a change of
mind is a new record that supersedes the old one.

| ADR | Title | Status |
| --- | ----- | ------ |
| [0001](0001-postgres-and-pgvector-as-the-index.md) | Postgres with pgvector is the only index store | Accepted |
| [0002](0002-immutable-pipeline-versions-and-shared-indexes.md) | Immutable pipeline versions that share indexes by fingerprint | Accepted |
| [0003](0003-evidence-based-relevance.md) | Judge relevance by expected document and evidence, not chunk ids | Accepted |
| [0004](0004-deterministic-providers-first.md) | Deterministic local providers first, model adapters behind the same interfaces | Accepted |
| [0005](0005-floci-for-local-aws.md) | Develop against an AWS emulator (Floci), provisioned by the production Terraform | Accepted |
| [0006](0006-one-queue-for-parse-index-and-eval-jobs.md) | One SQS queue with a dead-letter queue for parse, index and evaluation jobs | Accepted |

## Template

```markdown
# ADR NNNN: <decision in one line>

## Status
Proposed | Accepted | Superseded by NNNN

## Context
What forces are at play, and why a decision is needed now.

## Decision
What we will do.

## Consequences
What becomes easier, what becomes harder, what we accept.

## Alternatives considered
What else was evaluated, and why it lost.
```
