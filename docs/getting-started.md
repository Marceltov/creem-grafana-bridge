# Quick start

You need a Creem API key for each store (Creem dashboard → Developers → API keys) and a Grafana you can install a plugin in. The bridge only sends GET requests to Creem, but Creem has no read-only keys: treat the key as the secret it is.

## 1. Run the bridge next to Grafana

The bridge needs no port of its own: put it on the same Docker network as Grafana, which is its only client.

```yaml title="compose.yaml"
services:
  creem-bridge:
    image: ghcr.io/marceltov/creem-grafana-bridge:0.1.0
    restart: unless-stopped
    environment:
      CREEM_STORES: shop                # one name per store, comma-separated
      CREEM_KEY_SHOP: ${CREEM_KEY_SHOP} # each store's API key: CREEM_KEY_<NAME>
      BRIDGE_TOKEN: ${BRIDGE_TOKEN}     # what Grafana sends; e.g. openssl rand -hex 32

  grafana:
    image: grafana/grafana:13.2.3
    environment:
      GF_PLUGINS_PREINSTALL_SYNC: yesoreyeram-infinity-datasource@4.1.3
      BRIDGE_TOKEN: ${BRIDGE_TOKEN}
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
```

Every setting, with its default, is under [Configuration](configuration.md).

## 2. Check it answers

```bash
docker compose exec grafana wget -qO- \
  --header "Authorization: Bearer $BRIDGE_TOKEN" \
  "http://creem-bridge:8080/series?kind=cashflow&basis=net"
```

A list of rows (`time`, `store`, `plan`, `currency`, `amount`) means it reads your store. A `502` names the store it couldn't read and why, for example `store shop: Creem answered 401` for a wrong key.

## 3. Add the data source and the dashboard

Copy `examples/grafana/` from the repository into `./grafana/`: it provisions the data source with the token and the ready-made Revenue dashboard. [Grafana](grafana.md) explains both, and how to build your own panels.

!!! tip "Test mode"

    Set `CREEM_API_URL=https://test-api.creem.io` and use a test-mode key to try it against Creem's sandbox.
