"""Анализ рецептов по результату."""
from __future__ import annotations

from services.craft import RecipeAnalysis, analyze_recipe
from storage.hideout import find_recipes_by_result
from core.prefetch import prefetch


def analyze_recipe_by_id(item_id: str, opts, ctx) -> list[RecipeAnalysis]:
    recipes = find_recipes_by_result(ctx.hideout, item_id)
    if not recipes:
        return []
    prefetch(opts, ctx, recipes)
    return [
        analyze_recipe(
            r, ctx.item_index, ctx.price_service,
            fee_pct=opts.fee, craft_calc=ctx.craft_calc, lang=opts.lang,
            ignore_missing=opts.ignore_missing, exclusions=ctx.exclusions,
        )
        for r in recipes
    ]


# ─── batch ────────────────────────────────────────────────────────
