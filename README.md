# creem-grafana-bridge

Revenue, cashflow, a forecast and estimated payouts of one or more [Creem](https://creem.io) stores, as JSON series
for Grafana. It stores nothing: every answer is computed from Creem's own records (cached a few minutes), so a refund
corrects past months by itself. Python standard library only; it sends Creem nothing but GET requests.

## What it serves

`GET /series?kind=<kind>&basis=<basis>[&store=a,b]` with `Authorization: Bearer <BRIDGE_TOKEN>` returns rows

```json
[{"time": "2026-10-01T00:00:00+02:00", "store": "notefeed", "plan": "notefeed license, monthly", "currency": "EUR", "amount": 1.2}]
```

| kind | one row per | what |
|---|---|---|
| `revenue` | month × store × plan | what payments pay for, spread over the period each covers (a yearly payment ≈ 1/12 a month) |
| `cashflow` | month × store × plan | payments in the month they were made, less refunds |
| `forecast` | payment date × store × plan | what active subscriptions will pay, after their discounts, `FORECAST_MONTHS` ahead |
| `payouts` | payout date × store | estimated payouts to the bank, past and coming, after Creem's payout fee (plan `payout`) |

`basis=gross` is what customers paid (VAT included); `basis=net` is after VAT and Creem's fee. Months are calendar
months in `TZ`. Currencies are never added together. No customer data appears in any answer.

Optional: `by=plan` (default), `store` or `total` sums the plans (and stores) into `all`; `from` and `to` keep rows
with `from` ≤ time < `to`, as epoch milliseconds (Grafana's `${__from}`, `${__to}`) or relative: `now`, `now-30d`,
`now+12M`, `now/M` (the start of this month), `now+1M/M`. `per=month` sums the forecast's and the payouts' dates into months. `GET /stores` lists the configured stores, for a Grafana
variable.

`GET /health` answers `ok` without a token. If any store cannot be read, `/series` answers 502 naming the store rather
than totals that leave it out.

## Configuration

| Variable | Default | |
|---|---|---|
| `CREEM_STORES` | (required) | store names, comma-separated, e.g. `notefeed,other` |
| `CREEM_KEY_<NAME>` | (required) | each store's API key, e.g. `CREEM_KEY_NOTEFEED` |
| `BRIDGE_TOKEN` | (required) | the bearer token Grafana sends |
| `TZ` | `Europe/Berlin` | the zone months and dates are counted in |
| `FEE_PERCENT`, `FEE_FIXED` | `3.9`, `0.40` | Creem's fee per payment, on the total including VAT |
| `PAYOUT_MIN` | `50` | the balance a payout needs |
| `PAYOUT_HOLD_DAYS` | `12` | days new money is held before it can be paid out |
| `PAYOUT_FEE_MIN`, `PAYOUT_FEE_PERCENT` | `7`, `1` | the payout fee: the higher of the two |
| `FORECAST_MONTHS` | `12` | how far the forecast reaches |
| `CACHE_SECONDS` | `300` | how long a store's data is reused |
| `PORT` | `8080` | |
| `CREEM_API_URL` | `https://api.creem.io` | `https://test-api.creem.io` for test mode |

## Grafana

Install the [Infinity](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/) data source, point it at
the bridge with the token as a bearer token and the bridge's URL as an allowed host, then in a panel: type JSON,
parser Backend, URL `/series?kind=revenue&basis=net`, columns `time` (timestamp), `amount` (number), `plan` and
`store` (string), format time series.

## What is exact and what is estimated

- Gross and net per payment are exact: Creem's fee is 3.9 % + 0.40 of the total including VAT, rounded down to cents
  (Creem's worked example: 24.00 → 1.33). The fee is assumed to stay with Creem when a payment is refunded.
- Creem keeps no refund date: a refund counts in the month of the payment it refunds.
- Payouts are not in Creem's API. They are estimated from Creem's published rules (the 1st and 15th, the minimum, the
  hold, the payout fee); the actual dates and amounts are on the payout activity tab of each store's balance page.
- A subscription's net forecast uses the VAT share of its last payment; without one, its store's average.

## Development

```sh
uv run pytest -q
CREEM_STORES=demo CREEM_KEY_DEMO=… BRIDGE_TOKEN=t uv run python -m creem_bridge
```

MIT licence.
