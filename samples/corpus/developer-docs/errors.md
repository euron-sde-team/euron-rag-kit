# Errors

Acme Payments uses conventional HTTP status codes. Codes in the 2xx range mean success, 4xx
codes mean the request failed because of the information provided, and 5xx codes mean
something went wrong on our side.

## The error object

Every error response contains an error object with these fields: type, code, message, param
(the request parameter at fault, when there is one) and request_id. Include the request_id
when you contact support.

## HTTP status codes

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | invalid_request | A required parameter is missing or invalid |
| 401 | authentication_failed | No valid API key was provided |
| 402 | card_error | The card was declined |
| 403 | permission_denied | The key lacks permission for this request |
| 404 | not_found | The object does not exist |
| 409 | idempotency_conflict | An idempotency key was reused with different parameters |
| 429 | rate_limited | Too many requests |
| 500 | api_error | Something went wrong on our side |

## Card decline codes

Card errors carry a decline code that tells you why the bank refused the payment.

| Decline code | Name | What to do |
| --- | --- | --- |
| ACME-4001 | card_declined | Ask the customer to use another card |
| ACME-4011 | insufficient_funds | Ask the customer to use another card or try again later |
| ACME-4012 | expired_card | Ask the customer to update the expiry date |
| ACME-4013 | incorrect_cvc | Ask the customer to check the three-digit security code |
| ACME-4020 | processing_error | Safe to retry with backoff |
| ACME-4031 | fraudulent | Do not retry; the bank suspects fraud |

## Retrying failed requests

Retry 5xx responses and ACME-4020 processing errors with exponential backoff, always with the
same idempotency key. Never retry a payment declined with ACME-4031, because repeated
attempts on a card flagged as fraudulent can get your account reviewed.
