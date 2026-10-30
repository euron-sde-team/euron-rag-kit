# Rate limits

Rate limits protect the API from bursts that would slow it down for everyone. Limits are
applied per account.

## Default limits

| Mode | Requests per second |
| --- | --- |
| Live mode | 100 |
| Test mode | 25 |
| Search endpoints | 20 |

Payout creation also has a concurrency limit: at most 5 payout creation requests can be in
progress at the same time.

## When you hit a limit

Requests over the limit fail with HTTP 429 and the error code rate_limited. The response
includes a Retry-After header with the number of seconds to wait before retrying.

Retry with exponential backoff and jitter rather than retrying immediately in a tight loop.
The official SDKs retry 429 responses automatically.

## Requesting a higher limit

If your traffic regularly approaches the limits, contact support with two weeks of traffic
projections and we can raise the limits for your account.

## Load testing

Do not load test against live mode: test traffic counts against your live limits and can
affect real customers. Load test in test mode instead, keeping in mind that test mode allows
25 requests per second. Mock the API in your own test environment when you need higher
throughput than that.

## Read-after-write

Objects you create are available to read immediately. List endpoints are eventually
consistent and may take up to a few seconds to include newly created objects, so read a new
object by its id rather than searching for it.
