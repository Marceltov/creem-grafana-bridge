import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from creem_bridge.config import Config
from creem_bridge.creem import CreemError, StoreData
from creem_bridge.server import make_server
from helpers import at, live

ENV = {"CREEM_STORES": "notefeed, b", "CREEM_KEY_NOTEFEED": "k1", "CREEM_KEY_B": "k2", "BRIDGE_TOKEN": "t"}


@pytest.fixture
def serve():
    servers = []

    def start(load, env=ENV):
        srv = make_server(Config.from_env({**env, "PORT": "0"}), load=load, now=lambda: at("2026-10-26T08:00Z"))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    yield start
    for s in servers:
        s.shutdown()


def get(url, token="t"):
    req = Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urlopen(req) as r:
            return r.status, json.load(r) if "json" in r.headers["content-type"] else r.read().decode()
    except HTTPError as e:
        return e.code, json.load(e)


def stores(name, key, base_url):
    return live() if name == "notefeed" else StoreData(name, [], [])


def test_health_needs_no_token(serve):
    assert get(serve(stores) + "/health", token=None) == (200, "ok")


def test_series_needs_the_token(serve):
    base = serve(stores)
    assert get(base + "/series?kind=revenue&basis=gross", token=None)[0] == 401
    assert get(base + "/series?kind=revenue&basis=gross", token="wrong")[0] == 401


def test_rows_have_exactly_five_keys_and_numbers(serve):
    status, rows = get(serve(stores) + "/series?kind=cashflow&basis=net")
    assert status == 200
    assert rows == [{"time": "2026-10-01T00:00:00+02:00", "store": "notefeed", "plan": "notefeed license, monthly",
                     "currency": "EUR", "amount": -0.47}]


def test_every_kind_answers(serve):
    base = serve(stores)
    for kind in ("revenue", "cashflow", "forecast", "payouts"):
        assert get(base + f"/series?kind={kind}&basis=gross")[0] == 200


def test_bad_parameters_are_400(serve):
    base = serve(stores)
    assert get(base + "/series?kind=profit&basis=gross")[0] == 400
    assert get(base + "/series?kind=revenue&basis=after")[0] == 400
    assert get(base + "/series?kind=revenue&basis=gross&store=nope")[0] == 400


def test_one_failing_store_fails_the_request(serve):
    def load(name, key, base_url):
        if name == "b":
            raise CreemError(401)
        return live()

    status, body = get(serve(load) + "/series?kind=revenue&basis=gross")
    assert status == 502 and body == {"error": "store b: Creem answered 401"}


def test_store_without_sales_is_empty_not_an_error(serve):
    assert get(serve(stores) + "/series?kind=revenue&basis=gross&store=b") == (200, [])


def test_cache_asks_creem_once_per_period(serve):
    calls = []

    def load(name, key, base_url):
        calls.append(name)
        return StoreData(name, [], [])

    base = serve(load)
    get(base + "/series?kind=revenue&basis=gross")
    get(base + "/series?kind=cashflow&basis=net")
    assert sorted(calls) == ["b", "notefeed"]


def test_missing_key_names_the_variable():
    with pytest.raises(ValueError, match="CREEM_KEY_NOTEFEED"):
        Config.from_env({"CREEM_STORES": "notefeed", "BRIDGE_TOKEN": "t"})


def test_token_is_required():
    with pytest.raises(ValueError, match="BRIDGE_TOKEN"):
        Config.from_env({"CREEM_STORES": "notefeed", "CREEM_KEY_NOTEFEED": "k"})


def test_stores_lists_the_configured_names(serve):
    assert get(serve(stores) + "/stores") == (200, ["notefeed", "b"])


def test_from_to_filter_rows_in_ms_and_relative(serve):
    base = serve(stores)
    _, rows = get(base + "/series?kind=revenue&basis=net")
    assert [r["time"][:7] for r in rows] == ["2026-10", "2026-11"]
    # epoch milliseconds as Grafana sends ${__from} and ${__to}; `to` is exclusive
    nov = 1793487600000  # 2026-11-01T00:00+01:00
    assert [r["time"][:7] for r in get(base + f"/series?kind=revenue&basis=net&from={nov}")[1]] == ["2026-11"]
    assert [r["time"][:7] for r in get(base + f"/series?kind=revenue&basis=net&to={nov}")[1]] == ["2026-10"]
    # relative to now (2026-10-26): this month, and the month after
    assert [r["time"][:7] for r in get(base + "/series?kind=revenue&basis=net&from=now/M&to=now%2B1M/M")[1]] == ["2026-10"]
    assert [r["time"][:7] for r in get(base + "/series?kind=revenue&basis=net&from=now%2B1M/M")[1]] == ["2026-11"]
    assert get(base + "/series?kind=revenue&basis=net&from=yesterday")[0] == 400


