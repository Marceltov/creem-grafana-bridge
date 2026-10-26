"""What active subscriptions will pay on their coming dates, and when the money is likely to reach the bank.

Payouts are an estimate: Creem's API has no payouts, so they follow Creem's published rules (payouts on the 1st and
15th, a minimum balance, money held for some days first, a payout fee)."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from .creem import StoreData
from .money import CENT, Fees, Payment, net, payments
from .series import Row, next_month, rows

MONTHS_PER = {"month": 1, "year": 12}


@dataclass(frozen=True)
class PayoutRules:
    minimum: Decimal
    hold_days: int
    fee_min: Decimal
    fee_percent: Decimal


def _at(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def add_months(t: datetime, n: int) -> datetime:
    """`t` n calendar months later; a day the month lacks becomes its last day, as card billing does."""
    y, m = divmod(t.month - 1 + n, 12)
    year, month = t.year + y, m + 1
    last = (datetime(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)).day
    return t.replace(year=year, month=month, day=min(t.day, last))


def _price(sub: dict, when: datetime) -> Decimal:
    price = Decimal(sub["product"]["price"]) / 100
    d = sub.get("discount")
    if not d:
        return price
    created = _at(sub["created_at"])
    runs = {
        "forever": True,
        "once": False,  # the first payment, already made
        "repeating": when < add_months(created, int(d.get("durationInMonths") or 0)),
    }.get(d.get("duration"), False)
    if not runs:
        return price
    off = price * Decimal(d["amount"]) / 100 if d["type"] == "percentage" else Decimal(d["amount"]) / 100
    return max(price - off, Decimal(0)).quantize(CENT, ROUND_HALF_UP)


def _vat_share(sub: dict, fallback: Decimal) -> Decimal:
    last = sub.get("last_transaction") or {}
    if last.get("amount_paid"):
        return Decimal(last["tax_amount"] or 0) / Decimal(last["amount_paid"])
    return fallback


def _store_vat_share(ps: list[Payment]) -> Decimal:
    paid = sum((p.paid for p in ps), Decimal(0))
    return sum((p.tax for p in ps), Decimal(0)) / paid if paid else Decimal(0)


def forecast(data: list[StoreData], now: datetime, basis: str, fees: Fees, tz: ZoneInfo, months: int = 12) -> list[Row]:
    until = add_months(now, months)
    sums: dict[tuple, Decimal] = defaultdict(Decimal)
    for store in data:
        # A subscription with no paid payment yet (a free start) takes the store's VAT share.
        fallback = _store_vat_share(payments(store))
        for sub in store.subscriptions:
            if sub["status"] not in ("active", "trialing") or sub.get("canceled_at") or not sub.get("next_transaction_date"):
                continue
            product = sub["product"]
            if product["recurring_interval"] not in MONTHS_PER:
                raise ValueError(f"store {store.store}: billing every {product['recurring_interval']!r} is not supported yet")
            step = MONTHS_PER[product["recurring_interval"]] * int(product.get("recurring_interval_count") or 1)
            first, share, k = _at(sub["next_transaction_date"]), _vat_share(sub, fallback), 0
            while (when := add_months(first, k * step)) <= until:
                k += 1
                if when < now:
                    continue
                gross = _price(sub, when)
                tax = (gross * share).quantize(CENT, ROUND_HALF_UP)
                p = Payment(store.store, product["name"], product["currency"], gross, tax, Decimal(0), when, when, when, None)
                day = when.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
                sums[(day, p.store, p.plan, p.currency)] += gross if basis == "gross" else net(p, fees)
    return rows(sums)


def _payout_days(start: datetime, end: datetime, tz: ZoneInfo):
    m = start.astimezone(tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while m <= end:
        yield m
        yield datetime(m.year, m.month, 15, tzinfo=tz)
        m = next_month(m)


def payouts(ps: list[Payment], expected: list[Row], rules: PayoutRules, fees: Fees, tz: ZoneInfo) -> list[Row]:
    """Estimated payouts per store and currency, from what was paid (net) and what is expected (net rows)."""
    hold = timedelta(days=rules.hold_days)
    events: dict[tuple, list] = defaultdict(list)
    for p in ps:
        events[(p.store, p.currency)].append((p.paid_at + hold, net(p, fees)))
    for r in expected:
        events[(r["store"], r["currency"])].append((datetime.fromisoformat(r["time"]) + hold, Decimal(r["amount"])))
    sums: dict[tuple, Decimal] = {}
    for (store, currency), evs in events.items():
        evs.sort(key=lambda e: e[0])
        balance, i = Decimal(0), 0
        for day in _payout_days(evs[0][0], evs[-1][0] + timedelta(days=31), tz):
            while i < len(evs) and evs[i][0] <= day:
                balance += evs[i][1]
                i += 1
            if balance >= rules.minimum:
                fee = max(rules.fee_min, (balance * rules.fee_percent / 100).quantize(CENT, ROUND_HALF_UP))
                sums[(day, store, "payout", currency)] = balance - fee
                balance = Decimal(0)
    return rows(sums)
