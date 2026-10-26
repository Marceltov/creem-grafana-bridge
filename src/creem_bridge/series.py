"""Revenue (a payment spread over the period it pays for) and cashflow (a payment in the month it was made), by month."""

from collections import defaultdict
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from zoneinfo import ZoneInfo

from .money import CENT, Fees, Payment, kept, net

Row = dict


def amount(p: Payment, basis: str, fees: Fees) -> Decimal:
    if basis == "gross":
        return kept(p)
    if basis == "net":
        return net(p, fees)
    raise ValueError(f"unknown basis {basis!r}")


def month_start(t: datetime, tz: ZoneInfo) -> datetime:
    return t.astimezone(tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month(m: datetime) -> datetime:
    # Built anew in the zone, so the offset is the new month's (summer and winter time differ).
    return datetime(m.year + m.month // 12, m.month % 12 + 1, 1, tzinfo=m.tzinfo)


def spread(total: Decimal, weights: list[float]) -> list[Decimal]:
    """`total` in cents over `weights`, rounded down, the leftover cents to the largest remainders: the parts add up exactly."""
    cents = int(total / CENT)
    sign, cents = (-1 if cents < 0 else 1), abs(cents)
    whole = sum(weights)
    exact = [cents * w / whole for w in weights]
    parts = [int(e) for e in exact]
    for i in sorted(range(len(exact)), key=lambda i: exact[i] - parts[i], reverse=True)[: cents - sum(parts)]:
        parts[i] += 1
    return [sign * Decimal(c) * CENT for c in parts]


def rows(sums: dict[tuple, Decimal]) -> list[Row]:
    return [
        {"time": t.isoformat(), "store": s, "plan": p, "currency": c, "amount": a.quantize(CENT, ROUND_DOWN)}
        for (t, s, p, c), a in sorted(sums.items())
        if a
    ]


def revenue(ps: list[Payment], basis: str, fees: Fees, tz: ZoneInfo) -> list[Row]:
    sums: dict[tuple, Decimal] = defaultdict(Decimal)
    for p in ps:
        total = amount(p, basis, fees)
        start, end = p.period_start, max(p.period_end, p.period_start)
        months, weights = [], []
        m = month_start(start, tz)
        while m < end or not months:
            n = next_month(m)
            months.append(m)
            weights.append(max((min(n, end) - max(m, start)).total_seconds(), 0.0))
            m = n
        if not sum(weights):  # no period: all of it in the month it was paid
            weights = [1.0] + [0.0] * (len(months) - 1)
        for m, part in zip(months, spread(total, weights)):
            sums[(m, p.store, p.plan, p.currency)] += part
    return rows(sums)


def cashflow(ps: list[Payment], basis: str, fees: Fees, tz: ZoneInfo) -> list[Row]:
    sums: dict[tuple, Decimal] = defaultdict(Decimal)
    for p in ps:
        # Creem keeps no refund date: a refund counts in the month of its payment.
        sums[(month_start(p.paid_at, tz), p.store, p.plan, p.currency)] += amount(p, basis, fees)
    return rows(sums)
