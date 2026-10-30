# Payments API

A PaymentIntent tracks a payment from creation to completion. Create one PaymentIntent for
each order or customer session.

## Lifecycle

A PaymentIntent moves through these statuses: requires_payment_method, requires_confirmation,
requires_action (when the customer must complete 3-D Secure), processing and finally
succeeded. A PaymentIntent can be canceled at any time before it succeeds.

## Amounts and currencies

Amounts are integers in the smallest currency unit, so 1099 means $10.99. The minimum charge
is 50 cents in USD and the maximum is 999,999.99 USD per payment. Payments can be accepted in
135 currencies and settled in USD, EUR, GBP or INR.

## Capturing later

By default payments are captured automatically when they are confirmed. Set capture_method to
manual to place a hold on the card and capture the funds later, for example when an order
ships. A manually captured payment must be captured within 7 days, after which the
authorization expires and the hold is released.

## Metadata

Attach your own key-value data to a PaymentIntent with the metadata parameter. You can
specify up to 50 keys, with key names up to 40 characters and values up to 500 characters.

## Listing and pagination

List endpoints return up to 100 objects per page, with a default of 10. Use the
starting_after parameter with the last object id of a page to fetch the next page.

## 3-D Secure

Some banks require the customer to authenticate a payment with 3-D Secure. When that happens
the PaymentIntent moves to requires_action and your client must show the authentication
challenge. Payments authenticated with 3-D Secure shift liability for fraud disputes from
you to the card issuer. Set payment_method_options.card.request_three_d_secure to any to ask
for authentication on every payment.

## Statement descriptors

The statement descriptor is the text that appears on the customer's card statement. It
defaults to your account's business name and can be overridden per payment with
statement_descriptor. Descriptors are limited to 22 characters and must contain at least one
letter.

## Saving cards for later

To charge a customer again later without asking for their card, create a Customer and set
setup_future_usage to off_session when you create the first PaymentIntent. The saved payment
method can then be reused for subscriptions or one-click checkout.
