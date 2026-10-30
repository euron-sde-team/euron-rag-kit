# Getting started with Acme Payments

Acme Payments lets you accept card and bank payments through one REST API. This guide takes
you from a new account to your first successful test payment in about ten minutes.

## Create an account

Sign up at dashboard.acme-payments.example. Every new account starts in test mode, so you
can build and test your integration without moving real money. Switch to live mode from the
dashboard once your business details are verified.

## Get your API keys

Each account has two pairs of keys: one pair for test mode and one for live mode. Secret keys
authenticate requests from your server. Test secret keys start with ak_test_ and live secret
keys start with ak_live_. Publishable keys start with pk_ and are only used to tokenize card
details in the browser or a mobile app.

Keep secret keys on your server. Anyone holding a secret key can create charges and refunds
on your account.

## Make your first request

All API requests go to the base URL https://api.acme-payments.example/v2 over HTTPS. Send
your secret key as a bearer token in the Authorization header.

To take a payment, create a PaymentIntent with an amount in the smallest currency unit and a
currency. For example, an amount of 2000 with currency usd charges $20.00. Confirm the
PaymentIntent with the test card number 4242 4242 4242 4242, any future expiry date and any
three-digit CVC.

## Next steps

- Read Authentication to learn about restricted keys and key rotation.
- Add an Idempotency-Key header to every POST request so retries are safe.
- Register a webhook endpoint to hear about payments that succeed or fail asynchronously.
