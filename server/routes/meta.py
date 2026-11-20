"""
FastAPI-адаптер справочных эндпоинтов.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from fastapi import APIRouter, HTTPException

from cli.help import TOPICS, print_operations, print_topic
from config import DB_DIR
from server.deps import get_state
from services.catalog import (
    get_item_details as catalog_item_details,
    get_item_variants as catalog_item_variants,
    health as catalog_health,
    list_categories as catalog_categories,
    list_items as catalog_items,
)
from storage.hideout import find_recipes_by_result
from storage.listing import get_item_name

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    return catalog_health()


@router.get("/items")
def list_items(lang: str = "ru", q: str | None = None, craftable: bool = False) -> list[dict]:
    return catalog_items(get_state(), lang=lang, q=q, craftable=craftable)


@router.get("/categories")
def list_categories(lang: str = "ru") -> list[dict]:
    return catalog_categories(get_state(), lang=lang)


@router.get("/recipe-ingredients/{item_id}")
def recipe_ingredients(item_id: str, lang: str = "ru") -> dict:
    state = get_state()
    recipes = find_recipes_by_result(state.hideout, item_id)
    if not recipes:
        raise HTTPException(404, f"Рецепт {item_id} не найден")
    ing_ids = {ing["item"] for recipe in recipes for ing in recipe["ingredients"]}
    return {
        "item_id": item_id,
        "ingredients": [
            {"item_id": item_id, "name": get_item_name(state.item_index, item_id, lang)}
            for item_id in sorted(ing_ids, key=lambda x: get_item_name(state.item_index, x, lang))
        ],
    }


@router.get("/item-details/{item_id}")
def get_item_details(item_id: str, lang: str = "ru") -> dict:
    try:
        return catalog_item_details(get_state(), item_id, lang)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/item-details/{item_id}/variants")
def get_item_variants(item_id: str, lang: str = "ru") -> dict:
    try:
        return catalog_item_variants(get_state(), item_id, lang)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


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


@router.get("/stats-metadata")
def get_stats_metadata() -> list[dict]:
    stats_file = DB_DIR / "stats.json"
    if not stats_file.exists():
        raise HTTPException(404, "Файл stats.json не найден")
    with open(stats_file, "r", encoding="utf-8") as f:
        return json.load(f)
