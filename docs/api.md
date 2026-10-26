# HTTP API

## `GET /series`

Needs `Authorization: Bearer <BRIDGE_TOKEN>`. Returns a JSON list of rows:

```json
[{"time": "2026-10-01T00:00:00+02:00", "store": "shop", "plan": "Pro, monthly", "currency": "EUR", "amount": 1.2}]
```

`plan` is the Creem product's name (`one-time` for a payment without a subscription). Amounts are in major units, rounded to cents.

| Parameter | Values | |
|---|---|---|
| `kind` | `revenue`, `cashflow`, `forecast`, `payouts` | required; see below |
| `basis` | `gross` (default), `net` | before or after VAT and Creem's fee; payouts are always net |
| `store` | names, comma-separated | default: every store |
| `by` | `plan` (default), `store`, `total` | sums plans (and stores) into `all` |
| `per` | `date` (default), `month` | sums the forecast's and the payouts' dates into months |
| `currency` | e.g. `EUR` | keeps one currency |
| `from`, `to` | epoch ms, or `now`, `now-30d`, `now+12M`, `now/M`, `now+1M/M`, `now/d` | keeps rows with `from` ≤ time < `to`; `/M` and `/d` round to the start of that month or day |

| kind | one row per | |
|---|---|---|
| `revenue` | month × store × plan | payments spread over the period they cover |
| `cashflow` | month × store × plan | payments in the month they were made, less refunds |
| `forecast` | payment date × store × plan | what active subscriptions will pay, after discounts |
| `payouts` | payout date × store | estimated payouts, past and coming, plan `payout` |

Errors: `401` without the right token, `400` for an unknown parameter value, `502` with `{"error": "store <name>: …"}` when a store can't be read or holds something the bridge doesn't support yet.

## `GET /stores`

Needs the token. The configured store names, for a Grafana variable.

## `GET /health`

No token. `ok` while the server runs; it does not call Creem.
