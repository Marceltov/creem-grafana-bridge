"""Payments as Creem records them, and what each is worth gross (VAT included) and net (after VAT and Creem's fee)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from .creem import StoreData

CENT = Decimal("0.01")
PAID = {"paid", "refunded", "partially_refunded"}
# Statuses of payments that did not happen. Any other status is an error, not a payment left out of every total.
NOT_PAID = {"pending", "failed", "void", "canceled", "cancelled", "expired", "uncollectible", "open", "draft"}
# A payment Creem cannot tie to a subscription: a one-time product.
ONE_TIME = "one-time"


@dataclass(frozen=True)
class Fees:
    percent: Decimal
    fixed: Decimal


@dataclass(frozen=True)
class Payment:
    """One payment, in major units. Creem keeps no refund date, so `refunded_at` stays None (see the README)."""

    store: str
    plan: str
    currency: str
    paid: Decimal
    tax: Decimal
    refunded: Decimal
    period_start: datetime
    period_end: datetime
    paid_at: datetime
    refunded_at: datetime | None


def _major(cents) -> Decimal:
    return Decimal(cents or 0) / 100


def _time(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, UTC)


def payments(data: StoreData) -> list[Payment]:
    plans = {s["id"]: s["product"]["name"] for s in data.subscriptions}
    out = []
    for t in data.transactions:
        if t["status"] in NOT_PAID:
            continue
        if t["status"] not in PAID:
            raise ValueError(f"store {data.store}: payment status {t['status']!r} is not known yet")
        paid_at = _time(t["created_at"])
        out.append(Payment(
            store=data.store,
            plan=plans.get(t.get("subscription") or "", ONE_TIME),
            currency=t["currency"],
            paid=_major(t["amount_paid"]),
            tax=_major(t["tax_amount"]),
            refunded=_major(t.get("refunded_amount")),
            period_start=_time(t["period_start"]) if t.get("period_start") else paid_at,
            period_end=_time(t["period_end"]) if t.get("period_end") else paid_at,
            paid_at=paid_at,
            refunded_at=None,
        ))
    return out


def fee(p: Payment, fees: Fees) -> Decimal:
    """Creem's platform fee on the total including VAT, rounded down to cents as in Creem's worked example; it is not
    returned on a refund."""
    if not p.paid:
        return Decimal(0)
    return (p.paid * fees.percent / 100 + fees.fixed).quantize(CENT, ROUND_DOWN)


def kept(p: Payment) -> Decimal:
    """Gross: what the customer paid and was not refunded, VAT included."""
    return p.paid - p.refunded


def net(p: Payment, fees: Fees) -> Decimal:
    """What is kept after VAT (in proportion to what is kept) and Creem's fee."""
    if not p.paid:
        return Decimal(0)
    tax = (p.tax * kept(p) / p.paid).quantize(CENT, ROUND_HALF_UP)
    return kept(p) - tax - fee(p, fees)
