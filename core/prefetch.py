"""Общая подготовка и выполнение предварительной загрузки рыночных цен."""
from __future__ import annotations

from dataclasses import dataclass

from config import ENERGY_ITEM_ID


@dataclass(frozen=True)
class PrefetchPlan:
    """Неизменяемый план: все нужные предметы и отсутствующие в кэше."""

    items: frozenset[str]
    missing: tuple[str, ...]


def collect_prefetch_items(opts, ctx, recipes: list[dict]) -> set[str]:
    """Собирает предметы для загрузки с учётом рекурсивного дерева и исключений."""
    if ctx.craft_calc is not None and opts.recursive:
        return ctx.craft_calc.collect_tree_items(recipes)

    items = set() if ENERGY_ITEM_ID in ctx.exclusions else {ENERGY_ITEM_ID}
    for recipe in recipes:
        for result in recipe.get("result", []):
            items.add(result["item"])
        for ingredient in recipe.get("ingredients", []):
            if ingredient["item"] not in ctx.exclusions:
                items.add(ingredient["item"])
    return items


def build_prefetch_plan(opts, ctx, recipes: list[dict]) -> PrefetchPlan:
    """Формирует единый план загрузки для CLI, HTTP и Desktop."""
    items = collect_prefetch_items(opts, ctx, recipes)
    missing = tuple(item for item in items if not ctx.price_service.is_cached(item))
    return PrefetchPlan(items=frozenset(items), missing=missing)


def execute_prefetch(plan: PrefetchPlan, opts, ctx, progress=None) -> int:
    """Выполняет план и возвращает количество запрошенных предметов."""
    if plan.missing:
        ctx.price_service.prefetch(
            list(plan.missing), workers=opts.workers, progress=progress,
        )
    return len(plan.missing)


def prefetch(opts, ctx, recipes: list[dict], progress=None) -> int:
    """Совместимый интерфейс: собрать план и сразу выполнить загрузку."""
    return execute_prefetch(build_prefetch_plan(opts, ctx, recipes), opts, ctx, progress)
