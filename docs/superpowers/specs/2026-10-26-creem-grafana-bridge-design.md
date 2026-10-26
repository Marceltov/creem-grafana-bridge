# creem-grafana-bridge

2026-10-26 · project · draft for approval

## Why

Revenue and cashflow of the products sold through Creem should sit in Grafana next to everything else, as trends and
forecasts, and stay right as products are added. Each product has its own Creem store (its own API key); notefeed is
the first (notefeed/notefeed#233). Creem's dashboard shows one store at a time, no net figures and no forecast.

## Goals

- Per store, per plan (Creem product) and in total, by month:
  - **revenue**: what a payment pays for, spread over the period it covers (a yearly payment counts 1/12 per month, by days);
  - **cashflow**: payments when they are made, refunds when they are refunded.
- Each in two bases: **gross** (what customers paid, VAT included) and **net** (paid − VAT − Creem's fee). Net per
  payment is exact; Creem's fee is 3.9 % + 0.40 of the total including VAT, from the published formula.
- **Forecast**: the payments active subscriptions will make on their future dates, 12 months ahead, at what each will
  actually pay (price less its discount while the discount runs; a cancelled subscription stops at the end of its paid period).
- **Payout estimate**: when and how much reaches the bank, per store, from Creem's rules. Only an estimate: payouts are
  not in Creem's API.
- Trends as charts; Grafana's time picker decides the range.

## Non-goals

- Storing anything: Creem is the only copy. A refund or chargeback therefore corrects past months by itself.
- Converting currencies: every figure carries its currency; totals are per currency.
- Customer data: no names, e-mails or ids leave the bridge, only sums.
- Writing to Creem: the bridge only reads.
- Alerting (can come later on the same series).

## Anti-goals

- Numbers that look precise and are silently wrong (a product forgotten in the totals, a discount ignored, a refund
  double-counted). Every figure is tested against worked examples.
- A second place that has to be kept in sync with Creem.

## Approaches considered

1. **Prometheus exporter.** Fits the existing pipeline, but Prometheus cannot revise the past after a refund, has no
   future timestamps for a forecast curve, and keeps 400 days.
2. **Sync into a database, Grafana reads SQL.** Exact and revisable, but a sync and a database to run; a store's data
   would have to live apart from the products' databases.
3. **Grafana calls Creem directly** (Infinity plugin). Nothing new to run, but spreading, fees, forecast and payout
   rules would live untested in JSONata per panel, and multi-store charts need merging on every panel.
4. **A route inside notefeed.** Smallest for one product, but ties a generic need to one product's code.
5. **A small stateless bridge (chosen).** Fetches from Creem on request, does the arithmetic once in tested code,
   serves ready series; Grafana only draws. Generic over stores, so new products need configuration, not code.

## How (decided)

- Repository `marceltov/creem-grafana-bridge`, public, licence MIT (builder's call, matching a small generic tool).
- Runs on monitor-1 in infra-stacks (`creem-bridge/`), on the monitoring Docker network only, no published port.
  Grafana reads it with the Infinity data source plugin.
- Stores are configured by environment: `CREEM_STORES=notefeed` and per store `CREEM_KEY_<NAME>`; the keys live in
  infra-ansible's vault (Creem has no read-only keys; the bridge only calls read endpoints).
- A bearer token (`BRIDGE_TOKEN`, vault) between Grafana and the bridge, though the port is internal.
- A "Revenue" dashboard in its own Grafana folder in infra-stacks; only the owner uses Grafana.

## Creem facts the design rests on (live API, 2026-10-26)

- `GET /v1/transactions/search` (paged): `amount`, `amount_paid`, `tax_amount`, `discount_amount`, `refunded_amount`,
  `status` (`paid`, `refunded`, partial refunds possible), `period_start`/`period_end` (ms), `subscription`, `currency`, `created_at`.
- `GET /v1/subscriptions/search` (paged): `status`, `product` (id, name, price, `recurring_interval`,
  `tax_mode` inclusive), `next_transaction_date`, `current_period_end_date`, `canceled_at`, `discount` (`type`
  percentage/fixed, `amount`, `duration` once/repeating/forever, `durationInMonths`).
- No fee per transaction and no payouts in the API (`/v1/payouts` answers 500). Payout rules (docs.creem.io, Finance →
  Payouts): on the 1st and 15th, balance ≥ 50, new funds held 7–12 days, fee 7 or 1 % of the payout, whichever is higher.

## Interface (shape decided, details builder's)

- `GET /series?kind=revenue|cashflow|forecast|payouts&basis=gross|net[&store=…]` → JSON rows
  `{ time, store, plan, currency, amount }`, amounts in major units, one row per store × plan × month (forecast and
  payouts: per date). Infinity turns rows into time series grouped by store or plan.
- `GET /health` for the container check.
- Responses cached a few minutes; Creem is asked at most once per cache period per store.

## Dashboard

- Top row, tiles with a sparkline: net revenue this month, cash in the last 30 days, expected in the next 30 / 90 / 365
  days, next estimated payout (date and amount).
- Revenue by month, stacked by plan, gross and net side by side; cashflow by month the same way.
- Forecast: expected payments over the next 12 months, by store.
- Payouts: estimated payouts, past and coming.
- A store variable (all by default); colours per store and plan from the palette the other dashboards use.

## Left to the builder (my calls, to check)

- TypeScript on Node 24, `node:http` and `fetch`, vitest; image on ghcr.io via GitHub Actions, like noticebox.
- Fee and payout rules as configuration with today's values as defaults (`FEE_PERCENT=3.9`, `FEE_FIXED=0.40`,
  `PAYOUT_MIN=50`, `PAYOUT_HOLD_DAYS=12`, `PAYOUT_FEE_MIN=7`, `PAYOUT_FEE_PERCENT=1`), since Creem changes prices.
- Creem's fee on a refunded payment counts as kept (not returned); configurable if the first refund statement says otherwise.
- Net forecast uses the VAT share of each subscription's last payment (VAT depends on the customer's country).
- Months in Europe/Berlin (`TZ`, configurable), so a month matches the bank statement.
- A refund carries no date of its own in the transaction. If Creem's API has none elsewhere, it counts in the month of
  the payment it refunds; the builder checks the API first and records which it is.
- A 100 % discount (operator licences) yields 0, so such subscriptions add nothing to forecast or revenue.
- Check once against the first real payout's reverse invoice; record the result in the repo's README.
