"""Получение рейтинга из локальной копии опубликованных рыночных данных."""
from __future__ import annotations

import json

from services.market_data import INDEX_FILE, market_data_status
from storage.listing import get_item_name


def get_top_items(state, limit: int = 100) -> dict:
    """Возвращает рейтинг из локального индекса; сеть здесь не используется."""
    status = market_data_status()
    if not status["available"]:
        raise RuntimeError("Локальные рыночные данные отсутствуют. Выполните синхронизацию market-data.")
    payload = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    items = []
    for row in payload["items"][:max(1, min(int(limit), 500))]:
        item_id = str(row.get("item") or "")
        if not item_id or item_id not in state.craftable_index:
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
