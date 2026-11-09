"""Справочные эндпоинты: items, categories, help, health."""
from __future__ import annotations

import io
from contextlib import redirect_stdout

from fastapi import APIRouter, HTTPException

from cli.help import TOPICS, print_operations, print_topic
from server.deps import get_state
from storage.hideout import extract_category_id
from storage.listing import get_item_name

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.get("/items")
def list_items(lang: str = "ru", 
               q: str | None = None, 
               craftable: bool = False) -> list[dict]:
    state = get_state()
    index = state.craftable_index if craftable else state.item_index
    q_low = q.lower() if q else None
    out = []
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
    """Прямые ингредиенты (для управления исключениями)."""
    state = get_state()
    from storage.hideout import find_recipes_by_result
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
            {"item_id": i, "name": get_item_name(state.item_index, i, lang)}
            for i in sorted(ing_ids, key=lambda x: get_item_name(state.item_index, x, lang))
        ],
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