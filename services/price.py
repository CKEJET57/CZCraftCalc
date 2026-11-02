"""
services/price.py — цены за штуку.

Фичи:
  - requests.Session (keep-alive)
  - потокобезопасный кэш
  - бюджет запросов (max_requests)
  - параллельный prefetch()
  - heartbeat в stderr
  - verbose: лог каждого HTTP-запроса
  - опционально: только /lots (без /history)
"""

import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterable

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
        ttl: int = 600,
        history_limit: int = 200,
        lots_limit: int = 200,
        trim_ratio: float = 0.1,
        min_samples: int = 5,
        fallback_to_lots: bool = True,
        use_history: bool = True,
        max_requests: int = 500,
        heartbeat: bool = True,
        heartbeat_interval: float = 5.0,
        verbose: bool = False,
    ):
        self.token = token
        self.region = region
        self.ttl = ttl
        self.history_limit = history_limit
        self.lots_limit = lots_limit
        self.trim_ratio = trim_ratio
        self.min_samples = min_samples
        self.fallback_to_lots = fallback_to_lots
        self.use_history = use_history
        self.max_requests = max_requests
        self.heartbeat_enabled = heartbeat
        self.heartbeat_interval = heartbeat_interval
        self.verbose = verbose

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
        self._cache: dict[str, tuple[PriceInfo, float]] = {}
        self._lock = threading.Lock()
        self._requests_made = 0
        self._started_at = time.time()
        self._last_activity = time.time()
        self._last_activity_label = "init"

        self._hb_thread: threading.Thread | None = None
        self._hb_stop = threading.Event()
        if self.heartbeat_enabled:
            self._start_heartbeat()

    # ---------------- heartbeat ----------------
    def _start_heartbeat(self) -> None:
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._hb_thread.start()

    def stop_heartbeat(self) -> None:
        self._hb_stop.set()
        if self._hb_thread is not None:
            self._hb_thread.join(timeout=1.0)

    def _heartbeat_loop(self) -> None:
        while not self._hb_stop.wait(self.heartbeat_interval):
            with self._lock:
                req = self._requests_made
                cache = len(self._cache)
                idle = time.time() - self._last_activity
                label = self._last_activity_label
            elapsed = time.time() - self._started_at
            sys.stderr.write(
                f"  💓 alive {elapsed:5.1f}s | requests {req}/{self.max_requests} | "
                f"cache {cache} | idle {idle:4.1f}s | last: {label}\n"
            )
            sys.stderr.flush()

    def _touch(self, label: str) -> None:
        with self._lock:
            self._last_activity = time.time()
            self._last_activity_label = label

    # ---------------- публичный API ----------------
    def get(self, item_id: str) -> PriceInfo:
        with self._lock:
            hit = self._cache.get(item_id)
            if hit and time.time() - hit[1] < self.ttl:
                return hit[0]

        info = self._fetch(item_id)
        with self._lock:
            self._cache[item_id] = (info, time.time())
        return info

    def prefetch(
        self,
        item_ids: Iterable[str],
        workers: int = 4,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> None:
        unique = list({i for i in item_ids if i})
        todo = [i for i in unique if not self._is_cached(i)]
        total = len(todo)
        if not total:
            return
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self.get, iid): iid for iid in todo}
            for fut in as_completed(futures):
                iid = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    if self.verbose:
                        sys.stderr.write(f"  ! fail {iid}: {e}\n")
                done += 1
                if progress:
                    progress(done, total, iid)

    def stats(self) -> dict:
        with self._lock:
            return {
                "requests": self._requests_made,
                "cache_size": len(self._cache),
                "budget_exhausted": self._requests_made >= self.max_requests,
                "max_requests": self.max_requests,
                "elapsed": time.time() - self._started_at,
            }

    # ---------------- внутреннее ----------------
    def _is_cached(self, item_id: str) -> bool:
        with self._lock:
            hit = self._cache.get(item_id)
            return bool(hit and time.time() - hit[1] < self.ttl)

    def _http_get(self, url: str, params: dict, label: str) -> requests.Response | None:
        with self._lock:
            if self._requests_made >= self.max_requests:
                if self.verbose:
                    sys.stderr.write(f"  ! budget exhausted, skip {label}\n")
                return None
            self._requests_made += 1
        self._touch(label)

        t0 = time.time()
        try:
            r = self._session.get(url, params=params, timeout=20)
        except requests.RequestException as e:
            if self.verbose:
                dt = time.time() - t0
                sys.stderr.write(f"  [GET] {label:22s} → ERR ({dt:.2f}s) "
                                 f"{type(e).__name__}\n")
            return None

        if self.verbose:
            dt = time.time() - t0
            sys.stderr.write(f"  [GET] {label:22s} → {r.status_code} ({dt:.2f}s)\n")
        return r

    def _fetch(self, item_id: str) -> PriceInfo:
        if self.use_history:
            median, samples = self._history_median(item_id)
            if median is not None:
                return PriceInfo(item_id, median, "history", samples)

        if self.fallback_to_lots:
            min_lot, lots_count = self._min_lot_price(item_id)
            if min_lot is not None:
                return PriceInfo(item_id, min_lot, "lots", lots_count)

        return PriceInfo(item_id, None, "none", 0)
    
    def get_history(self, item_id: str, limit: int | None = None) -> list[dict]:
        """
        Сырые сделки из /history.
        Возвращает [{price, amount, [time]}, ...] или [] при ошибке.
        """
        limit = limit if limit is not None else self.history_limit
        url = f"{EAPI_BASE}/{self.region}/auction/{item_id}/history"
        r = self._http_get(url, {"limit": limit}, f"{item_id}/history")
        if r is None or r.status_code != 200:
            return []
        try:
            data = r.json()
        except ValueError:
            return []
        return data.get("prices") or data.get("lots") or []

    def _history_median(self, item_id: str) -> tuple[float | None, int]:
        url = f"{EAPI_BASE}/{self.region}/auction/{item_id}/history"
        r = self._http_get(url, {"limit": self.history_limit}, f"{item_id}/history")
        if r is None or r.status_code != 200:
            return None, 0
        try:
            data = r.json()
        except ValueError:
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
        r = self._http_get(url, {"limit": self.lots_limit, "additional": "true"},
                           f"{item_id}/lots")
        if r is None or r.status_code != 200:
            return None, 0
        try:
            data = r.json()
        except ValueError:
            return None, 0

        lots = data.get("lots") or data.get("prices") or []
        unit_prices = []
        for lot in lots:
            amount = lot.get("amount", 0)
            price = lot.get("buyoutPrice") or lot.get("price")
            if amount > 0 and price and price > 0:
                unit_prices.append(price / amount)
        if not unit_prices:
            return None, 0
        return min(unit_prices), len(unit_prices)


@contextmanager
def phase(name: str, label_width: int = 40):
    """Печатает '▶ name ... ✓ X.Xs' в stderr."""
    t0 = time.time()
    dots = "." * max(3, label_width - len(name))
    sys.stderr.write(f"▶ {name} {dots} ")
    sys.stderr.flush()
    try:
        yield
    finally:
        dt = time.time() - t0
        sys.stderr.write(f"✓ {dt:.1f}s\n")
        sys.stderr.flush()