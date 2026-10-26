# Grafana

Grafana reads the bridge with the [Infinity](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/) data source plugin. Install it with `GF_PLUGINS_PREINSTALL_SYNC=yesoreyeram-infinity-datasource@4.1.3`, or from Grafana's plugin catalogue.

## The data source

```yaml title="grafana/provisioning/datasources/revenue.yaml"
apiVersion: 1
datasources:
  - name: Revenue
    uid: revenue
    type: yesoreyeram-infinity-datasource
    access: proxy
    url: http://creem-bridge:8080
    jsonData:
      auth_method: bearerToken
      allowedHosts: [http://creem-bridge:8080]   # the token goes to the bridge and nowhere else
    secureJsonData:
      bearerToken: $BRIDGE_TOKEN                 # from Grafana's environment
```

## The ready-made dashboard

`examples/grafana/dashboards/revenue.json` (uid `revenue`) expects the data source above. It has:

- **Tiles:** revenue this month, cash in this month, expected in the next 30 days, 90 days and 12 months, the next payout.
- **Revenue per month** and **cashflow per month**, stacked by plan.
- **Expected payments per month**, by store, and **estimated payouts**.
- **Amounts** (net or gross) and **Store** at the top. The time range runs from 12 months back to 12 months ahead, so the past and the forecast share one axis.

It asks for euros (`currency=EUR`) and shows months in `Europe/Berlin`. For another currency or zone, change those in the JSON.

## Your own panels

A panel query is type **JSON**, parser **Backend**, source **URL**, with the URL relative to the data source:

```text
/series?kind=revenue&basis=net&by=plan&currency=EUR&from=${__from}&to=${__to}
```

Columns: `time` as timestamp, `amount` as number, and `plan` or `store` as string; format **Time series**. Add the transformation **Prepare time series → Multi-frame** so each plan or store becomes its own series, and set the display name to `${__field.labels.plan}`.

For a single number, use `by=total` with a fixed window (`from=now/M&to=now%2B1M/M` is this month) and a stat panel summing the values.

!!! note "One currency per query"

    Grafana adds up whatever rows it gets. The bridge never adds currencies together, but a panel that asks for every currency would. Ask for one with `currency=`.

All parameters are in the [HTTP API](api.md).
