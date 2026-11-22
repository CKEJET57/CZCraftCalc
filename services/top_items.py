"""Получение опубликованного почасового рейтинга предметов."""
from __future__ import annotations

import threading
import time

import requests

from storage.listing import get_item_name

INDEX_URL = (
    "https://raw.githubusercontent.com/CKEJET57/CZCraftCalc/"
    "market-data/database/market/top_items.json"
)
_CACHE_TTL_SECONDS = 60
_cache_lock = threading.Lock()
_cache_payload: dict | None = None
_cache_expires_at = 0.0


def _load_index() -> dict:
    global _cache_payload, _cache_expires_at
    now = time.monotonic()
    with _cache_lock:
        if _cache_payload is not None and now < _cache_expires_at:
            return _cache_payload

        response = requests.get(INDEX_URL, timeout=(5, 20))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("Опубликованный индекс рейтинга имеет неверный формат.")

        _cache_payload = payload
        _cache_expires_at = time.monotonic() + _CACHE_TTL_SECONDS
        return payload


def get_top_items(state, limit: int = 100) -> dict:
    """Возвращает предметы за один общий последний завершённый час."""
    payload = _load_index()
    items = []
    for row in payload["items"][:max(1, min(int(limit), 500))]:
        item_id = str(row.get("item") or "")
        if not item_id:
            continue
        # Старый индекс может содержать предметы, удалённые из каталога крафта.
        if item_id not in state.craftable_index:
            continue
        item = state.item_index.get(item_id)
        if item is None:
            continue
        icon_path = item.get("icon") or ""
        items.append({
            "item_id": item_id,
            "name": get_item_name(state.item_index, item_id, "ru"),
            "color": item.get("color", "DEFAULT"),
            "icon_url": f"/api/static{icon_path}" if icon_path else None,
            "deals": int(row.get("deals") or 0),
            "turnover": float(row.get("turnover") or 0),
            "median_unit": float(row.get("median_unit") or 0),
        })
    return {"hour": payload.get("hour"), "items": items}
