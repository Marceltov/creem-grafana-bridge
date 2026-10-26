"""Settings, all from the environment. Defaults are Creem's published fees and payout rules as of October 2026."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .forecast import PayoutRules
from .money import Fees


@dataclass(frozen=True)
class Config:
    stores: dict[str, str]  # name → API key
    token: str
    tz: ZoneInfo
    fees: Fees
    payouts: PayoutRules
    cache_seconds: int
    port: int
    base_url: str
    months: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Config":
        names = [n.strip() for n in env.get("CREEM_STORES", "").split(",") if n.strip()]
        if not names:
            raise ValueError("CREEM_STORES names no store")
        stores = {}
        for name in names:
            var = f"CREEM_KEY_{name.upper().replace('-', '_')}"
            if not env.get(var):
                raise ValueError(f"{var} is not set (the API key of store {name})")
            stores[name] = env[var]
        if not env.get("BRIDGE_TOKEN"):
            raise ValueError("BRIDGE_TOKEN is not set")

        def read(var: str, default: str, kind):
            value = env.get(var) or default
            try:
                return kind(value)
            except (InvalidOperation, ValueError, ZoneInfoNotFoundError):
                raise ValueError(f"{var}={value!r} is not a valid {getattr(kind, '__name__', kind)}") from None

        def dec(var: str, default: str) -> Decimal:
            return read(var, default, Decimal)

        return cls(
            stores=stores,
            token=env["BRIDGE_TOKEN"],
            tz=read("TZ", "Europe/Berlin", ZoneInfo),
            fees=Fees(dec("FEE_PERCENT", "3.9"), dec("FEE_FIXED", "0.40")),
            payouts=PayoutRules(dec("PAYOUT_MIN", "50"), read("PAYOUT_HOLD_DAYS", "12", int),
                                dec("PAYOUT_FEE_MIN", "7"), dec("PAYOUT_FEE_PERCENT", "1")),
            cache_seconds=read("CACHE_SECONDS", "300", int),
            port=read("PORT", "8080", int),
            base_url=(env.get("CREEM_API_URL") or "https://api.creem.io").rstrip("/"),
            months=read("FORECAST_MONTHS", "12", int),
        )
