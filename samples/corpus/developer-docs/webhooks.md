# Webhooks

Webhooks tell your server about events in your account as they happen, such as a payment
that succeeds after a 3-D Secure challenge or a payout that fails. Acme sends each event as
a JSON POST request to the endpoints you register.

## Registering endpoints

Register endpoints in Dashboard > Developers > Webhooks. Endpoints must use HTTPS, and each
account can register up to 16 endpoints. Subscribe each endpoint only to the event types it
handles.

Common event types include payment_intent.succeeded, payment_intent.payment_failed,
charge.refunded, charge.dispute.created, payout.paid and payout.failed.

## Verifying signatures

Every webhook request carries an Acme-Signature header in the form t=timestamp,v1=signature.
To verify it, compute an HMAC-SHA256 of the timestamp, a period and the raw request body,
using the endpoint's signing secret (it starts with whsec_). Compare your result with the v1
value using a constant-time comparison.

Reject events whose timestamp is more than five minutes old. The timestamp is part of the
signed payload, so this check stops attackers from replaying a captured request later.

## Responding and retries

Respond with a 2xx status code within 10 seconds, before doing any slow work. If your
endpoint does not answer in time or returns an error, Acme retries the event with exponential
backoff for up to 3 days. You can also resend any event from the dashboard.

## Duplicates and ordering

Events can arrive more than once and in a different order than they happened. Make your
handler idempotent by recording the event id of every event you process and skipping ids you
have already seen.

## The event object

Each event has an id that starts with evt_, a type, a created timestamp, an api_version and a
data.object field holding the object the event is about, such as the PaymentIntent that
succeeded. The api_version is the version that was current when the event was created, so
pin your parsing code to a version and upgrade it deliberately.

## Testing webhooks locally

Use the Acme CLI to forward events to a server running on your machine:

    acme listen --forward-to localhost:4242/webhooks

The CLI prints a temporary signing secret that starts with whsec_. Use it while testing, and
trigger sample events with acme trigger payment_intent.succeeded.

## Best practices

- Return a 2xx response before running slow work such as sending email; queue that work.
- Verify every signature, even in staging environments.
- Do not rely on events for real-time user interfaces; poll the object when a user is waiting.
- Roll the endpoint signing secret if it may have leaked. The old secret keeps working for up
  to 24 hours so you can deploy the new one.
