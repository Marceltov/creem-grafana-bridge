# Contributing

```bash
uv run pytest -q
CREEM_STORES=shop CREEM_KEY_SHOP=… BRIDGE_TOKEN=t uv run python -m creem_bridge
uvx --with mkdocs-material==9.7.7 --with 'mkdocs<2' mkdocs serve   # this site
```

The code is in `src/creem_bridge/`: `creem.py` reads a store, `money.py` turns payments into gross and net, `series.py` makes revenue and cashflow, `forecast.py` the forecast and payouts, `server.py` the HTTP side. Tests use a store recorded from Creem's live API (`tests/fixtures/`, customer fields removed).

The design and its reasoning are in `docs/superpowers/`. Changes to how a number is computed come with a test that shows the number.

A tag `v*` builds and publishes the image to `ghcr.io/marceltov/creem-grafana-bridge`.
