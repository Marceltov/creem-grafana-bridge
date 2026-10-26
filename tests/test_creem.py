from urllib.parse import parse_qs, urlparse

import pytest

from creem_bridge.creem import CreemError, StoreData, fetch_all, load_store


def page_of(url: str) -> int:
    return int(parse_qs(urlparse(url).query)["page_number"][0])


def test_fetch_all_reads_every_page():
    pages = {
        1: {"items": [{"id": "a"}], "pagination": {"next_page": 2}},
        2: {"items": [{"id": "b"}], "pagination": {"next_page": None}},
    }
    seen = []

    def get(url, headers):
        seen.append((url, headers["x-api-key"]))
        return pages[page_of(url)]

    assert [i["id"] for i in fetch_all("https://x", "k", "/v1/transactions/search", get)] == ["a", "b"]
    assert all(k == "k" for _, k in seen)
    assert all(urlparse(u).path == "/v1/transactions/search" for u, _ in seen)


def test_load_store_reads_transactions_and_subscriptions():
    def get(url, headers):
        kind = urlparse(url).path.split("/")[2]
        return {"items": [{"kind": kind}], "pagination": {"next_page": None}}

    data = load_store("notefeed", "k", "https://x", get)
    assert data == StoreData("notefeed", [{"kind": "transactions"}], [{"kind": "subscriptions"}])


def test_non_200_raises_creem_error():
    def get(url, headers):
        raise CreemError(401)

    with pytest.raises(CreemError) as e:
        load_store("notefeed", "k", "https://x", get)
    assert e.value.status == 401


def test_requests_name_themselves():
    # Creem answers urllib's default user agent with 403.
    seen = []

    def get(url, headers):
        seen.append(headers)
        return {"items": [], "pagination": {"next_page": None}}

    fetch_all("https://x", "k", "/v1/products/search", get)
    assert seen[0]["user-agent"].startswith("creem-grafana-bridge/")
