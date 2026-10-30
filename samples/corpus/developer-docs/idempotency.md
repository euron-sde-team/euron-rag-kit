# Idempotent requests

Networks fail. When a request times out you cannot tell whether the payment was created, and
retrying blindly could charge a customer twice. Idempotency keys make retries safe.

## Sending an idempotency key

Send an Idempotency-Key header with any POST request. The key is a unique value you generate
for each operation; we recommend a version 4 UUID. Keys can be up to 255 characters long.

The first request with a given key is processed normally. Results, including errors, are
saved for 24 hours. A retry with the same key within 24 hours returns the saved response
instead of performing the operation again, and the response carries the header
Idempotent-Replayed: true.

## Conflicts

Reusing an idempotency key with different request parameters returns HTTP 409 with the error
code idempotency_conflict. Generate a new key whenever the parameters change.

## Which requests need keys

GET and DELETE requests are idempotent by definition, so an Idempotency-Key header on them is
ignored. The official SDKs add an idempotency key to every POST they retry automatically.
