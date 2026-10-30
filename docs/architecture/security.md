# Security

How RAGKit protects accounts, project data, ingested content and the infrastructure it runs
on. The attacker's view, with each threat traced to these controls, is in the
[threat model](threat-model.md). To report a vulnerability, follow
[SECURITY.md](../../SECURITY.md).

- [Principles](#principles)
- [Identity and sessions](#identity-and-sessions)
- [API keys](#api-keys)
- [Authorisation and project isolation](#authorisation-and-project-isolation)
- [Ingestion: uploads and URLs](#ingestion-uploads-and-urls)
- [Model answers and prompt injection](#model-answers-and-prompt-injection)
- [Web application](#web-application)
- [Data protection](#data-protection)
- [Infrastructure](#infrastructure)
- [Secrets](#secrets)
- [Logging and audit](#logging-and-audit)
- [Abuse limits](#abuse-limits)
- [Production guard rails](#production-guard-rails)

## Principles

- **Isolation by construction.** Every project-scoped route resolves the caller's role
  before the handler runs, and every repository query filters by `project_id`. A route
  cannot forget a check it never performs itself.
- **Deny by default.** Non-members get 404 (the project's existence is not revealed),
  unknown fields are rejected (`extra="forbid"` on every request model), unsafe methods with
  a cookie must come from an allowed origin.
- **Least privilege everywhere.** Roles in the product, one task role per service on AWS,
  KMS usage scoped by `kms:ViaService`, IAM actions scoped to the `projects/` prefix of one
  bucket and one queue.
- **Nothing secret in the database, the logs or a Terraform plan.** Password hashes, keyed
  API key hashes, secrets injected from Secrets Manager, structured logs with sensitive keys
  redacted.

## Identity and sessions

| Control | Implementation |
| ------- | -------------- |
| Password storage | Argon2id (`argon2-cffi` defaults), rehashed on sign-in when the parameters change |
| Password policy | 10 to 256 characters; account creation by the CLI reads the password from a prompt or standard input, never from shell history |
| Sign-in throttling | 10 attempts per minute per client address (Valkey); after 8 consecutive failures an account is locked for 15 minutes |
| Unknown accounts | the same error and the same Argon2 work as a wrong password, so sign-in does not reveal which emails exist |
| Session token | HS256 JWT with `sub`, `jti`, `sv` (session version) and expiry (7 days by default), signed with `SESSION_SECRET` |
| Transport | httponly cookie, `SameSite=Lax`, `Secure` in production; also accepted as `Authorization: Bearer` |
| Sign-out | the token's `jti` goes on a denylist in Valkey until the token would expire |
| Sign out everywhere | a password change bumps the user's `session_version`; older tokens are refused |
| Sign-up | off unless `ALLOW_SIGNUP=true`; the first account of a deployment is created by the setup screen or the CLI and becomes the administrator |

If Valkey cannot be reached, a session cannot be checked against the sign-out list, so it is
refused with 503 instead of trusted. API keys keep working.

## API keys

- Format `rgk_<prefix>_<secret>`: a 10-character base32 prefix (the lookup key, shown in the
  dashboard) and a 43-character URL-safe secret from `secrets.token_urlsafe`.
- Only `HMAC-SHA256(API_KEY_PEPPER, secret)` is stored; verification uses a constant-time
  comparison. A database dump alone cannot recover or verify a key.
- A key belongs to one project with role `viewer` (query, answer, read) or `editor` (also
  ingest, create versions, datasets and runs). Keys can never manage members or other keys.
- Optional expiry (1 to 365 days); revocation is immediate. The full key is shown once.
- Requests made with a key are attributed to it in query logs and the audit trail.

## Authorisation and project isolation

| Role | Can |
| ---- | --- |
| viewer | read collections, documents, chunks, versions, datasets, runs and analytics; query and answer; use the playground |
| editor | everything a viewer can, plus ingest and delete documents, create and activate pipeline versions, manage datasets, start, baseline and delete runs |
| owner | everything an editor can, plus members, API keys, project settings, deleting collections and the project |

- The access dependencies (`ProjectAccess`, `CollectionAccess`) resolve `{project}` by slug
  or id, load the caller's membership or key, compare roles and only then call the route.
  A collection is always looked up inside the resolved project.
- The last owner of a project cannot be removed or demoted.
- An integration test calls every project-scoped route as a signed-in outsider and expects
  404 for each one, so a new route without the dependency fails CI.

## Ingestion: uploads and URLs

**Uploads**

- At most 20 files per request and `MAX_UPLOAD_MB` (25 MB by default) per file; the request
  body is capped by middleware before parsing starts.
- The extension selects the parser and the file's magic bytes must agree
  (`content_mismatch` otherwise): a renamed executable is not "a PDF".
- Parsers run with limits (`MAX_DOCUMENT_PAGES`, extracted text size), in a worker thread,
  and fail per document: one bad file marks one document `failed` with a message that is
  safe to show.
- Originals are stored under generated keys (`projects/<p>/collections/<c>/documents/<d>/`),
  never under a user-supplied path, and are only ever streamed back by the API after an
  access check. The bucket has no public access and no CORS.

**URLs** (`integrations/fetcher.py`)

- `http` and `https` only, on ports 80, 443 or 8000 to 9999.
- The host name is resolved and every address must be public: private, loopback,
  link-local (including the instance metadata address `169.254.169.254`), multicast and
  reserved ranges are refused, for IPv4 and IPv6.
- Redirects are followed by hand, at most 3, and every hop is checked again, so a public URL
  cannot redirect into the VPC.
- 20 second timeout, the same size cap as uploads, and only supported content types.
- `URL_FETCH_ALLOW_PRIVATE=true` exists for local development against services on your
  machine; production refuses to start with it.

## Model answers and prompt injection

Ingested content is untrusted: a document can contain text written to manipulate a model.

- Sources are passed to models inside a `<sources>` block, numbered, with an instruction
  that they are data and that instructions inside them must be ignored. The judge prompt
  says the same about the context, the answer and the reference.
- Answers can only cite sources they were given: `[n]` markers that point anywhere else are
  removed before the answer is returned, and each kept citation carries a quote from its
  source, so a reader can check it.
- Models have no tools and no network access through RAGKit; the worst outcome of an
  injection is a wrong or unhelpful answer, which faithfulness and correctness metrics are
  designed to expose.
- The default extractive answerer uses no model at all.
- Provider credentials (`LLM_API_KEY`, `EMBEDDINGS_API_KEY`) live in Secrets Manager on AWS
  and are never returned by the API.

## Web application

- The dashboard renders all user and document content as text (React escaping); query
  highlighting splits text into segments rather than injecting HTML.
- CSRF: cookie-authenticated requests with unsafe methods must carry an `Origin` (or
  `Referer`) from `CORS_ORIGINS` or `WEB_URL`; bearer requests are not affected.
- CORS lists the web origins explicitly, with credentials; `*` is refused in production.
- API responses carry `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `X-Frame-Options: DENY` and, in production, HSTS. The web app sends `nosniff`,
  `X-Frame-Options: DENY` and a restrictive `Permissions-Policy`.
- The API URL reaches the browser through `/env.js` at runtime; nothing secret is ever part
  of the web image or its configuration.

## Data protection

| Data | Protection |
| ---- | ---------- |
| Original files and URL snapshots | S3, SSE-KMS with the deployment key, versioned, public access blocked, TLS-only bucket policy |
| Database | RDS storage encrypted with the key, TLS required (`rds.force_ssl`), private subnets only, automated backups |
| Cache | ElastiCache encrypted at rest and in transit, auth token required |
| Queue | SQS encrypted with the key; messages carry ids only, never document content |
| Secrets | Secrets Manager, encrypted with the key |
| Logs | CloudWatch, encrypted with the key |

Messages, logs and audit details never contain document text or answers. Query text is kept
in `query_logs` for the top-queries view and can be turned off with `QUERY_LOG_TEXT=false`.

## Infrastructure

- **Network**: public subnets hold only the load balancer and NAT gateways; tasks, the
  database and the cache are in private subnets without public addresses. Security groups
  allow the load balancer to the services' container port, the services to the database and
  cache ports, and HTTPS out. The default security group denies everything. VPC flow logs
  are on.
- **Edge**: TLS 1.2+ (`ELBSecurityPolicy-TLS13-1-2-2021-06`), HTTP redirected to HTTPS,
  invalid headers dropped, unknown hosts answered 404, `/metrics` answered 404 on every
  host (Prometheus metrics stay inside the VPC), optional WAF with AWS managed rules and a
  per-address rate rule.
- **Containers**: non-root users, read-only root file systems with a writable `/tmp`, no
  privileged mode, `tini` as PID 1 for clean signal handling, pinned base images.
- **IAM**: one execution role (pull, log, inject the listed secrets) and one task role per
  service. The API may put, get and delete objects under `projects/` and send to the jobs
  queue; the worker may get and put objects (URL snapshots) and consume the queue. KMS use is
  limited to requests made through S3, SQS and Secrets Manager.
- **Client addresses**: uvicorn trusts `X-Forwarded-For` only from the VPC range
  (`FORWARDED_ALLOW_IPS`), never `*`, so per-address limits see the real client.
- **Policy as code**: tflint and checkov run in CI; every checkov exception is an inline
  skip with its reason next to the resource.

## Secrets

| Secret | Locally | On AWS |
| ------ | ------- | ------ |
| `SESSION_SECRET`, `API_KEY_PEPPER` | random values in `deploy/compose/.env` (`make env`) | generated by Terraform into Secrets Manager, injected into the tasks |
| Database password | fixed local value in compose | managed and rotated by RDS in Secrets Manager; the app reads it for each new connection (`DATABASE_SECRET_ARN`) |
| `REDIS_URL` (with auth token) | local Valkey without auth | Secrets Manager |
| `LLM_API_KEY` | optional, in `.env` | optional, a secret ARN passed to Terraform |

`deploy/compose/.env`, `.env.aws` and `terraform.tfvars` are git-ignored; `make sanitize`
and gitleaks fail CI on committed credentials, private keys or real account ids.

## Logging and audit

- Structured JSON logs with a request id on every line; keys that look sensitive
  (`password`, `secret`, `token`, `authorization`, `api_key`, `cookie`) are redacted before
  a line is written. Access logs are off in uvicorn; the request middleware logs method,
  route template, status and duration instead.
- The audit trail records sign-in relevant and data-changing actions per project: members,
  keys, collections, documents, versions and activations, datasets and runs, with the
  acting person or key.

## Abuse limits

Per minute, counted in Valkey: sign-in 10 per address; query and answer 600, ingestion 120
and evaluation runs 30 per person or key. Responses carry `X-RateLimit-*` headers and 429s a
`Retry-After`. Without Valkey, serving limits let requests through uncounted and sign-in
answers 503. Further bounds: 20 files per upload, 100 sources per import, 2,000 questions per
dataset import, `top_k` at most 50 and 200 candidates, filters at most 32 conditions deep 4.

## Production guard rails

With `APP_ENV=production` the API and worker refuse to start (listing every problem) unless:
`SESSION_SECRET` and `API_KEY_PEPPER` are random, at least 32 characters and different;
`COOKIE_SECURE=true`; `CORS_ORIGINS` lists explicit origins; storage is S3 and the queue is
SQS; `AWS_ENDPOINT_URL` is unset (no emulator); `URL_FETCH_ALLOW_PRIVATE` is false; and a
model provider, when configured, names its model. The demo seeder refuses to run in
production.
