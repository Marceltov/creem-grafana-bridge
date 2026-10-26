# creem-grafana-bridge

Revenue, cashflow, a forecast and estimated payouts of one or more [Creem](https://creem.io) stores, as JSON series
for Grafana. Gross and net (after VAT and Creem's fee), per plan, per store or in total. It stores nothing: every
answer is computed from Creem's own records, so a refund corrects past months by itself.

**Documentation: <https://marceltov.github.io/creem-grafana-bridge/>**

```yaml
creem-bridge:
  image: ghcr.io/marceltov/creem-grafana-bridge:0.1.0
  environment:
    CREEM_STORES: shop
    CREEM_KEY_SHOP: ${CREEM_KEY_SHOP}
    BRIDGE_TOKEN: ${BRIDGE_TOKEN}
```

Then point Grafana's Infinity data source at it: see [Quick start](https://marceltov.github.io/creem-grafana-bridge/getting-started/)
and the ready-made dashboard in [`examples/grafana/`](examples/grafana/).

Python standard library only; MIT licence.
