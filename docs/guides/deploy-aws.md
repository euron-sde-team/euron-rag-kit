# Deploy to AWS

This guide deploys a complete environment with one command: network, keys, database, cache,
queue, storage, the web app, the API, the job workers and monitoring. Two environments ship
with the repository: `aws-dev` (a cheaper full copy) and `aws-prod`. Both call the same module,
`infra/terraform/modules/deployment`, with different sizes and safety switches.

After deployment you have:

| URL | What |
| --- | --- |
| `https://app.<domain>` | The dashboard |
| `https://api.<domain>` | The API (interactive reference at `/docs`) |

- [What gets created](#what-gets-created)
- [Prerequisites](#prerequisites)
- [1. Configure the environment](#1-configure-the-environment)
- [2. Deploy](#2-deploy)
- [3. Create the first account](#3-create-the-first-account)
- [4. Answer with a hosted model (optional)](#4-answer-with-a-hosted-model-optional)
- [Updating](#updating)
- [Local containers against real AWS](#local-containers-against-real-aws)
- [Tearing down](#tearing-down)
- [Security notes](#security-notes)

## What gets created

| Area | Resources |
| --- | --- |
| Network | A VPC with public and private subnets in two (dev) or three (prod) zones, NAT (one, or one per zone) for model providers and the URLs people ingest, an S3 gateway endpoint, flow logs, and in prod interface endpoints for KMS and Secrets Manager |
| Keys and secrets | One customer-managed KMS key with rotation (S3, SQS, RDS, Valkey, Secrets Manager and logs); Secrets Manager entries for `SESSION_SECRET` and `API_KEY_PEPPER` (generated), `REDIS_URL` and the RDS-managed database password |
| Data | RDS PostgreSQL 16 with pgvector (TLS enforced, Multi-AZ in prod), ElastiCache Valkey with TLS and an auth token (a replica in prod), the corpus bucket for originals and URL snapshots (private, versioned, SSE-KMS), the jobs queue with its dead-letter queue (three receives) |
| Compute | ECR repositories for `api` and `web` (immutable tags, scan on push; the worker runs the `api` image), an ECS cluster with three Fargate services on ARM64 with CPU autoscaling, and a task definition for one-off CLI tasks |
| Identity | Separate task roles: the API may read, write and delete corpus objects and enqueue jobs; the workers may read originals, write URL snapshots and consume jobs |
| Edge | An Application Load Balancer routing `app.` and `api.` by host, an ACM certificate, DNS records, HTTP redirected to HTTPS, `/metrics` answered with 404, and in prod a WAF |
| Monitoring | CloudWatch log groups, alarms (5xx, unhealthy targets, CPU and memory, job backlog, any dead letter, database) to an SNS topic, optionally e-mailed, and a dashboard |

| Switch | `aws-dev` | `aws-prod` |
| --- | --- | --- |
| Zones, NAT gateways | 2, one shared | 3, one per zone |
| Interface endpoints | off | on |
| Database | single zone, 3 days of backups | Multi-AZ, 14 days, deletion protection |
| Cache replicas | 0 | 1 (automatic failover) |
| WAF | off | on |
| API, worker, web (min to max) | 1 to 2 each | 2 to 6, 2 to 8, 2 to 6 |
| Task sizes | API 1 vCPU and 2 GB, worker 1 vCPU and 3 GB (2 jobs at once), web 0.25 vCPU and 512 MB | the same (override in `envs/aws-prod/main.tf`) |
| Log retention | 14 days | 365 days |

The API and the worker each load the embedding model and the reranker (baked into the image),
which is why they get more memory than a typical web service.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| An AWS account and credentials | With permission to create the resources above; the deploy runs as you |
| Terraform 1.10 or later | `versions.tf` requires `>= 1.10.0`, the AWS provider `~> 6.70` and `random ~> 3.9` |
| Docker with `buildx` | Images are built for `linux/arm64` |
| AWS CLI v2 | ECR login, waiting for services, one-off tasks |
| `python3` | Used by the scripts to read Terraform output |
| A domain | The dashboard is served at `app.<domain>` and the API at `api.<domain>` |

Use the same region in your shell as in `terraform.tfvars`:

```bash
export AWS_REGION=us-east-1
```

## 1. Configure the environment

```bash
cp infra/terraform/envs/aws-dev/terraform.tfvars.example infra/terraform/envs/aws-dev/terraform.tfvars
```

`terraform.tfvars` is git-ignored. Variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `region` | `us-east-1` | AWS region |
| `name_prefix` | `ragkit-dev` | Prefix for every resource name; the bucket name derives from it, so make it globally unique (for example `acme-ragkit-dev`) |
| `domain` | required | Parent domain, for example `ragkit.example.com` |
| `route53_zone_id` | `null` | Hosted zone for the domain: the certificate is validated and the DNS records are created automatically |
| `certificate_arn` | `null` | An issued ACM certificate for `app.<domain>` and `api.<domain>`, when the zone is not in Route53 |
| `alarm_email` | `null` | Address subscribed to the alarm topic (confirm the subscription e-mail) |
| `product_name` | `Euron RAGKit` | Name shown in the dashboard |
| `llm_provider` | `none` | `none` (offline extractive answers and deterministic grading), `openai` or `ollama` |
| `llm_model` | `""` | The model, when the provider is not `none` |
| `llm_base_url` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `llm_api_key_secret_arn` | `null` | Secrets Manager reference (`<secret arn>:<json key>::`) injected as `LLM_API_KEY` |
| `db_instance_class` | `db.t4g.medium` | RDS instance class |
| `cache_node_type` | `cache.t4g.small` | ElastiCache node type |
| `image_tag` | set by `make aws-deploy` | Image tag; set it here only to pin a release for manual `terraform` runs |

Minimal example:

```hcl
name_prefix     = "acme-ragkit-dev"
domain          = "ragkit.example.com"
route53_zone_id = "<ROUTE53_HOSTED_ZONE_ID>"
alarm_email     = "oncall@example.com"
```

The deployment module also takes `extra_environment` (plain configuration for the API and the
workers, never secrets: the values land in the task definitions in clear text), the task sizes
and counts, `kms_admin_principal_arns` and an access-log bucket for the load balancer; call it
from your own environment folder to set them.

**Without a Route53 zone**, request and validate an ACM certificate for `app.<domain>` and
`api.<domain>` yourself, set `certificate_arn`, and after the deploy point both names at the
`load_balancer_dns_name` output (CNAME or alias). The `certificate_validation_records` output
lists the DNS records to publish when you let Terraform request the certificate instead.

**Database size.** Vectors and chunk text dominate storage: a 384-dimension embedding is
about 1.5 KB per chunk before the index, and every pipeline version with its own chunking or
embedding settings builds its own index. The module starts at 30 GiB and lets storage
autoscale to 200 GiB.

### Remote state

State contains the generated application secrets. For anything shared, keep it in S3:

```bash
cp infra/terraform/envs/aws-dev/backend.tf.example infra/terraform/envs/aws-dev/backend.tf
```

Uncomment the block and fill in a bucket that is private, versioned and encrypted, with
access limited to the people who deploy. It uses S3-native locking (`use_lockfile = true`),
so no DynamoDB table is needed.

## 2. Deploy

```bash
make aws-deploy ENV=aws-dev
```

`ENV` defaults to `aws-dev`; `TAG` defaults to the first 12 characters of the current commit.
The target runs `scripts/aws-deploy.sh <env> <tag>`, which:

1. checks that `terraform`, `docker` and `aws` are installed and `terraform.tfvars` exists,
   and notes uncommitted changes (images are built from the working tree as it is);
2. **registries**: `terraform apply -target=module.ragkit.module.ecr`;
3. logs Docker in to ECR;
4. **images**: builds `api` and `web` (`infra/docker/api.Dockerfile` and `web.Dockerfile`) for
   `linux/arm64` and pushes `<repo>:<tag>`;
5. **infrastructure**: `terraform apply` of everything else with that `image_tag`;
6. **rollout**: `aws ecs wait services-stable` for the `api`, `worker` and `web` services;
7. prints the `urls` output and the next step.

The first image build downloads the embedding model, the reranker and the tokenizer (about
200 MB) and bakes them into the image, so no task ever downloads a model at runtime.

Database migrations run when the API (and the worker) boots (`MIGRATE_ON_BOOT=true`) under a
Postgres advisory lock, so several tasks starting together are safe; the first migration
enables the `vector` and `citext` extensions. To run them as an explicit step:

```bash
make aws-migrate ENV=aws-dev
```

To preview changes without applying:

```bash
make aws-plan ENV=aws-dev
```

## 3. Create the first account

Until the first account exists, the sign-in page offers to create it (the first account
becomes the instance administrator), so do that right after deploying, or from your machine
as a one-off ECS task:

```bash
make aws-cli ENV=aws-dev ARGS="user create --email you@example.com --name 'Your Name' --admin"
```

With no terminal attached (an ECS one-off task has none), the command generates a temporary
password and prints it in the task's log, which the target tails for you. Sign in at
`https://app.<domain>` and change it at once: account menu, **Change password**. Then create a
project and a collection and add sources. Further accounts join a project through
**Settings, Members**. `ALLOW_SIGNUP` stays `false` on AWS, so nobody can create an account
from the sign-in page once the first one exists.

To fill the new deployment with your own content and test it from code:

1. **Settings, API keys**: create a viewer key for your application and an editor key for CI.
2. Add documents in the dashboard, or `ragkit ingest <collection> docs/*.pdf` with the SDK.
3. Point your application and your CI at `https://api.<domain>` (`RAGKIT_URL`).

## 4. Answer with a hosted model (optional)

The offline extractive answerer works with no key. To answer (and optionally grade
evaluations) with an OpenAI-compatible model:

1. Store the key in Secrets Manager (with the default `aws/secretsmanager` key, or the
   deployment's own KMS key; the task execution role can decrypt either):

   ```bash
   aws secretsmanager create-secret --name acme-ragkit-dev/llm \
     --secret-string '{"LLM_API_KEY": "<your key>"}'
   ```

2. Reference it in `terraform.tfvars`:

   ```hcl
   llm_provider           = "openai"
   llm_model              = "gpt-4.1-mini"
   llm_api_key_secret_arn = "<secret arn>:LLM_API_KEY::"
   ```

3. `make aws-deploy ENV=aws-dev`.

For a model server inside your network (Ollama, vLLM), set `llm_provider = "ollama"` or
`"openai"` with `llm_base_url` pointing at it, and make sure the tasks' security group can
reach it. Model calls carry the question and the retrieved passages, so choose a provider
that fits your data policy; answers are cited and verified either way.

## Updating

Run `make aws-deploy` again from the new commit. Images get a new tag; ECS starts the new
tasks next to the old ones, moves traffic once they pass their health checks, and rolls back
on its own if they never do. A stopping worker stops receiving, lets in-flight jobs finish
for up to 90 seconds, hands any still running back to the queue at once, then exits (ECS
waits 120 seconds before it kills a worker), so a rollout never loses or stalls work.

To roll back, apply the previous tag without rebuilding (tags are immutable, so the images
are still in ECR):

```bash
terraform -chdir=infra/terraform/envs/aws-dev apply -var image_tag=<previous tag>
```

Keep migrations additive (add first, remove a release later), so the previous image still
works against the newer schema; that is what makes a rollback a tag change.

## Local containers against real AWS

To run the local stack against the real bucket, queue and key of an AWS environment (for
example to test IAM or KMS behaviour the emulator does not reproduce):

```bash
cp deploy/compose/.env.aws.example deploy/compose/.env.aws   # fill in from the Terraform outputs
make up-aws
```

The containers use your AWS profile (`AWS_PROFILE`, default `default`), mounted read-only.

## Tearing down

```bash
terraform -chdir=infra/terraform/envs/aws-dev destroy
```

In `aws-prod`, turn off deletion protection first (it guards the database, the load balancer
and the registries) and empty the versioned corpus bucket. The KMS key and the secrets enter
their deletion and recovery windows (30 days in prod, 7 and 0 in dev) instead of disappearing
at once. Deleting the KMS key makes the stored originals and the queue unreadable.

## Security notes

- The tasks run in private subnets with no public IPs, as non-root users with read-only root
  filesystems; only the load balancer is public, and it answers `/metrics` with 404.
- Uploads are stored under generated keys in a private, versioned, KMS-encrypted bucket; the
  URL loader refuses private, loopback, link-local and metadata addresses on every redirect.
- Forwarded client addresses are trusted only from the VPC range (`FORWARDED_ALLOW_IPS`), so
  the per-address sign-in limit sees the real client.
- `make tf-security` (checkov) passes with every skip justified inline.
- See [security.md](../architecture/security.md#production-guard-rails) for what the process
  refuses to start without, and [operations.md](operations.md) for day-two tasks: alarms,
  scaling, rotation, backups.
