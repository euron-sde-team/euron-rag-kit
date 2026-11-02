## What and why

<!-- One paragraph: the problem, and how this change solves it. Link the issue. -->

## How it was verified

- [ ] `make lint typecheck test`
- [ ] `make test-integration` (if API, database, queue, worker, retrieval or evaluation code changed)
- [ ] `make e2e` (if a user flow, the web app or the infrastructure changed)
- [ ] `make tf-validate tf-lint tf-security` (if Terraform changed)

## Checklist

- [ ] Docs updated (`docs/`, the configuration reference) for any behavior or config change
- [ ] `make openapi` re-run if a route changed
- [ ] New migration instead of editing an applied one
- [ ] Project data stays in its project: every repository query filters by project, covered by a test
- [ ] A changed chunker, cleaning rule or embedding step bumps the indexer version, so existing indexes rebuild
- [ ] A new or changed metric keeps its formula in the LLD and has unit tests with worked examples
- [ ] No secrets, account ids, real emails or hostnames (`make sanitize` is clean)
- [ ] Security-relevant change? Described the threat and mitigation above
