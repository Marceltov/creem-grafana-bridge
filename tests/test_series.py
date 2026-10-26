from decimal import Decimal
from zoneinfo import ZoneInfo

from creem_bridge.series import cashflow, revenue
from helpers import F, pay

BERLIN = ZoneInfo("Europe/Berlin")


def test_yearly_spreads_over_thirteen_months_and_adds_up():
    p = pay(paid="19.90", tax="3.18", start="2026-10-21T15:51Z", end="2027-10-21T15:51Z", plan="yearly")
    rows = revenue([p], "gross", F, BERLIN)
    assert len(rows) == 13
    assert sum(r["amount"] for r in rows) == Decimal("19.90")
    assert rows[0]["time"] == "2026-10-01T00:00:00+02:00"
    assert rows[1]["time"] == "2026-11-01T00:00:00+01:00"
    # November is 30 of 365 days.
    assert rows[1]["amount"] == Decimal("1.64")


def test_net_revenue_adds_up_to_net():
    p = pay(paid="19.90", tax="3.18", start="2026-10-21T15:51Z", end="2027-10-21T15:51Z")
    assert sum(r["amount"] for r in revenue([p], "net", F, BERLIN)) == Decimal("15.55")


def test_month_boundary_is_berlin():
    # 23:30 UTC on 31 October is already 1 November in Berlin.
    rows = cashflow([pay(paid="1.99", tax="0.32", paid_at="2026-10-31T23:30Z")], "gross", F, BERLIN)
    assert rows[0]["time"] == "2026-11-01T00:00:00+01:00"


def test_cashflow_net_per_store_plan_currency():
    ps = [
        pay(paid="1.99", tax="0.32", paid_at="2026-10-05T10:00Z"),
        pay(paid="1.99", tax="0.32", paid_at="2026-10-06T10:00Z"),
        pay(paid="19.90", tax="3.18", paid_at="2026-10-06T10:00Z", plan="yearly"),
        pay(paid="5.00", tax="0", paid_at="2026-10-06T10:00Z", store="other", currency="USD"),
    ]
    rows = cashflow(ps, "net", F, BERLIN)
    got = {(r["store"], r["plan"], r["currency"]): r["amount"] for r in rows}
    assert got == {
        ("notefeed", "monthly", "EUR"): Decimal("2.40"),   # 2 × (1.99 − 0.32 − 0.47)
        ("notefeed", "yearly", "EUR"): Decimal("15.55"),   # 19.90 − 3.18 − 1.17
        ("other", "monthly", "USD"): Decimal("4.41"),  # 5.00 − 0.59 (0.195 + 0.40, rounded down)
    }
    assert set(rows[0]) == {"time", "store", "plan", "currency", "amount"}


def test_refunded_payment_leaves_nothing_gross():
    assert cashflow([pay(paid="1.99", tax="0.32", refunded="1.99")], "gross", F, BERLIN) == []
