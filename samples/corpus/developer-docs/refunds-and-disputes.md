# Refunds and disputes

## Refunds

You can refund a payment fully or partially. Refunds can be issued up to 180 days after the
original charge. You can issue several partial refunds as long as their total does not exceed
the original amount.

Processing fees are not returned when you refund a payment. Refunds usually take 5 to 10
business days to appear on the customer's statement, depending on their bank.

## Disputes

A dispute (also called a chargeback) happens when a cardholder asks their bank to reverse a
payment. You are notified with the charge.dispute.created webhook event.

Each dispute carries a dispute fee of $15, which is refunded if you win. Respond with
evidence within 7 days through the dashboard or the API. Useful evidence includes receipts,
shipping tracking numbers and your communication with the customer. The card network
usually decides within 60 to 75 days.

## Dispute monitoring

Card networks watch the share of your payments that are disputed. A dispute rate above 0.75%
in a month enrolls your account in a monitoring program, which can add fees and require a
remediation plan.
