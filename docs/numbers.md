# How the numbers are made

Some figures are exact, some are estimates. This page says which, and what the bridge assumes.

## Exact

- **Gross per payment** is what Creem recorded as paid, less what was refunded.
- **Net per payment** is gross less its VAT (in proportion to what was kept) and Creem's fee. The fee is 3.9 % + 0.40 of the total including VAT, rounded down to cents, as in Creem's worked example (24.00 → 1.33). It is assumed to stay with Creem when a payment is refunded.
- **Revenue** spreads each payment over the period it covers by time, month by month in `TZ`. The cents are shared out so the months add up exactly to the payment.

## Approximations

- **Refunds** count in the month of the payment they refund. Creem records how much was refunded but not when.
- **Forecast:** every active subscription repeats at its interval from its next payment date, at its price less its discount while the discount runs. A subscription cancelled to the end of its period forecasts nothing. Net uses the VAT share of the subscription's last payment; without one, its store's average.
- **Payouts** are not in Creem's API. They follow Creem's published rules: on the 1st and 15th, once the balance is at least `PAYOUT_MIN`, with money held `PAYOUT_HOLD_DAYS` first, less the higher of `PAYOUT_FEE_MIN` and `PAYOUT_FEE_PERCENT`. The real payouts are on the payout activity tab of each store's balance page.

## Refused rather than guessed

The bridge answers with an error naming the store instead of totals that silently leave something out when:

- Creem can't be reached, answers an error, or sends something unexpected;
- a payment has a status it doesn't know;
- a product bills by the week or day, or its price excludes VAT.

Each of these is a small addition when a store needs it: open an issue.
