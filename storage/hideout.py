"""
storage/hideout.py — загрузка и фильтрация hideout_recipes.json.
"""

import json

from config import BASE_DIR

HIDEOUT_FILE = BASE_DIR / "database" / "hideout_recipes.json"


def load_hideout_recipes() -> dict:
    if not HIDEOUT_FILE.exists():
        raise FileNotFoundError(f"Не найден файл: {HIDEOUT_FILE}")
    with HIDEOUT_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def extract_category_id(recipe: dict) -> str | None:
    """
    "hideout.benches.categories.ammunition.name" → "ammunition"
    """
    key = recipe.get("category", {}).get("key", "")
    parts = key.split(".")
    if "categories" in parts:
        idx = parts.index("categories")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def find_recipes_by_result(data: dict, item_id: str) -> list[dict]:
    return [
        r for r in data["recipes"]
        if any(x.get("item") == item_id for x in r.get("result", []))
    ]


def filter_recipes(
    data: dict,
    bench: str | None = None,
    category_id: str | None = None,
    perk_id: str | None = None,
) -> list[dict]:
    out = []
    for r in data["recipes"]:
        if bench and r.get("bench") != bench:
            continue
        if category_id and extract_category_id(r) != category_id:
            continue
        if perk_id and perk_id not in r.get("requirements", {}).get("perks", {}):
            continue
        out.append(r)
    return out