def test_by_total_and_store_sum_the_plans(serve):
    def load(name, key, base_url):
        return live() if name == "notefeed" else StoreData(name, [], [])

    base = serve(load)
    _, rows = get(base + "/series?kind=cashflow&basis=net&by=total")
    assert rows == [{"time": "2026-10-01T00:00:00+02:00", "store": "all", "plan": "all", "currency": "EUR", "amount": -0.47}]
    _, rows = get(base + "/series?kind=cashflow&basis=net&by=store")
    assert [(r["store"], r["plan"]) for r in rows] == [("notefeed", "all")]
    assert get(base + "/series?kind=cashflow&basis=net&by=colour")[0] == 400


def test_per_month_sums_dates_into_months(serve):
    def load(name, key, base_url):
        return StoreData(name, [], [{
            "id": "s", "status": "active", "canceled_at": None, "created_at": "2026-10-01T10:00:00Z",
            "next_transaction_date": "2026-11-01T10:00:00Z", "discount": None,
            "product": {"name": "weekly-ish", "price": 100, "currency": "EUR", "recurring_interval": "month", "recurring_interval_count": 1},
            "last_transaction": {"amount_paid": 100, "tax_amount": 0}}])

    base = serve(load)
    _, rows = get(base + "/series?kind=forecast&basis=gross&by=total&per=month&to=now%2B3M/M")
    # one subscription in each of two stores: two payments per month, in November and December
    assert [(r["time"], r["amount"]) for r in rows] == [("2026-11-01T00:00:00+01:00", 2.0), ("2026-12-01T00:00:00+01:00", 2.0)]
    assert get(base + "/series?kind=forecast&basis=gross&per=week")[0] == 400


def test_any_store_failure_names_the_store(serve):
    def load(name, key, base_url):
        if name == "b":
            raise TimeoutError("read timed out")
        return live()

    status, body = get(serve(load) + "/series?kind=revenue&basis=gross")
    assert status == 502 and body["error"].startswith("store b:")


def test_parallel_requests_ask_creem_once(serve):
    import time as _time
    from concurrent.futures import ThreadPoolExecutor
    calls = []

    def load(name, key, base_url):
        calls.append(name)
        _time.sleep(0.2)
        return StoreData(name, [], [])

    base = serve(load)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: get(base + "/series?kind=revenue&basis=gross"), range(8)))
    assert sorted(calls) == ["b", "notefeed"]


def test_unknown_payment_status_is_502_naming_the_store(serve):
    def load(name, key, base_url):
        d = live()
        d.transactions[0] = {**d.transactions[0], "status": "chargeback"}
        return StoreData(name, d.transactions, d.subscriptions)

    status, body = get(serve(load) + "/series?kind=cashflow&basis=gross&store=b")
    assert status == 502 and "store b" in body["error"] and "chargeback" in body["error"]


def test_currency_keeps_one_currency(serve):
    def load(name, key, base_url):
        d = live()
        t = d.transactions[1]
        usd = {**t, "id": "t2", "currency": "USD"}
        return StoreData(name, [t, usd], d.subscriptions)

    base = serve(load)
    _, rows = get(base + "/series?kind=cashflow&basis=gross&by=total&store=notefeed")
    assert sorted(r["currency"] for r in rows) == []  # both refunded: nothing kept
    _, rows = get(base + "/series?kind=cashflow&basis=net&by=total&store=notefeed&currency=USD")
    assert [r["currency"] for r in rows] == ["USD"]


def test_from_start_of_today_keeps_a_payment_due_later_today(serve):
    def load(name, key, base_url):
        return StoreData(name, [], [{
            "id": "s", "status": "active", "canceled_at": None, "created_at": "2026-09-26T15:00:00Z",
            "next_transaction_date": "2026-10-26T15:00:00Z", "discount": None,
            "product": {"name": "m", "price": 100, "currency": "EUR", "recurring_interval": "month", "recurring_interval_count": 1},
            "last_transaction": {"amount_paid": 100, "tax_amount": 0}}])

    base = serve(load)
    q = "/series?kind=forecast&basis=gross&by=total&store=notefeed&to=now%2B1d"
    assert get(base + q + "&from=now")[1] == []
    assert [r["time"] for r in get(base + q + "&from=now/d")[1]] == ["2026-10-26T00:00:00+01:00"]


def test_token_needs_the_bearer_scheme(serve):
    req = Request(serve(stores) + "/series?kind=revenue", headers={"Authorization": "t"})
    with pytest.raises(HTTPError) as e:
        urlopen(req)
    assert e.value.code == 401


def test_total_keeps_currencies_apart(serve):
    def load(name, key, base_url):
        d = live()
        t = {**d.transactions[1], "status": "paid", "refunded_amount": None}
        return StoreData(name, [t, {**t, "id": "t2", "currency": "USD"}], d.subscriptions)

    _, rows = get(serve(load) + "/series?kind=cashflow&basis=gross&by=total&store=notefeed")
    assert sorted((r["currency"], r["amount"]) for r in rows) == [("EUR", 1.99), ("USD", 1.99)]


@pytest.mark.parametrize("var,value", [("FEE_PERCENT", "abc"), ("TZ", "Mars/Base"), ("PORT", "x"), ("PAYOUT_HOLD_DAYS", "1.5")])
def test_bad_setting_names_the_variable(var, value):
    with pytest.raises(ValueError, match=var):
        Config.from_env({**ENV, var: value})
