"""Сериализация dataclass-результатов в JSON-совместимые dict."""
from __future__ import annotations

from core.analysis import BatchResult, HistoryResult
from services.craft import CostResult, IngredientCost, RecipeAnalysis


def _serialize_cost_result(cr: CostResult, max_depth: int = 5,
                           current: int = 0) -> dict:
    d = {
        "item_id": cr.item_id,
        "amount": cr.amount,
        "cost": cr.cost,
        "source": cr.source,
        "unit_price": cr.unit_price,
        "market_cost": cr.market_cost,
        "craft_cost": cr.craft_cost,
        "craft_runs": cr.craft_runs,
        "craft_yield": cr.craft_yield,
        "ingredients_cost": cr.ingredients_cost,
        "energy_cost": cr.energy_cost,
        "why": cr.why,
    }
    if cr.children:
        if current < max_depth:
            d["children"] = [
                _serialize_cost_result(c, max_depth, current + 1)
                for c in cr.children
            ]
        else:
            d["children_count"] = len(cr.children)
    return d


def _serialize_ingredient(ing: IngredientCost) -> dict:
    return {
        "item_id": ing.item_id,
        "name": ing.name,
        "amount": ing.amount,
        "unit_price": ing.unit_price,
        "total_price": ing.total_price,
        "source": ing.source,
        "craft_path": (
            _serialize_cost_result(ing.craft_path)
            if ing.craft_path else None
        ),
    }


def _serialize_analysis(a: RecipeAnalysis) -> dict:
    return {
        "result_item_id": a.result_item_id,
        "result_name": a.result_name,
        "result_amount": a.result_amount,
        "category": a.category_ru,
        "subcategory": a.subcategory_ru,
        "bench": a.recipe.get("bench"),
        "requirements": a.recipe.get("requirements", {}),
        "ingredients": [_serialize_ingredient(i) for i in a.ingredients],
        "ingredients_cost": a.ingredients_cost,
        "energy": a.energy,
        "energy_cost": a.energy_cost,
        "total_cost": a.total_cost,
        "revenue_gross": a.result_revenue_gross,
        "fee_pct": a.fee_pct,
        "fee_amount": a.fee_amount,
        "revenue_net": a.result_revenue_net,
        "profit": a.profit,
        "margin_pct": a.margin_pct,
        "missing_ingredients": a.missing_ingredients,
        "missing_energy": a.missing_energy,
        "partial": a.partial,
        "excluded_summary": a.excluded_summary,
        "required_total": {
            k: {"amount": v[0], "source": v[1]}
            for k, v in a.required_total.items()
        },
        "full_tree": {
            k: {"amount": v[0], "source": v[1]}
            for k, v in a.full_tree.items()
        },
    }


def serialize_recipe_list(analyses: list[RecipeAnalysis]) -> list[dict]:
    return [_serialize_analysis(a) for a in analyses]


def serialize_batch(result: BatchResult) -> dict:
    return {
        "total_analyzed": result.total_analyzed,
        "with_full_price": result.with_full_price,
        "without_data": result.without_data,
        "top_n": result.top_n,
        "sort": result.sort,
        "per_category": result.per_category,
        "sections": [
            {
                "category_id": sec.category_id,
                "category_name": sec.category_name,
                "items": [_serialize_analysis(a) for a in sec.items],
            }
            for sec in result.sections
        ],
    }


def serialize_history(result: HistoryResult) -> dict:
    d = {
        "item_id": result.item_id,
        "item_name": result.item_name,
        "deals": result.deals,
        "stats": result.stats,
        "page": result.page,
        "page_size": result.page_size,
        "total_pages": result.total_pages,
    }
    if result.raw_sample is not None:
        d["raw_sample"] = result.raw_sample
    return d
