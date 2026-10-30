# Escalation policy

Tier 1 support answers account, billing and integration questions. Escalate to the payments
on-call engineer when an issue affects payments for many customers at once.

## Severity levels

- Severity 1: payments cannot be processed, or customer data may be exposed.
- Severity 2: a feature is degraded, or the error rate is above 5% for more than ten minutes,
  but payments still succeed.
- Severity 3: an issue affects a single merchant and has a workaround.

## When to page on-call

Page the payments on-call engineer through PagerDuty within 10 minutes when payment failures
affect more than 100 customers, or for any suspected data exposure. Do not page for a single
merchant's integration problem; open a Severity 3 ticket instead.

## Handing over

Add the merchant id, request ids, timestamps and the exact error codes to the ticket before
escalating. Stay on the ticket as the customer contact until engineering takes over.
