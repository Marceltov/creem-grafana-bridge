"""Settings, all from the environment. Defaults are Creem's published fees and payout rules as of October 2026."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

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

        def dec(var: str, default: str) -> Decimal:
            return Decimal(env.get(var) or default)

        return cls(
            stores=stores,
            token=env["BRIDGE_TOKEN"],
            tz=ZoneInfo(env.get("TZ") or "Europe/Berlin"),
            fees=Fees(dec("FEE_PERCENT", "3.9"), dec("FEE_FIXED", "0.40")),
            payouts=PayoutRules(dec("PAYOUT_MIN", "50"), int(env.get("PAYOUT_HOLD_DAYS") or 12),
                                dec("PAYOUT_FEE_MIN", "7"), dec("PAYOUT_FEE_PERCENT", "1")),
            cache_seconds=int(env.get("CACHE_SECONDS") or 300),
            port=int(env.get("PORT") or 8080),
            base_url=(env.get("CREEM_API_URL") or "https://api.creem.io").rstrip("/"),
            months=int(env.get("FORECAST_MONTHS") or 12),
        )
