#!/usr/bin/env bash
# Make sure the services the integration tests need are reachable: Postgres (pgvector),
# Valkey and Floci, from the compose stack (started on their own if the stack is down).
# The suite creates its own `ragkit_test` database, uses Valkey database 15 and makes
# uniquely named buckets and queues, so the development data is never touched.
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file deploy/compose/.env -f deploy/compose/compose.yaml
  -f deploy/compose/compose.floci.yaml)
[[ -f deploy/compose/.env ]] || scripts/gen-local-env.sh >/dev/null
"${compose[@]}" up -d --wait postgres valkey floci >/dev/null
