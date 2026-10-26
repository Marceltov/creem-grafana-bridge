# creem-grafana-bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A stateless service that reads one or more Creem stores and serves revenue, cashflow, forecast and payout
series to Grafana, deployed on monitor-1 with a "Revenue" dashboard.

**Architecture:** `creem.py` fetches all pages from Creem; `money.py` turns transactions into `Payment`s with exact
gross/net amounts; `series.py` and `forecast.py` compute rows; `server.py` serves them as JSON behind a bearer token,
cached. Grafana reads it with the Infinity data source.

**Tech Stack:** Python 3.13 standard library (`http.server`, `urllib.request`, `json`, `decimal`, `zoneinfo`,
`datetime`), pytest, uv; Docker image on ghcr.io via GitHub Actions; Grafana 13.2.3 with the Infinity plugin.

**Spec:** `docs/superpowers/specs/2026-10-26-creem-grafana-bridge-design.md`

## Global Constraints

- No runtime dependencies outside the standard library; pytest only as a dev dependency (`uv add --dev pytest`).
- Money is `Decimal` everywhere; it becomes a JSON number only at the HTTP boundary, rounded to 2 places.
- Months are calendar months in `TZ` (default `Europe/Berlin`); a row's `time` is the month's first day 00:00 in that
  zone, as ISO 8601 with offset.
- Rows are exactly `{"time", "store", "plan", "currency", "amount"}`; no customer, e-mail, order or subscription id ever
  appears in a response.
- Different currencies are never added together.
- The bridge only sends GET requests to Creem.
- Defaults: `FEE_PERCENT=3.9`, `FEE_FIXED=0.40`, `PAYOUT_MIN=50`, `PAYOUT_HOLD_DAYS=12`, `PAYOUT_FEE_MIN=7`,
  `PAYOUT_FEE_PERCENT=1`, `CACHE_SECONDS=300`, `PORT=8080`, `CREEM_API_URL=https://api.creem.io`, horizon 12 months.
- Commit messages end with the Co-Authored-By and Claude-Session lines of the session.
- Nothing is pushed, published, tagged or deployed without the owner's go (CLAUDE.md rules carry over).

## Review Focus

1. A partial refund (`refunded_amount` < `amount_paid`): gross and net drop proportionally, VAT included — test in Task 2.
2. A payment just before midnight UTC on the last day of a month lands in the next month in Europe/Berlin — test in Task 3.
3. A store whose key is wrong or Creem is down: the whole response is an error naming the store, never totals that
   silently leave a store out — test in Task 5.
4. More than one page of transactions or subscriptions: every page is read — test in Task 1.
5. A store with no sales yet: empty rows and 200, not an error — test in Task 5.

---

### Task 1: Repository and Creem client

**Files:**
- Create: `pyproject.toml`, `.python-version` (3.13), `src/creem_bridge/__init__.py`, `src/creem_bridge/creem.py`
- Test: `tests/test_creem.py`

**Interfaces:**
- Produces: `fetch_all(base_url: str, key: str, path: str, get=None) -> list[dict]` (follows
  `pagination.next_page`, `page_size=100`, header `x-api-key`; `get(url, headers) -> dict` is injectable, default uses
  `urllib.request`); `class CreemError(Exception)` raised with the HTTP status on any non-200;
  `@dataclass StoreData(store: str, transactions: list[dict], subscriptions: list[dict])`;
  `load_store(store: str, key: str, base_url: str, get=None) -> StoreData` (paths `/v1/transactions/search`,
  `/v1/subscriptions/search`).

- [ ] **Step 1: Check refund dates in Creem's API.** With the live key in `~/.config/notefeed/creem-live.env`, GET
  `/v1/transactions/search` and look for a refund date or a refunds endpoint (`/v1/refunds/search`, a transaction of
  type `refund`). Record the answer as a ledger ruling; Task 2's `refunded_at` follows it (spec: if none, a refund
  counts in the month of the payment).
- [ ] **Step 2: Write the failing tests**

```python
def test_fetch_all_reads_every_page():
    pages = {1: {"items": [{"id": "a"}], "pagination": {"next_page": 2}},
             2: {"items": [{"id": "b"}], "pagination": {"next_page": None}}}
    seen = []
    def get(url, headers):
        seen.append((url, headers["x-api-key"]))
        return pages[int(parse_qs(urlparse(url).query)["page_number"][0])]
    assert [i["id"] for i in fetch_all("https://x", "k", "/v1/transactions/search", get)] == ["a", "b"]
    assert all(k == "k" for _, k in seen)

def test_non_200_raises_creem_error(): ...  # get raises CreemError(401) → load_store propagates it
```

