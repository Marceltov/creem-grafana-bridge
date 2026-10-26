"""Reading a Creem store: every page of its transactions and subscriptions, with GET requests only."""

import json
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PAGE_SIZE = 100
# Creem answers urllib's default user agent with 403.
USER_AGENT = "creem-grafana-bridge/0.1.0"

Get = Callable[[str, dict[str, str]], dict]


class CreemError(Exception):
    """Creem did not answer 200; `status` is its HTTP status, or 0 when it could not be reached."""

    def __init__(self, status: int):
        super().__init__(f"Creem answered {status}" if status else "Creem could not be reached")
        self.status = status


@dataclass
class StoreData:
    store: str
    transactions: list[dict]
    subscriptions: list[dict]


def _urlopen_get(url: str, headers: dict[str, str]) -> dict:
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as r:
            return json.load(r)
    except HTTPError as e:
        raise CreemError(e.code) from None
    except URLError:
        raise CreemError(0) from None


def fetch_all(base_url: str, key: str, path: str, get: Get | None = None) -> list[dict]:
    get = get or _urlopen_get
    items: list[dict] = []
    page: int | None = 1
    while page:
        body = get(f"{base_url}{path}?{urlencode({'page_size': PAGE_SIZE, 'page_number': page})}", {"x-api-key": key, "accept": "application/json", "user-agent": USER_AGENT})
        items += body["items"]
        page = body["pagination"]["next_page"]
    return items


def load_store(store: str, key: str, base_url: str, get: Get | None = None) -> StoreData:
    return StoreData(
        store,
        fetch_all(base_url, key, "/v1/transactions/search", get),
        fetch_all(base_url, key, "/v1/subscriptions/search", get),
    )
