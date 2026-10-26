"""GET /series for Grafana (behind a bearer token) and GET /health for the container check."""

import hmac
import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import Config
from .creem import CreemError, StoreData, load_store
from .forecast import forecast, payouts
from .money import payments
from .series import cashflow, revenue

log = logging.getLogger("creem_bridge")
KINDS = ("revenue", "cashflow", "forecast", "payouts")
BASES = ("gross", "net")


class StoreFailed(Exception):
    pass


def make_server(cfg: Config, load: Callable[[str, str, str], StoreData] = load_store,
                now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> ThreadingHTTPServer:
    cache: dict[str, tuple[float, StoreData]] = {}
    lock = threading.Lock()

    def store_data(name: str) -> StoreData:
        with lock:
            hit = cache.get(name)
            if hit and time.monotonic() - hit[0] < cfg.cache_seconds:
                return hit[1]
        try:
            data = load(name, cfg.stores[name], cfg.base_url)
        except CreemError as e:
            raise StoreFailed(f"store {name}: {e}") from None
        with lock:
            cache[name] = (time.monotonic(), data)
        return data

    def series(kind: str, basis: str, names: list[str]) -> list[dict]:
        data = [store_data(n) for n in names]
        ps = [p for d in data for p in payments(d)]
        try:
            if kind == "revenue":
                return revenue(ps, basis, cfg.fees, cfg.tz)
            if kind == "cashflow":
                return cashflow(ps, basis, cfg.fees, cfg.tz)
            if kind == "forecast":
                return forecast(data, now(), basis, cfg.fees, cfg.tz, cfg.months)
            # Payouts are always after fees; `basis` does not apply.
            return payouts(ps, forecast(data, now(), "net", cfg.fees, cfg.tz, cfg.months), cfg.payouts, cfg.fees, cfg.tz)
        except ValueError as e:
            raise StoreFailed(str(e)) from None

    class Handler(BaseHTTPRequestHandler):
        def send(self, status: int, body, content_type="application/json"):
            raw = (json.dumps(body) if content_type == "application/json" else body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/health":
                return self.send(200, "ok", "text/plain")
            if url.path != "/series":
                return self.send(404, {"error": "not found"})
            given = self.headers.get("Authorization", "").removeprefix("Bearer ")
            if not hmac.compare_digest(given.encode(), cfg.token.encode()):
                return self.send(401, {"error": "unauthorized"})
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            kind, basis = q.get("kind"), q.get("basis", "gross")
            names = [n.strip() for n in q["store"].split(",")] if q.get("store") else list(cfg.stores)
            if kind not in KINDS or basis not in BASES or any(n not in cfg.stores for n in names):
                return self.send(400, {"error": f"kind is one of {KINDS}, basis one of {BASES}, store any of {list(cfg.stores)}"})
            try:
                rows = series(kind, basis, names)
            except StoreFailed as e:
                return self.send(502, {"error": str(e)})
            self.send(200, [{**r, "amount": float(r["amount"])} for r in rows])

        def log_message(self, fmt, *args):
            # The request line only: no headers, so never the token.
            log.info("%s %s", self.address_string(), fmt % args)

    return ThreadingHTTPServer(("0.0.0.0", cfg.port), Handler)
