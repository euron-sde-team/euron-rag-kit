# Platforms and marketplaces

Acme Connect lets platforms and marketplaces accept payments on behalf of other businesses,
called connected accounts, and pay them out.

## Connected accounts

Each seller on your platform gets a connected account. Create connected accounts with the
accounts API and send each seller through hosted onboarding, where they provide the business
and identity details required for verification. A connected account cannot receive payouts
until verification is complete.

Verification usually finishes within 1 to 2 business days. Sellers whose details cannot be
verified automatically are asked for documents, such as a business registration certificate.

## Taking fees

Platforms earn revenue with application fees. Set application_fee_amount on a PaymentIntent
to keep part of the payment, and the rest is transferred to the connected account. Acme's own
processing fee is charged to the platform.

## Paying out connected accounts

Connected accounts receive payouts on their own schedule, by default daily on a two business
day rolling basis like a standard account. Platforms can pause payouts for a connected
account, for example while investigating suspected fraud.

## Responsibilities

Platforms are responsible for the disputes and refunds of the payments they create, and for
monitoring their sellers for fraud. A platform can debit a connected account's balance to
recover refunds and dispute losses.
