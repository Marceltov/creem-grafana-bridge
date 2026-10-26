"""GET /series for Grafana (behind a bearer token) and GET /health for the container check."""

import hmac
import json
import logging
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import Config
from .creem import CreemError, StoreData, load_store
from .forecast import add_months, forecast, payouts
from .money import payments
from .series import cashflow, month_start, revenue

log = logging.getLogger("creem_bridge")
KINDS = ("revenue", "cashflow", "forecast", "payouts")
BASES = ("gross", "net")
GROUPS = ("plan", "store", "total")
PERIODS = ("date", "month")
RELATIVE = re.compile(r"now(?:([+-])(\d+)([dM]))?(?:/([dM]))?")


def instant(value: str, now: datetime, tz: ZoneInfo) -> datetime:
    """Epoch milliseconds, as Grafana's ${__from} and ${__to}, or Grafana-style `now`, `now-30d`, `now+1M/M` (/M: the
    start of that month, /d: the start of that day)."""
    if value.isdigit():
        return datetime.fromtimestamp(int(value) / 1000, UTC)
    m = RELATIVE.fullmatch(value)
    if not m:
        raise ValueError(value)
    sign, n, unit, round_to = m.groups()
    t = now
    if n:
        k = int(n) * (1 if sign == "+" else -1)
        t = add_months(t, k) if unit == "M" else t + timedelta(days=k)
    if round_to == "M":
        return month_start(t, tz)
    if round_to == "d":
        return t.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return t


def regroup(rows: list[dict], by: str, per: str, tz: ZoneInfo) -> list[dict]:
    """Sums the plans (by store) or everything (total) into "all", and dates into their month (per month)."""
    if by == "plan" and per == "date":
        return rows
    sums: dict[tuple, Decimal] = defaultdict(Decimal)
    for r in rows:
        t = month_start(datetime.fromisoformat(r["time"]), tz).isoformat() if per == "month" else r["time"]
        store = r["store"] if by != "total" else "all"
        plan = r["plan"] if by == "plan" else "all"
        sums[(t, store, plan, r["currency"])] += r["amount"]
    return [{"time": t, "store": s, "plan": p, "currency": c, "amount": a} for (t, s, p, c), a in sorted(sums.items())]


class StoreFailed(Exception):
    pass


def make_server(cfg: Config, load: Callable[[str, str, str], StoreData] = load_store,
                now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> ThreadingHTTPServer:
    cache: dict[str, tuple[float, StoreData]] = {}
    # One lock per store, held while it is fetched: the dashboard's panels ask at once, and Creem is asked once.
    locks = {name: threading.Lock() for name in cfg.stores}

    def store_data(name: str) -> StoreData:
        with locks[name]:
            hit = cache.get(name)
            if hit and time.monotonic() - hit[0] < cfg.cache_seconds:
                return hit[1]
            try:
                data = load(name, cfg.stores[name], cfg.base_url)
            except Exception as e:  # any failure, so no answer leaves a store out without saying which
                raise StoreFailed(f"store {name}: {e}") from None
            cache[name] = (time.monotonic(), data)
            return data

    def series(kind: str, basis: str, names: list[str]) -> list[dict]:
        data = [store_data(n) for n in names]
        try:
            ps = [p for d in data for p in payments(d)]
            if kind == "revenue":
                return revenue(ps, basis, cfg.fees, cfg.tz)
            if kind == "cashflow":
                return cashflow(ps, basis, cfg.fees, cfg.tz)
            if kind == "forecast":
                return forecast(data, now(), basis, cfg.fees, cfg.tz, cfg.months)
            # Payouts are always after fees; `basis` does not apply.
            return payouts(ps, forecast(data, now(), "net", cfg.fees, cfg.tz, cfg.months), cfg.payouts, cfg.fees, cfg.tz)
        except Exception as e:
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
            if url.path not in ("/series", "/stores"):
                return self.send(404, {"error": "not found"})
            given = self.headers.get("Authorization", "")
            if not hmac.compare_digest(given.encode(), f"Bearer {cfg.token}".encode()):
                return self.send(401, {"error": "unauthorized"})
            if url.path == "/stores":
                return self.send(200, list(cfg.stores))
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            kind, basis, by, per = q.get("kind"), q.get("basis", "gross"), q.get("by", "plan"), q.get("per", "date")
            # Grafana's multi-value variable sends "All" as the list of every value, or as nothing.
            names = [n.strip() for n in q["store"].split(",")] if q.get("store") else list(cfg.stores)
            try:
                start = instant(q["from"], now(), cfg.tz) if q.get("from") else None
                end = instant(q["to"], now(), cfg.tz) if q.get("to") else None
            except ValueError:
                return self.send(400, {"error": "from and to are epoch milliseconds or now, now-30d, now+1M/M, now/d"})
            if kind not in KINDS or basis not in BASES or by not in GROUPS or per not in PERIODS or any(n not in cfg.stores for n in names):
                return self.send(400, {"error": f"kind is one of {KINDS}, basis one of {BASES}, by one of {GROUPS}, per one of {PERIODS}, store any of {list(cfg.stores)}"})
            try:
                rows = series(kind, basis, names)
            except StoreFailed as e:
                return self.send(502, {"error": str(e)})
            currency = q.get("currency")
            rows = [r for r in rows if (currency is None or r["currency"] == currency) and (start is None or datetime.fromisoformat(r["time"]) >= start)
                    and (end is None or datetime.fromisoformat(r["time"]) < end)]
            self.send(200, [{**r, "amount": float(r["amount"])} for r in regroup(rows, by, per, cfg.tz)])

        def log_message(self, fmt, *args):
            # The request line only: no headers, so never the token.
            log.info("%s %s", self.address_string(), fmt % args)

    return ThreadingHTTPServer(("0.0.0.0", cfg.port), Handler)
