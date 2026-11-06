"""
storage/listing.py — загрузка и индексирование database/listing.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from config import LISTING_FILE


def load_listing(path: Path | None = None) -> list:
    """Читает JSON-массив листинга. По умолчанию — database/listing.json."""
    path = path or LISTING_FILE
    if not path.exists():
        raise FileNotFoundError(f"Не найден файл базы: {path}")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Ожидался JSON-массив в {path.name}")
    return data


def extract_item_id(item: dict) -> str | None:
    """
    Достаёт itemId из записи listing.
    Пример data: "/items/other/qyvk.json"  →  "qyvk"
    """
    raw = item.get("data")
    if not raw:
        return None
    return Path(raw).stem


def build_item_index(listing: list) -> dict[str, dict]:
    """itemId → запись listing."""
    index: dict[str, dict] = {}
    for item in listing:
        item_id = extract_item_id(item)
        if item_id:
            index[item_id] = item
    return index


def get_item_name(index: dict[str, dict], item_id: str, lang: str = "ru") -> str:
    """Возвращает название предмета по itemId. Если нет — сам itemId."""
    item = index.get(item_id)
    if not item:
        return f"[неизвестный itemId: {item_id}]"

    name_block = item.get("name", {})
    lines = name_block.get("lines", {})
    return (
        lines.get(lang)
        or lines.get("en")
        or lines.get("ru")
        or name_block.get("key")
        or item_id
    )