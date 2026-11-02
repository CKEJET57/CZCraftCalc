"""
services/craft.py — прибыльность одного рецепта.
"""

from dataclasses import dataclass

from services.price import PriceService
from storage.listing import get_item_name


@dataclass
class IngredientCost:
    item_id: str
    name: str
    amount: int
    unit_price: float | None
    total_price: float | None
    source: str


@dataclass
class RecipeAnalysis:
    recipe: dict
    result_item_id: str
    result_name: str
    result_amount: int
    result_revenue: float | None
    ingredients: list[IngredientCost]
    total_cost: float | None
    profit: float | None
    margin_pct: float | None
    missing_ingredients: int
    energy: float
    category_ru: str
    subcategory_ru: str


def analyze_recipe(
    recipe: dict,
    item_index: dict[str, dict],
    price_service: PriceService,
    lang: str = "ru",
) -> RecipeAnalysis:
    result = recipe["result"][0]
    result_item_id = result["item"]
    result_amount = result["amount"]
    result_name = get_item_name(item_index, result_item_id, lang)

    # выручка = цена результата × количество
    result_info = price_service.get(result_item_id)
    revenue = (result_info.unit_price * result_amount
               if result_info.unit_price is not None else None)

    ingredients: list[IngredientCost] = []
    total_cost = 0.0
    missing = 0

    for ing in recipe["ingredients"]:
        info = price_service.get(ing["item"])
        name = get_item_name(item_index, ing["item"], lang)
        if info.unit_price is None:
            total = None
            missing += 1
        else:
            total = info.unit_price * ing["amount"]
            total_cost += total

        ingredients.append(IngredientCost(
            item_id=ing["item"],
            name=name,
            amount=ing["amount"],
            unit_price=info.unit_price,
            total_price=total,
            source=info.source,
        ))

    cat = recipe["category"]["lines"].get(lang) or ""
    subcat = recipe["subcategory"]["lines"].get(lang) or ""

    if missing > 0 or revenue is None:
        return RecipeAnalysis(
            recipe=recipe, result_item_id=result_item_id,
            result_name=result_name, result_amount=result_amount,
            result_revenue=revenue, ingredients=ingredients,
            total_cost=None, profit=None, margin_pct=None,
            missing_ingredients=missing, energy=recipe.get("energy", 0.0),
            category_ru=cat, subcategory_ru=subcat,
        )

    profit = revenue - total_cost
    margin = (profit / total_cost * 100) if total_cost > 0 else None

    return RecipeAnalysis(
        recipe=recipe, result_item_id=result_item_id,
        result_name=result_name, result_amount=result_amount,
        result_revenue=revenue, ingredients=ingredients,
        total_cost=total_cost, profit=profit, margin_pct=margin,
        missing_ingredients=0, energy=recipe.get("energy", 0.0),
        category_ru=cat, subcategory_ru=subcat,
    )