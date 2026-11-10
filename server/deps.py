"""
server/deps.py — синглтон-состояние процесса API.
"""
from __future__ import annotations

import threading
import time

from api.auth import fetch_token
from config import LISTING_CRAFT_FILE
from core.context import AnalysisContext
from services.craft import CraftCalculator
from services.price import PriceService
from storage.hideout import load_hideout_recipes
from storage.listing import build_item_index, load_listing


class AppState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._item_index: dict | None = None
        self._craftable_index: dict | None = None
        self._hideout: dict | None = None
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._price_services: dict[str, PriceService] = {}

    def _ensure_data(self) -> None:
        if self._item_index is None:
            listing = load_listing()
            self._item_index = build_item_index(listing)
            
            try:
                craft_listing = load_listing(LISTING_CRAFT_FILE)
                self._craftable_index = build_item_index(craft_listing)
            except Exception:
                self._craftable_index = self._item_index

            self._hideout = load_hideout_recipes()

    @property
    def item_index(self) -> dict:
        self._ensure_data()
        assert self._item_index is not None
        return self._item_index

    @property
    def craftable_index(self) -> dict:
        self._ensure_data()
        assert self._craftable_index is not None
        return self._craftable_index

    @property
    def hideout(self) -> dict:
        self._ensure_data()
        assert self._hideout is not None
        return self._hideout

    def _get_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token
            data = fetch_token()
            self._token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 3600)
            return self._token

    def invalidate_token(self) -> None:
        with self._lock:
            self._token = None
            self._token_expires_at = 0.0
            for svc in self._price_services.values():
                svc.close()
            self._price_services.clear()

    # ОБНОВЛЕННЫЙ МЕТОД
    def get_price_service(self, region: str, *, no_history: bool = False, use_local: bool = False) -> PriceService:
        key = f"{region}|{'lots' if no_history else 'history'}|{'local' if use_local else 'online'}"
        with self._lock:
            svc = self._price_services.get(key)
            if svc is not None:
                return svc
            token = self._get_token()
            svc = PriceService(
                token, region=region,
                use_history=not no_history,
                max_requests=10_000_000,
                heartbeat=False, 
                verbose=False,
                use_local=use_local, # <-- ПЕРЕДАЕМ СЮДА
            )
            self._price_services[key] = svc
            return svc

    def build_context(self, opts) -> AnalysisContext:
        exclusions = set()
        if opts.exclude:
            exclusions.update(
                x.strip() for x in opts.exclude.split(",") if x.strip()
            )
            
        # Читаем флаг из opts безопасно
        use_local = getattr(opts, 'use_local_data', False)
        
        price_service = self.get_price_service(
            opts.region, no_history=opts.no_history, use_local=use_local
        )
        craft_calc = None
        if opts.recursive:
            craft_calc = CraftCalculator(
                self.hideout, price_service,
                max_depth=opts.max_depth, exclusions=exclusions,
            )
        return AnalysisContext(
            item_index=self.item_index,
            hideout=self.hideout,
            price_service=price_service,
            craft_calc=craft_calc,
            exclusions=exclusions,
        )

    def shutdown(self) -> None:
        with self._lock:
            for svc in self._price_services.values():
                svc.close()
            self._price_services.clear()


_state: AppState | None = None

def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
    return _state