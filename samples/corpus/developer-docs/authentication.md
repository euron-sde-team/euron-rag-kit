# Authentication

The Acme Payments API authenticates every request with an API key sent as a bearer token:

    Authorization: Bearer ak_test_your_key_here

Requests without a valid key fail with HTTP 401 and the error code authentication_failed.
Requests made over plain HTTP are refused; the API requires TLS 1.2 or higher.

## Secret, publishable and restricted keys

Secret keys can perform any operation on your account and must only be used on your server.
Publishable keys can only tokenize payment details, so they are safe to embed in a web page
or a mobile app. Never embed a secret key in a mobile app, even an obfuscated one.

Restricted keys carry only the permissions you grant them, for example read-only access to
payouts for a reporting job. Create restricted keys for services that do not need full
access, and give each service its own key so you can revoke one without affecting the rest.

## Rotating keys

Roll a key from Dashboard > Developers > API keys. Rolling creates a new key immediately and
keeps the old key working for a grace period you choose, up to 7 days, so you can deploy the
new key without downtime. A key that may have leaked should be rolled with no grace period.

## Two-factor authentication

Dashboard users with the admin role must enable two-factor authentication. API keys are not
affected by two-factor settings.
