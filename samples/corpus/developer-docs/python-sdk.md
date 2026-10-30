# Python SDK

The official Python SDK wraps the REST API with typed objects, automatic retries and
pagination helpers.

## Installation

Install the SDK with pip install acme-payments. It requires Python 3.9 or later.

## Configuration

Create a client with your secret key, ideally read from an environment variable:

    import os
    import acme

    client = acme.Client(api_key=os.environ["ACME_API_KEY"])

Since version 5.0 the SDK also ships acme.AsyncClient for asyncio applications.

## Retries and timeouts

The client retries failed requests automatically. The max_network_retries setting defaults
to 2. Connection errors, 429 responses and 5xx responses are retried with exponential
backoff, and the SDK adds an idempotency key to every POST it retries so a retry never
creates a duplicate payment. Requests time out after 80 seconds by default; pass timeout to
the client to change it.

## Pagination

List methods return one page at a time. Call auto_paging_iter to iterate over every object
across pages, for example client.payment_intents.list(limit=100).auto_paging_iter().

## Debug logging

Set the environment variable ACME_LOG=debug to log every request and response, with secret
keys redacted.