- [ ] **Step 3: Run** `uv run pytest -q tests/test_creem.py` — Expected: FAIL (module missing).
- [ ] **Step 4: Implement** `creem.py` per Interfaces.
- [ ] **Step 5: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 6: Commit** `git add -A && git commit -m "Creem client: every page of a store's transactions and subscriptions"`

### Task 2: Payments, fees and net

**Files:** Create `src/creem_bridge/money.py`; Test `tests/test_money.py`

**Interfaces:**
- Consumes: `StoreData` (Task 1).
- Produces: `@dataclass(frozen=True) Fees(percent: Decimal, fixed: Decimal)`;
  `@dataclass(frozen=True) Payment(store, plan, currency, paid: Decimal, tax: Decimal, refunded: Decimal,
  period_start: datetime, period_end: datetime, paid_at: datetime, refunded_at: datetime | None)` (major units, aware
  UTC datetimes); `payments(data: StoreData) -> list[Payment]` (plan = the subscription's product name, looked up by
  `transaction.subscription`; only `status` in `paid`/`refunded`/`partially_refunded`);
  `fee(p: Payment, fees: Fees) -> Decimal`; `kept(p: Payment) -> Decimal` (gross after refunds);
  `net(p: Payment, fees: Fees) -> Decimal`.

Rules: fee = `percent`% of `paid` + `fixed`, rounded DOWN to cents (Creem's worked example: 24.00 → 1.33), 0 when
`paid` is 0, kept on refund. `kept = paid − refunded`. `net = kept − tax × kept/paid − fee` (0 when paid is 0).

- [ ] **Step 1: Write the failing tests**

```python
F = Fees(Decimal("3.9"), Decimal("0.40"))
def test_creem_worked_example():   # docs: 24.00 incl. 4.00 VAT → fee 1.33, net 18.67
    p = pay(paid="24.00", tax="4.00"); assert fee(p, F) == Decimal("1.33"); assert net(p, F) == Decimal("18.67")
def test_full_refund_keeps_the_fee():  # notefeed's go-live test: 1.99, VAT 0.32, refunded
    p = pay(paid="1.99", tax="0.32", refunded="1.99"); assert kept(p) == 0; assert net(p, F) == Decimal("-0.47")
def test_partial_refund_is_proportional():
    p = pay(paid="24.00", tax="4.00", refunded="12.00"); assert kept(p) == Decimal("12.00"); assert net(p, F) == Decimal("8.67")
def test_free_payment_is_zero():   # 100 % discount: amount_paid 0
    p = pay(paid="0", tax="0"); assert fee(p, F) == 0 and net(p, F) == 0
def test_payments_from_creem_json(): ...  # the two live transactions (cents → major units, ms → UTC, plan names
                                          # "notefeed license, yearly"/"…monthly"), no customer fields on Payment
```

- [ ] **Step 2: Run** `uv run pytest -q tests/test_money.py` — Expected: FAIL.
- [ ] **Step 3: Implement** `money.py`.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** "Payments with exact gross and net: Creem's fee rounded down, kept on refunds"

### Task 3: Revenue and cashflow by month

**Files:** Create `src/creem_bridge/series.py`; Test `tests/test_series.py`

**Interfaces:**
- Consumes: `Payment`, `Fees`, `kept`, `net` (Task 2).
- Produces: `Row = dict` with the five keys; `revenue(ps: list[Payment], basis: str, fees: Fees, tz: ZoneInfo) -> list[Row]`;
  `cashflow(ps, basis, fees, tz) -> list[Row]`; `basis` is `"gross"` (uses `kept`) or `"net"`. Rows sorted by time,
  store, plan; amounts `Decimal` quantized to cents; rows with amount 0 omitted.

Revenue spreads each payment's amount over `period_start`…`period_end` by days per local month; per payment, the
cents are distributed by largest remainder so the months add up exactly to the payment. Cashflow puts `kept`/`net` in
the month of `paid_at` (refunds per Task 1's ruling).

- [ ] **Step 1: Write the failing tests**

```python
def test_yearly_spreads_over_thirteen_months_and_adds_up():
    p = pay(paid="19.90", tax="3.18", start="2026-10-21T15:51Z", end="2027-10-21T15:51Z")
    rows = revenue([p], "gross", F, BERLIN)
    assert len(rows) == 13 and sum(r["amount"] for r in rows) == Decimal("19.90")
    assert rows[0]["time"] == "2026-10-01T00:00:00+02:00"
def test_month_boundary_is_berlin():   # 2026-10-31T23:30Z is 1 November in Berlin
    assert cashflow([pay(paid="1.99", tax="0.32", paid_at="2026-10-31T23:30Z")], "gross", F, BERLIN)[0]["time"] == "2026-11-01T00:00:00+01:00"
def test_cashflow_net_sums_per_store_plan_currency(): ...  # two stores, two plans, EUR and USD stay apart
```

- [ ] **Step 2–4:** run (FAIL), implement, run `uv run pytest -q` (PASS).
- [ ] **Step 5: Commit** "Revenue spread by days per Berlin month, cashflow by payment month"

### Task 4: Forecast and payout estimate

**Files:** Create `src/creem_bridge/forecast.py`; Test `tests/test_forecast.py`

**Interfaces:**
- Consumes: `StoreData`, `Payment`, `Fees`, `net`, `Row`.
- Produces: `forecast(data: list[StoreData], now: datetime, basis: str, fees: Fees, months: int = 12) -> list[Row]`
  (one row per expected payment date, `time` = that date's local midnight);
  `@dataclass(frozen=True) PayoutRules(minimum, hold_days, fee_min, fee_percent)`;
  `payouts(ps: list[Payment], expected: list[Row], rules: PayoutRules, fees: Fees, tz) -> list[Row]` (plan `"payout"`).

Forecast: subscriptions with `status` `active` or `trialing` and no `canceled_at`; from `next_transaction_date`,
repeat every `recurring_interval_count` × `recurring_interval` until `now + months`. Amount = product price less the
discount while it runs (`once`: first payment only, already past; `repeating`: until `created_at + durationInMonths`;
`forever`), percentage rounded half-up to cents. Net uses the VAT share of the subscription's last paid transaction.
Payouts: each net amount becomes available `hold_days` after it is paid; on every 1st and 15th, if the available
balance ≥ `minimum`, it is paid out less `max(fee_min, fee_percent % of it)`; past payouts from `ps`, future ones also
from `expected` (net).

- [ ] **Step 1: Write the failing tests**

```python
def test_monthly_without_discount_twelve_payments():  # next 2026-11-21, 1.99 → 12 rows of 1.99
def test_operator_licence_with_100_percent_forecasts_nothing():  # the live yearly subscription → []
def test_repeating_discount_ends():   # 20 % for 3 months on 19.90 monthly from 2026-10-21 → 15.92 ×2 (Nov, Dec), then 19.90
def test_cancelled_subscription_forecasts_nothing():
def test_payout_waits_for_minimum_and_hold():   # net 60.00 paid 2026-10-10 → payout 2026-11-01 of 53.00; net 40.00 → none
def test_payout_fee_is_one_percent_above_700(): # 1000.00 available → 990.00
```

- [ ] **Step 2–4:** run (FAIL), implement, run `uv run pytest -q` (PASS).
- [ ] **Step 5: Commit** "Forecast from active subscriptions after discounts; payout estimate from Creem's rules"

### Task 5: HTTP server and configuration

**Files:** Create `src/creem_bridge/config.py`, `src/creem_bridge/server.py`, `src/creem_bridge/__main__.py`;
Test `tests/test_server.py`

**Interfaces:**
- Consumes: `load_store`, `CreemError`, `payments`, `revenue`, `cashflow`, `forecast`, `payouts`.
- Produces: `@dataclass Config` with `from_env(env: Mapping[str, str]) -> Config` (`CREEM_STORES` comma-separated,
  key `CREEM_KEY_<NAME upper>`, missing key → `ValueError` naming the variable; `BRIDGE_TOKEN` required; the defaults of
  Global Constraints); `make_server(cfg: Config, load=load_store, now=lambda: datetime.now(UTC)) -> ThreadingHTTPServer`;
  `python -m creem_bridge` serves on `PORT`.

`GET /health` → 200 `ok` (no token). `GET /series?kind=revenue|cashflow|forecast|payouts&basis=gross|net[&store=a,b]`
with `Authorization: Bearer <BRIDGE_TOKEN>` → 200 JSON list of rows (amounts as numbers); wrong token 401; unknown
kind/basis/store 400; any store failing to load → 502 `{"error": "store <name>: Creem answered <status>"}`. Each store's
`StoreData` cached `CACHE_SECONDS`. Logs one line per request without the token or keys.

- [ ] **Step 1: Write the failing tests** (server on port 0, fake `load`)

```python
def test_series_needs_the_token(): ...      # no/wrong header → 401
def test_revenue_rows_have_exactly_five_keys(): ...
def test_one_failing_store_fails_the_request(): ...   # load raises CreemError(401) for "b" → 502 naming "b"
def test_store_without_sales_is_empty_not_an_error(): ...  # → 200, []
def test_cache_asks_creem_once_per_period(): ...      # two requests → load called once per store
def test_missing_key_names_the_variable(): ...        # Config.from_env({"CREEM_STORES": "notefeed", "BRIDGE_TOKEN": "t"})
```

- [ ] **Step 2–4:** run (FAIL), implement, run `uv run pytest -q` (PASS).
- [ ] **Step 5: Smoke against live Creem:** `CREEM_STORES=notefeed CREEM_KEY_NOTEFEED=$CREEM_API_KEY BRIDGE_TOKEN=t uv run python -m creem_bridge`
  and `curl -H 'Authorization: Bearer t' 'localhost:8080/series?kind=cashflow&basis=net'` — Expected: one October
  row for the monthly plan, amount -0.47; the yearly operator licence adds nothing.
- [ ] **Step 6: Commit** "HTTP: /series and /health behind a bearer token, cached per store"

### Task 6: Image, CI, README

**Files:** Create `Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml`, `README.md`, `LICENSE` (MIT)

- `Dockerfile`: `python:3.13-slim` pinned by digest, non-root user, copies `src/`, `CMD ["python", "-m", "creem_bridge"]`,
  `HEALTHCHECK` via `python -c` urllib on `/health`.
- `ci.yml`: on push/PR run `uv run pytest -q`; on tag `v*` build and push `ghcr.io/marceltov/creem-grafana-bridge:<version>`.
- README: what it serves, configuration table (every variable and default), Grafana Infinity setup (data source with
  bearer token, a panel query example), the fee and payout assumptions and that payouts are estimates.

- [ ] **Step 1:** `docker build -t creem-bridge:dev .` and run it with the smoke env from Task 5 — Expected: `/health` 200, same rows.
- [ ] **Step 2: Commit** "Image, CI and README"
- [ ] **Step 3 (owner's go):** create the public repo `marceltov/creem-grafana-bridge`, push, CI green, tag `v0.1.0`, image published.

### Task 7: infra-stacks: service, plugin, data source, dashboard

**Files:** Modify `monitoring/compose.yaml`, `monitoring/grafana/provisioning/datasources/datasources.yaml`;
Create `monitoring/grafana/dashboards/revenue/revenue.json`

- Service `creem-bridge` in `monitoring/compose.yaml` (on the `monitoring` network, no ports, image pinned by version
  and digest, env `CREEM_STORES`, `CREEM_KEY_NOTEFEED`, `BRIDGE_TOKEN` from `.env`). Ruling against the spec's
  `creem-bridge/` folder: it lives with Grafana, its only client, so no new folder, env file or recreate check.
- Grafana: `GF_PLUGINS_PREINSTALL_SYNC: yesoreyeram-infinity-datasource@<latest 3.x, looked up on grafana.com>`;
  `BRIDGE_TOKEN` passed to Grafana.
- Data source `Revenue` (uid `revenue`, type `yesoreyeram-infinity-datasource`, `url: http://creem-bridge:8080`,
  `allowedHosts: [http://creem-bridge:8080]`, bearer token from `$BRIDGE_TOKEN` in `secureJsonData`).
- Dashboard "Revenue" (uid `revenue`) per the spec's Dashboard section: store variable; tiles; revenue and cashflow
  stacked by plan, gross and net; forecast; payouts. Palette and conventions as the other dashboards (blue, orange,
  aqua … in fixed order; status colours reserved).

- [ ] **Step 1:** local Grafana 13.2.3 + the bridge image with the live key (as for the earlier screenshots); every
  panel shows data or a deliberate "no data" text; screenshot at 1600 px wide, both themes looked at.
- [ ] **Step 2: Commit** on branch `revenue-dashboard` "Revenue: Creem stores through creem-grafana-bridge"

### Task 8: infra-ansible: secrets and deploy

**Files:** Modify `inventory/group_vars/all/vault.yml` (via `ansible-vault edit`: `vault_creem_key_notefeed`,
`vault_creem_bridge_token` = 32 random bytes hex), `inventory/group_vars/all/vars.yml` (`creem_stores: [notefeed]`),
`roles/stacks/templates/monitoring.env.j2` (`CREEM_STORES`, `CREEM_KEY_NOTEFEED`, `BRIDGE_TOKEN`).

- [ ] **Step 1:** `ansible-playbook site.yml --check --diff` on a branch — Expected: only monitoring's .env (no diff
  printed) and the checkout change.
- [ ] **Step 2: Commit** on branch `creem-bridge` "Creem bridge: the notefeed store's key and the bridge token"
- [ ] **Step 3 (owner's "merge"):** merge infra-stacks then infra-ansible PRs, run `ansible-playbook site.yml`;
  Expected: `creem-bridge` healthy, the Revenue dashboard renders with the live store.
