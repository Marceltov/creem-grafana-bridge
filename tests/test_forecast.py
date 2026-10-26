from decimal import Decimal
from zoneinfo import ZoneInfo

from creem_bridge.creem import StoreData
from creem_bridge.forecast import PayoutRules, forecast, payouts
from creem_bridge.money import Fees
from helpers import F, at, live, pay

BERLIN = ZoneInfo("Europe/Berlin")
NOW = at("2026-10-26T08:00Z")
RULES = PayoutRules(minimum=Decimal(50), hold_days=12, fee_min=Decimal(7), fee_percent=Decimal(1))
NO_FEES = Fees(Decimal(0), Decimal(0))


def sub(price=199, interval="month", next_at="2026-11-21T15:29:07Z", status="active", canceled_at=None,
        discount=None, created="2026-10-21T15:29:07Z", last=(199, 32)):
    return {
        "id": "sub_1", "status": status, "canceled_at": canceled_at, "created_at": created,
        "next_transaction_date": next_at, "discount": discount,
        "product": {"name": "monthly", "price": price, "currency": "EUR",
                    "recurring_interval": interval, "recurring_interval_count": 1},
        "last_transaction": {"amount_paid": last[0], "tax_amount": last[1]},
    }


def store(*subs):
    return [StoreData("notefeed", [], list(subs))]


def test_monthly_without_discount_twelve_payments():
    rows = forecast(store(sub()), NOW, "gross", F, BERLIN)
    assert len(rows) == 12
    assert all(r["amount"] == Decimal("1.99") for r in rows)
    assert rows[0]["time"] == "2026-11-21T00:00:00+01:00"
    assert rows[-1]["time"] == "2027-10-21T00:00:00+02:00"


def test_net_forecast_uses_the_last_payments_vat_share():
    rows = forecast(store(sub()), NOW, "net", F, BERLIN)
    assert rows[0]["amount"] == Decimal("1.20")  # 1.99 − 0.32 VAT − 0.47 fee


def test_operator_licence_with_100_percent_forecasts_nothing():
    assert forecast([live()], NOW, "gross", F, BERLIN) == []


def test_repeating_discount_ends():
    d = {"type": "percentage", "amount": 20, "duration": "repeating", "durationInMonths": 3}
    rows = forecast(store(sub(price=1990, discount=d, last=(1592, 254))), NOW, "gross", F, BERLIN)
    assert [r["amount"] for r in rows[:3]] == [Decimal("15.92"), Decimal("15.92"), Decimal("19.90")]


def test_cancelled_subscription_forecasts_nothing():
    assert forecast(store(sub(status="canceled", canceled_at="2026-10-22T00:00Z")), NOW, "gross", F, BERLIN) == []
    # cancelled to the end of its period: still "active", but nothing more is coming
    assert forecast(store(sub(canceled_at="2026-10-22T00:00Z")), NOW, "gross", F, BERLIN) == []


def test_yearly_repeats_yearly():
    rows = forecast(store(sub(price=1990, interval="year", next_at="2027-10-21T15:51:36Z")), NOW, "gross", F, BERLIN)
    assert [r["time"][:10] for r in rows] == ["2027-10-21"]


def test_payout_waits_for_minimum_and_hold():
    rows = payouts([pay(paid="60.00", tax="0", paid_at="2026-10-10T10:00Z")], [], RULES, NO_FEES, BERLIN)
    assert [(r["time"], r["plan"], r["amount"]) for r in rows] == [("2026-11-01T00:00:00+01:00", "payout", Decimal("53.00"))]
    assert payouts([pay(paid="40.00", tax="0", paid_at="2026-10-10T10:00Z")], [], RULES, NO_FEES, BERLIN) == []


def test_payout_fee_is_one_percent_above_700():
    rows = payouts([pay(paid="1000.00", tax="0", paid_at="2026-10-10T10:00Z")], [], RULES, NO_FEES, BERLIN)
    assert rows[0]["amount"] == Decimal("990.00")


def test_expected_payments_become_future_payouts():
    expected = [{"time": "2026-11-21T00:00:00+01:00", "store": "notefeed", "plan": "monthly", "currency": "EUR", "amount": Decimal("60.00")}]
    rows = payouts([], expected, RULES, NO_FEES, BERLIN)
    assert [r["time"][:10] for r in rows] == ["2026-12-15"]  # available 3 December, next payout day the 15th


def test_unknown_interval_is_named():
    import pytest
    with pytest.raises(ValueError, match="week"):
        forecast(store(sub(interval="week")), NOW, "gross", F, BERLIN)


def test_units_multiply_the_price():
    s = sub(price=1000)
    s["items"] = [{"units": 5}]
    assert forecast(store(s), NOW, "gross", F, BERLIN)[0]["amount"] == Decimal("50.00")


def test_prices_without_vat_are_named_not_guessed():
    import pytest
    s = sub()
    s["product"]["tax_mode"] = "exclusive"
    with pytest.raises(ValueError, match="exclusive"):
        forecast(store(s), NOW, "gross", F, BERLIN)


def test_month_end_is_clamped_without_drift():
    rows = forecast(store(sub(next_at="2027-01-31T10:00:00Z")), NOW, "gross", F, BERLIN, months=6)
    assert [r["time"][:10] for r in rows] == ["2027-01-31", "2027-02-28", "2027-03-31"]


def test_dates_keep_their_day_across_the_clock_change():
    rows = forecast(store(sub(next_at="2027-03-28T10:00:00Z")), NOW, "gross", F, BERLIN, months=7)
    assert [r["time"] for r in rows[:2]] == ["2027-03-28T00:00:00+01:00", "2027-04-28T00:00:00+02:00"]


def test_forever_and_fixed_discounts():
    forever = {"type": "percentage", "amount": 50, "duration": "forever"}
    assert {r["amount"] for r in forecast(store(sub(price=1990, discount=forever)), NOW, "gross", F, BERLIN)} == {Decimal("9.95")}
    fixed = {"type": "fixed", "amount": 500, "duration": "forever"}
    assert {r["amount"] for r in forecast(store(sub(price=1990, discount=fixed)), NOW, "gross", F, BERLIN)} == {Decimal("14.90")}


def test_once_discount_is_used_by_the_first_payment():
    once = {"type": "percentage", "amount": 50, "duration": "once"}
    # active: the first payment already took it
    assert forecast(store(sub(price=1990, discount=once)), NOW, "gross", F, BERLIN)[0]["amount"] == Decimal("19.90")
    # trialing: the first payment is still to come and takes it
    rows = forecast(store(sub(price=1990, discount=once, status="trialing", last=(0, 0))), NOW, "gross", F, BERLIN)
    assert [r["amount"] for r in rows[:2]] == [Decimal("9.95"), Decimal("19.90")]


def test_repeating_discount_of_a_trial_counts_from_the_first_payment():
    d = {"type": "percentage", "amount": 20, "duration": "repeating", "durationInMonths": 2}
    s = sub(price=1990, discount=d, status="trialing", created="2026-10-14T15:29:07Z", last=(0, 0))
    rows = forecast(store(s), NOW, "gross", F, BERLIN)
    assert [r["amount"] for r in rows[:3]] == [Decimal("15.92"), Decimal("15.92"), Decimal("19.90")]
