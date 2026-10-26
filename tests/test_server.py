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
