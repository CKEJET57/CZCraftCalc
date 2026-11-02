"""
services/price.py — единая точка получения цены за штуку.

Приоритет:
  1) медиана истории (trimmed median, как в JS-фрагменте)
  2) fallback: минимальная цена активного лота
  3) None — если данных нет
"""

import statistics
import time
from dataclasses import dataclass

import requests

from config import DEFAULT_REGION, EAPI_BASE


@dataclass
class PriceInfo:
    item_id: str
    unit_price: float | None
    source: str          # "history" | "lots" | "none"
    samples: int = 0


class PriceService:
    def __init__(
        self,
        token: str,
        region: str = DEFAULT_REGION,
        ttl: int = 600,                 # кэш живёт 10 минут
        history_limit: int = 200,
        lots_limit: int = 200,
        trim_ratio: float = 0.1,        # отсечь 10% с краёв
        min_samples: int = 5,           # меньше — не доверяем медиане
        fallback_to_lots: bool = True,
    ):
        self.token = token
        self.region = region
        self.ttl = ttl
        self.history_limit = history_limit
        self.lots_limit = lots_limit
        self.trim_ratio = trim_ratio
        self.min_samples = min_samples
        self.fallback_to_lots = fallback_to_lots
        self._cache: dict[str, tuple[PriceInfo, float]] = {}

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def get(self, item_id: str) -> PriceInfo:
        now = time.time()
        if item_id in self._cache:
            info, ts = self._cache[item_id]
            if now - ts < self.ttl:
                return info

        info = self._fetch(item_id)
        self._cache[item_id] = (info, now)
        return info

    def _fetch(self, item_id: str) -> PriceInfo:
        median, samples = self._history_median(item_id)
        if median is not None:
            return PriceInfo(item_id, median, "history", samples)

        if self.fallback_to_lots:
            min_lot, lots_count = self._min_lot_price(item_id)
            if min_lot is not None:
                return PriceInfo(item_id, min_lot, "lots", lots_count)

        return PriceInfo(item_id, None, "none", 0)

    def _history_median(self, item_id: str) -> tuple[float | None, int]:
        url = f"{EAPI_BASE}/{self.region}/auction/{item_id}/history"
        try:
            r = requests.get(
                url,
                params={"limit": self.history_limit},
                headers=self._headers(),
                timeout=20,
            )
            if r.status_code != 200:
                return None, 0
            data = r.json()
        except (requests.RequestException, ValueError):
            return None, 0

        prices = data.get("prices") or data.get("lots") or []
        unit = sorted(
            p["price"] / p["amount"]
            for p in prices
            if p.get("amount", 0) > 0 and p.get("price", 0) > 0
        )
        if len(unit) < self.min_samples:
            return None, len(unit)

        trim = int(len(unit) * self.trim_ratio)
        core = unit[trim: len(unit) - trim] if trim else unit
        return statistics.median(core), len(core)

    def _min_lot_price(self, item_id: str) -> tuple[float | None, int]:
        url = f"{EAPI_BASE}/{self.region}/auction/{item_id}/lots"
        try:
            r = requests.get(
                url,
                params={"limit": self.lots_limit, "additional": "true"},
                headers=self._headers(),
                timeout=20,
            )
            if r.status_code != 200:
                return None, 0
            data = r.json()
        except (requests.RequestException, ValueError):
            return None, 0

        lots = data.get("lots") or data.get("prices") or []
        unit_prices = []
        for lot in lots:
            amount = lot.get("amount", 0)
            price = lot.get("buyoutPrice") or lot.get("price")  # buyout → price
            if amount > 0 and price and price > 0:
                unit_prices.append(price / amount)

        if not unit_prices:
            return None, 0
        return min(unit_prices), len(unit_prices)