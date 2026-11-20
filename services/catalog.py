"""Общие операции каталога предметов без зависимости от HTTP."""
from __future__ import annotations

import json

from config import DB_DIR
from storage.hideout import extract_category_id
from storage.listing import get_item_name


def _get_text(obj, lang: str) -> str:
    if obj is None:
        return ""
    if isinstance(obj, (str, int, float)):
        return str(obj)
    if isinstance(obj, dict):
        if lang in obj:
            return str(obj[lang])
        if "ru" in obj:
            return str(obj["ru"])
        if "en" in obj:
            return str(obj["en"])
        if "lines" in obj:
            lines = obj["lines"]
            return lines.get(lang) or lines.get("ru") or lines.get("en") or ""
        if "text" in obj:
            return _get_text(obj["text"], lang)
    return str(obj)


def _parse_list_block(block_data: dict, lang: str) -> dict:
    title = _get_text(block_data.get("title"), lang)
    elements = []
    for element in block_data.get("elements", []):
        element_type = element.get("type")
        if element_type == "text":
            value = _get_text(element.get("text"), lang)
            if value:
                elements.append({
                    "type": "text", "name": "", "value": value,
                    "nameColor": None, "valueColor": None,
                })
        elif element_type in ("numeric", "key-value", "range"):
            name = _get_text(element.get("name") or element.get("key"), lang)
            formatted = element.get("formatted", {})
            if formatted and "value" in formatted:
                value = _get_text(formatted["value"], lang)
                name_color = formatted.get("nameColor")
                value_color = formatted.get("valueColor")
            else:
                value = _get_text(element.get("value"), lang)
                name_color = value_color = None
            if name and value:
                elements.append({
                    "type": element_type, "name": name, "value": value,
                    "nameColor": name_color, "valueColor": value_color,
                })
    return {"type": "list", "title": title, "elements": elements}


def _parse_blocks(data: dict, lang: str) -> list[dict]:
    result = []
    for block in data.get("infoBlocks", []):
        block_type = block.get("type")
        if block_type == "list":
            parsed = _parse_list_block(block, lang)
            if parsed["elements"]:
                result.append(parsed)
        elif block_type == "grouped":
            for sub_block in block.get("detailed", []):
                parsed = _parse_list_block(sub_block, lang)
                if parsed["elements"]:
                    result.append(parsed)
        elif block_type == "text":
            value = _get_text(block.get("text"), lang).replace("\\n", "\n")
            title = _get_text(block.get("title"), lang)
            if value:
                result.append({"type": "text", "title": title, "text": value})
    return result


def health() -> dict:
    return {"ok": True}


def list_items(state, lang: str = "ru", q: str | None = None, craftable: bool = False) -> list[dict]:
    """Список предметов с необязательным поиском по названию."""
    index = state.craftable_index if craftable else state.item_index
    query = q.lower() if q else None
    result = []
    for item_id in index:
        name = get_item_name(index, item_id, lang)
        if query and query not in name.lower():
            continue
        result.append({"item_id": item_id, "name": name})
    result.sort(key=lambda item: item["name"])
    return result


def list_categories(state, lang: str = "ru") -> list[dict]:
    categories: dict[str, str] = {}
    for recipe in state.hideout["recipes"]:
        category_id = extract_category_id(recipe) or "other"
        if category_id not in categories:
            categories[category_id] = recipe["category"]["lines"].get(lang) or category_id
    return [{"id": key, "name": value} for key, value in categories.items()]


def get_item_details(state, item_id: str, lang: str = "ru") -> dict:
    item = state.item_index.get(item_id)
    if not item:
        raise LookupError(f"Предмет {item_id} не найден в listing")

    data_path = item.get("data", "")
    icon_path = item.get("icon", "")
    icon_url = f"/api/static{icon_path}" if icon_path else None
    blocks = []
    has_variants = False
    max_variant_level = 0

    if data_path:
        file_path = DB_DIR / data_path.lstrip("/")
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    blocks = _parse_blocks(json.load(file), lang)
            except Exception as exc:
                print(f"Error parsing {item_id}: {exc}")

            variants_dir = file_path.parent / "_variants" / item_id
            if variants_dir.is_dir():
                levels = [
                    int(path.stem) for path in variants_dir.glob("*.json")
                    if path.stem.isdigit()
                ]
                if levels:
                    has_variants = True
                    max_variant_level = max(levels)

    return {
        "color": item.get("color", "DEFAULT"),
        "status": item.get("status", {}).get("state", "NONE"),
        "category": item.get("category", ""),
        "icon_url": icon_url,
        "blocks": blocks,
        "has_variants": has_variants,
        "max_variant_level": max_variant_level,
    }


def get_item_variants(state, item_id: str, lang: str = "ru") -> dict:
    item = state.item_index.get(item_id)
    if not item:
        raise LookupError(f"Предмет {item_id} не найден в listing")
    data_path = item.get("data", "")
    if not data_path:
        return {"available": False, "variants": []}

    variants_dir = (DB_DIR / data_path.lstrip("/")).parent / "_variants" / item_id
    if not variants_dir.is_dir():
        return {"available": False, "variants": []}

    files = sorted(
        (path for path in variants_dir.glob("*.json") if path.stem.isdigit()),
        key=lambda path: int(path.stem),
    )
    variants = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as file:
                raw = json.load(file)
            variants.append({
                "level": int(path.stem),
                "blocks": _parse_blocks(raw, lang),
            })
        except Exception as exc:
            print(f"Error parsing variant {path}: {exc}")
    return {"available": bool(variants), "variants": variants}
