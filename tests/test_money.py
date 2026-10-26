from dataclasses import fields
from decimal import Decimal

from creem_bridge.money import Payment, fee, kept, net, payments
from helpers import F, at, live, pay


def test_creem_worked_example():
    # docs.creem.io, Finance → Payouts: 24.00 including 4.00 VAT → fee 1.33, net 18.67.
    p = pay(paid="24.00", tax="4.00")
    assert fee(p, F) == Decimal("1.33")
    assert net(p, F) == Decimal("18.67")


def test_full_refund_keeps_the_fee():
    p = pay(paid="1.99", tax="0.32", refunded="1.99")
    assert kept(p) == 0
    assert net(p, F) == Decimal("-0.47")


def test_partial_refund_is_proportional():
    p = pay(paid="24.00", tax="4.00", refunded="12.00")
    assert kept(p) == Decimal("12.00")
    assert net(p, F) == Decimal("8.67")


def test_free_payment_is_zero():
    p = pay(paid="0", tax="0")
    assert fee(p, F) == 0 and net(p, F) == 0


def test_payments_from_creem_json():
    ps = sorted(payments(live()), key=lambda p: p.plan)
    monthly, yearly = ps
    assert monthly.plan == "notefeed license, monthly" and yearly.plan == "notefeed license, yearly"
    assert (monthly.paid, monthly.tax, monthly.refunded) == (Decimal("1.99"), Decimal("0.32"), Decimal("1.99"))
    assert (yearly.paid, yearly.refunded) == (Decimal("0"), Decimal("0"))
    assert monthly.currency == "EUR" and monthly.store == "notefeed"
    assert yearly.period_start == at("2026-10-21T15:51:36.860Z")
    assert yearly.paid_at.tzinfo is not None
    assert {f.name for f in fields(Payment)} == {
        "store", "plan", "currency", "paid", "tax", "refunded", "period_start", "period_end", "paid_at", "refunded_at"}


def _tx(status):
    return {"id": "t", "amount": 199, "amount_paid": 199, "currency": "EUR", "tax_amount": 32, "status": status,
            "refunded_amount": None, "subscription": None, "period_start": 1792596547051, "period_end": 1795274947051,
            "created_at": 1792596548688}


def test_unknown_payment_status_is_named_not_dropped():
    import pytest
    from creem_bridge.creem import StoreData
    with pytest.raises(ValueError, match="chargeback"):
        payments(StoreData("notefeed", [_tx("chargeback")], []))


def test_payments_that_did_not_happen_are_left_out():
    from creem_bridge.creem import StoreData
    assert payments(StoreData("notefeed", [_tx("pending"), _tx("failed")], [])) == []
