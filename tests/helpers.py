import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from creem_bridge.creem import StoreData
from creem_bridge.money import Fees, Payment

F = Fees(Decimal("3.9"), Decimal("0.40"))


def at(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def pay(paid, tax, refunded="0", start="2026-10-21T00:00Z", end="2026-11-21T00:00Z", paid_at=None,
        store="notefeed", plan="monthly", currency="EUR") -> Payment:
    return Payment(store, plan, currency, Decimal(paid), Decimal(tax), Decimal(refunded),
                   at(start), at(end), at(paid_at or start), None)


def live() -> StoreData:
    d = json.loads((Path(__file__).parent / "fixtures" / "notefeed.json").read_text())
    return StoreData("notefeed", d["transactions"], d["subscriptions"])
