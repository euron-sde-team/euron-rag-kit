# Handling refund requests

Merchants often ask support to refund a payment for them. Merchants issue refunds themselves
from the dashboard or the API; support only explains the rules.

## Checking eligibility

1. Confirm the payment is less than 180 days old. Older payments cannot be refunded through
   Acme; the merchant must send the customer money another way.
2. Check whether earlier partial refunds exist. Partial refunds can never add up to more than
   the original amount.
3. Remind the merchant that processing fees are not returned on refunds.

## Reply template

Thanks for reaching out. You can refund this payment from Dashboard > Payments by opening the
payment and choosing Refund. The customer will usually see the refund within 5 to 10 business
days. Processing fees for the original payment are not returned.
