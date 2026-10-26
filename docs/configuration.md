# Configuration

Everything is set through the environment. The bridge refuses to start, with a message naming the variable, when a required one is missing.

| Variable | Default | |
|---|---|---|
| `CREEM_STORES` | (required) | the store names, comma-separated, e.g. `shop,other` |
| `CREEM_KEY_<NAME>` | (required) | each store's API key: `CREEM_KEY_SHOP`; a `-` in the name becomes `_` |
| `BRIDGE_TOKEN` | (required) | the bearer token Grafana sends |
| `TZ` | `Europe/Berlin` | the zone months and dates are counted in |
| `FEE_PERCENT`, `FEE_FIXED` | `3.9`, `0.40` | Creem's fee per payment, on the total including VAT |
| `PAYOUT_MIN` | `50` | the balance a payout needs |
| `PAYOUT_HOLD_DAYS` | `12` | days new money is held before it can be paid out |
| `PAYOUT_FEE_MIN`, `PAYOUT_FEE_PERCENT` | `7`, `1` | the payout fee: the higher of the two |
| `FORECAST_MONTHS` | `12` | how far the forecast reaches |
| `CACHE_SECONDS` | `300` | how long a store's data is reused before Creem is asked again |
| `PORT` | `8080` | |
| `CREEM_API_URL` | `https://api.creem.io` | `https://test-api.creem.io` for test mode |

The fee and payout defaults are Creem's published terms as of October 2026 ([Fees and payouts](https://docs.creem.io/merchant-of-record/finance/payouts)). If Creem changes them, change the settings; no new version is needed.
