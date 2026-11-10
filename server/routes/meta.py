"""
server/routes/meta.py — справочные эндпоинты: items, categories, help,
item-details, health.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from fastapi import APIRouter, HTTPException

from cli.help import TOPICS, print_operations, print_topic
from config import DB_DIR
from server.deps import get_state
from storage.hideout import extract_category_id, find_recipes_by_result
from storage.listing import get_item_name

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.get("/items")
def list_items(
    lang: str = "ru",
    q: str | None = None,
    craftable: bool = False,
) -> list[dict]:
    """
    Список предметов.
    - craftable=true → только те, что есть в listing_craft.json
    - q=... → фильтр по названию (регистронезависимый)
    """
    state = get_state()
    index = state.craftable_index if craftable else state.item_index

    q_low = q.lower() if q else None
    out: list[dict] = []
    for item_id in index:
        name = get_item_name(index, item_id, lang)
        if q_low and q_low not in name.lower():
            continue
        out.append({"item_id": item_id, "name": name})

    out.sort(key=lambda x: x["name"])
    return out


@router.get("/categories")
def list_categories(lang: str = "ru") -> list[dict]:
    state = get_state()
    cats: dict[str, str] = {}
    for r in state.hideout["recipes"]:
        cid = extract_category_id(r) or "other"
        if cid not in cats:
            cats[cid] = r["category"]["lines"].get(lang) or cid
    return [{"id": k, "name": v} for k, v in cats.items()]


@router.get("/recipe-ingredients/{item_id}")
def recipe_ingredients(item_id: str, lang: str = "ru") -> dict:
    """Прямые ингредиенты рецепта (для UI/управления)."""
    state = get_state()
    recipes = find_recipes_by_result(state.hideout, item_id)
    if not recipes:
        raise HTTPException(404, f"Рецепт {item_id} не найден")

    ing_ids: set[str] = set()
    for r in recipes:
        for ing in r["ingredients"]:
            ing_ids.add(ing["item"])

    return {
        "item_id": item_id,
        "ingredients": [
            {
                "item_id": i,
                "name": get_item_name(state.item_index, i, lang),
            }
            for i in sorted(
                ing_ids,
                key=lambda x: get_item_name(state.item_index, x, lang),
            )
        ],
    }


@router.get("/item-details/{item_id}")
def get_item_details(item_id: str, lang: str = "ru") -> dict:
    state = get_state()
    item = state.item_index.get(item_id)
    if not item:
        raise HTTPException(404, f"Предмет {item_id} не найден в listing")

    data_path = item.get("data", "")
    icon_path = item.get("icon", "")
    icon_url = f"/api/static{icon_path}" if icon_path else None
    category = item.get("category", "") # <-- Берем категорию (например, armor/combat)

    blocks_out = []

    if data_path:
        file_path = DB_DIR / data_path.lstrip("/")
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                def get_text(obj):
                    if obj is None: return ""
                    if isinstance(obj, (str, int, float)): return str(obj)
                    if isinstance(obj, dict):
                        if lang in obj: return str(obj[lang])
                        if "ru" in obj: return str(obj["ru"])
                        if "en" in obj: return str(obj["en"])
                        if "lines" in obj:
                            lines = obj["lines"]
                            return lines.get(lang) or lines.get("ru") or lines.get("en") or ""
                        if "text" in obj:
                            return get_text(obj["text"])
                    return str(obj)

                def parse_list_block(block_data):
                    b_title = get_text(block_data.get("title"))
                    elements = []
                    for el in block_data.get("elements", []):
                        el_type = el.get("type")
                        
                        if el_type == "text":
                            val = get_text(el.get("text"))
                            if val:
                                elements.append({"type": "text", "name": "", "value": val, "nameColor": None, "valueColor": None})
                        elif el_type in ("numeric", "key-value", "range"):
                            name = get_text(el.get("name") or el.get("key"))
                            formatted = el.get("formatted", {})
                            
                            if formatted and "value" in formatted:
                                val = get_text(formatted["value"])
                                name_color = formatted.get("nameColor")
                                val_color = formatted.get("valueColor")
                            else:
                                val = get_text(el.get("value"))
                                name_color = None
                                val_color = None

                            if name and val:
                                elements.append({
                                    "type": el_type,
                                    "name": name,
                                    "value": val,
                                    "nameColor": name_color,
                                    "valueColor": val_color,
                                })
                    return {"type": "list", "title": b_title, "elements": elements}

                for block in data.get("infoBlocks", []):
                    b_type = block.get("type")

                    if b_type == "list":
                        parsed = parse_list_block(block)
                        if parsed["elements"]:
                            blocks_out.append(parsed)

                    elif b_type == "grouped":
                        for sub_block in block.get("detailed", []):
                            parsed = parse_list_block(sub_block)
                            if parsed["elements"]:
                                blocks_out.append(parsed)

                    elif b_type == "text":
                        # Заменяем литеральные \n на настоящие переносы строк
                        text_val = get_text(block.get("text")).replace("\\n", "\n")
                        b_title = get_text(block.get("title"))
                        if text_val:
                            blocks_out.append({"type": "text", "title": b_title, "text": text_val})

            except Exception as e:
                print(f"Error parsing {item_id}: {e}")

    return {
        "color": item.get("color", "DEFAULT"),
        "status": item.get("status", {}).get("state", "NONE"),
        "category": category, # <-- Отдаем на фронт
        "icon_url": icon_url,
        "blocks": blocks_out,
    }


@router.get("/help")
def help_root() -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_operations()
    return {"text": buf.getvalue(), "topics": list(TOPICS.keys())}


@router.get("/help/{topic}")
def help_topic(topic: str) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = print_topic(topic)
    if not ok:
        raise HTTPException(404, f"Тема «{topic}» не найдена")
    return {"topic": topic, "text": buf.getvalue()}