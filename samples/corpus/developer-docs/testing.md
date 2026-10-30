# Testing your integration

Test mode behaves like live mode but never moves real money. Use the test card numbers below
with any future expiry date and any three-digit CVC.

## Test card numbers

| Card number | Result |
| --- | --- |
| 4242 4242 4242 4242 | The payment succeeds |
| 4000 0000 0000 0002 | Declined with ACME-4001 card_declined |
| 4000 0000 0000 9995 | Declined with ACME-4011 insufficient_funds |
| 4000 0000 0000 0069 | Declined with ACME-4012 expired_card |
| 4000 0000 0000 0127 | Declined with ACME-4013 incorrect_cvc |
| 4000 0027 6000 3184 | Requires 3-D Secure authentication |
| 4000 0000 0000 0259 | Succeeds, then is disputed as fraudulent |

## Test bank accounts

Use routing number 110000000 with account number 0001234567 to simulate a successful bank
payment, or account number 0001111116 to simulate a payment that fails because the account
is closed.

## Testing payouts

Payouts in test mode are simulated and arrive instantly. To test a failed payout, add the
test bank account with account number 0001111116 as your payout destination; the next
payout fails and sends a payout.failed event.

## Going live checklist

1. Swap your test secret key for your live secret key in your server configuration.
2. Register your live webhook endpoints; test endpoints do not receive live events.
3. Make sure every POST request sends an Idempotency-Key header.
4. Confirm your statement descriptor reads correctly.
