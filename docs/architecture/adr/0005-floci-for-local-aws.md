# ADR 0005: Develop against an AWS emulator (Floci), provisioned by the production Terraform

## Status

Accepted.

## Context

In production RAGKit depends on S3 (originals and URL snapshots with SSE-KMS), SQS with a
dead-letter queue (parse, index and evaluation jobs), KMS and Secrets Manager. Local
development that swaps each of these for a different mechanism (a directory, an in-process
queue, plain secrets) leaves the code paths that matter most in production untested until
they reach a real AWS account: SSE-KMS writes, SQS long polling, visibility extension and
redrive, and the Terraform itself.

## Decision

- `make up` runs the Floci AWS emulator (`floci/floci`, MIT licence) alongside Postgres with
  pgvector, Valkey and the application images.
- A one-shot Terraform container applies `infra/terraform/envs/local-floci` against the
  emulator before the API and the worker start. That environment uses the **same** `kms`,
  `storage`, `queue` and `secrets` modules as production, with only the endpoint and a few
  emulator switches changed (no TLS-only bucket policy, versioning off, force-destroy on).
- The API and the worker run locally with `STORAGE_BACKEND=s3` and `QUEUE_BACKEND=sqs`,
  pointed at the emulator with `AWS_ENDPOINT_URL`, so every job goes through a real queue
  with a dead-letter queue.
- Terraform state for the local environment lives in a Docker volume and is wiped with the
  emulator by `make down`.
- The integration suite provisions its own KMS key, bucket, queue and dead-letter queue on
  the emulator and runs the real worker against them.
- `STORAGE_BACKEND=local` and `QUEUE_BACKEND=inline` remain for running the API alone.

## Consequences

Positive:

- Developers and CI exercise the real SDK calls, SSE-KMS uploads, SQS long polling,
  visibility changes, the hand-back on shutdown and redrive, without an AWS account.
- The Terraform modules are applied on every `make up`, not only on deploy.

Trade-offs:

- An emulator is not AWS: IAM policy evaluation, quotas and some timing are not reproduced;
  [deploy-aws.md](../../guides/deploy-aws.md) and `make up-aws` cover the gap.
- One more container and image version to keep current.

## Alternatives considered

- **Per-service local substitutes** (a directory, an in-process queue, MinIO). Simple, but
  the production code paths for SQS and KMS would go untested locally.
- **LocalStack.** A comparable emulator offering the same approach; Floci is the one this
  project is built and tested against, as are the other Euron open-source projects.
- **A shared development AWS account.** Highest fidelity, but needs credentials for every
  contributor, costs money, and shared state makes tests interfere with each other.
