---
hide:
  - toc
---

<div class="cb-hero" markdown>

# Your Creem stores' revenue, in Grafana

<p class="cb-hero__lead">creem-grafana-bridge reads the payments and subscriptions of one or more <a href="https://creem.io">Creem</a> stores and hands Grafana ready-made series: revenue per month, cashflow, what the active subscriptions will pay, and when the money is likely to reach your bank. Before and after VAT and Creem's fee.</p>

[Set it up](getting-started.md){ .md-button .md-button--primary } [Connect Grafana](grafana.md){ .md-button }

</div>

![The Revenue dashboard with two made-up stores](images/dashboard-light.png#only-light)
![The Revenue dashboard with two made-up stores](images/dashboard-dark.png#only-dark)

<small>The example dashboard (`examples/grafana/dashboards/revenue.json`) with two made-up stores.</small>

## What it does

- **Revenue and cashflow, per month.** Revenue spreads each payment over the period it pays for, so a yearly licence counts about 1/12 in each month. Cashflow puts it in the month it was paid.
- **Gross and net.** Gross is what customers paid, VAT included. Net is after VAT and Creem's fee, exact to the cent.
- **A forecast that holds with three customers.** It doesn't fit a curve: it lists what each active subscription will pay on its coming dates, after its discount, if nobody cancels.
- **Estimated payouts.** When and how much reaches your bank, from Creem's payout rules: Creem's API has no payouts.
- **Several stores.** One key per store; every series can be shown per plan, per store or in total.
- **Stores nothing.** Every answer is computed from Creem's own records (cached a few minutes). A refund corrects past months by itself, and there is no database to keep in sync.
- **Never silently wrong.** If a store can't be read, or holds something the bridge doesn't understand yet, the answer is an error naming the store, not totals that quietly leave it out.

```mermaid
flowchart LR
  creem1[Creem store A] -- GET, API key --> bridge[creem-grafana-bridge]
  creem2[Creem store B] -- GET, API key --> bridge
  bridge -- JSON series, bearer token --> grafana[Grafana + Infinity plugin]
```

It is a small Python service using only the standard library, published as a container image: `ghcr.io/marceltov/creem-grafana-bridge`.
