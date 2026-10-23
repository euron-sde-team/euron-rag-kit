# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.x (latest minor) | Yes |
| Older minors | No |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository ("Security" tab, "Report a vulnerability").

Please include:

- the affected component (`apps/api`, `apps/web`, `sdk/python`, `infra/terraform/...`) and
  the version or commit,
- a description of the issue and its impact,
- steps to reproduce, or a proof of concept,
- any suggested mitigation.

What to expect:

| Stage | Target |
| ----- | ------ |
| Acknowledgement | within 3 business days |
| Initial assessment and severity | within 7 business days |
| Fix or mitigation for critical and high issues | within 30 days |
| Coordinated public disclosure | after a fix is released, credited to you unless you prefer otherwise |

## Scope

In scope: the code in this repository and the infrastructure it provisions with its default
settings. The most important classes of issue for this project are:

- **Crossing a project boundary**: reading, querying, evaluating or citing another project's
  collections, documents, chunks or evaluation results, with a session or an API key.
- **Server-side request forgery through the URL loader**: making a RAGKit server fetch an
  address it refuses by policy (private ranges, loopback, link-local, cloud metadata).
- **API key or session forgery**, and privilege escalation from the `viewer` to the `editor`
  or `owner` role.

Out of scope:

- **Content a project member can already read.** Members see every collection in their
  project by design, and retrieval results and answers quote those documents.
- **Instructions planted inside your own documents.** A model-backed answerer or judge may
  follow text written into a document you ingested yourself. RAGKit fences sources as data
  and tells the model to ignore instructions inside them, but no prompt is a security
  boundary. Reports where a document crosses into another project or exposes secrets are in
  scope.
- **The demo seed.** `make demo` creates well-known demo accounts on purpose and refuses to
  run with `APP_ENV=production`.
- Findings that need a compromised host, a compromised AWS account or leaked deployment
  secrets.
- Denial of service through resource exhaustion of a deployment you operate yourself.

## Hardening checklist for operators

See [docs/architecture/security.md](docs/architecture/security.md#operator-checklist).
