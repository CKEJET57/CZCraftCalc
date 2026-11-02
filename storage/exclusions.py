"""
storage/exclusions.py — управление исключениями (нулевая стоимость).

Файл: database/exclusions.json
Формат: {"items": ["7rp7", "404p"]}
"""

import json

from config import EXCLUSIONS_FILE


def load_exclusions() -> set[str]:
    if not EXCLUSIONS_FILE.exists():
        return set()
    try:
        with EXCLUSIONS_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return set()
    items = data.get("items", []) if isinstance(data, dict) else data
    return {str(i) for i in items if i}


def save_exclusions(items: set[str]) -> None:
    EXCLUSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with EXCLUSIONS_FILE.open("w", encoding="utf-8") as f:
        json.dump({"items": sorted(items)}, f, ensure_ascii=False, indent=2)


def add_exclusions(items: set[str]) -> set[str]:
    current = load_exclusions()
    current.update(items)
    save_exclusions(current)
    return current


def remove_exclusions(items: set[str]) -> set[str]:
    current = load_exclusions()
    current -= items
    save_exclusions(current)
    return current


def clear_exclusions() -> None:
    save_exclusions(set())