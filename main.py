"""
main.py — CLI калькулятора крафта.

Примеры:
  python main.py recipe qyvk
  python main.py batch --bench workbench --category ammunition --top 10
  python main.py batch --bench laboratory_table --perk medicine --top 5
"""

import argparse
import sys

import requests

from api.auth import fetch_token
from config import DEFAULT_REGION
from services.craft import RecipeAnalysis, analyze_recipe
from services.price import PriceService
from storage.hideout import (
    filter_recipes, find_recipes_by_result, load_hideout_recipes,
)
from storage.listing import build_item_index, load_listing


# ---------- форматирование ----------
def fmt_price(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f} ₽".replace(",", " ")


def fmt_pct(v: float | None) -> str:
    return f"{v:+.1f}%" if v is not None else "—"


def print_analysis(a: RecipeAnalysis) -> None:
    print(f"\n=== {a.result_name} ×{a.result_amount} ===")
    print(f"  Верстак: {a.recipe['bench']} / {a.category_ru} / {a.subcategory_ru}")
    reqs = a.recipe.get("requirements", {})
    print(f"  Перки: {reqs.get('perks', {})}")
    print(f"  Фичи: {', '.join(reqs.get('features', [])) or '—'}")
    print(f"  Энергия: {a.energy:.0f}")

    print("\n  Ингредиенты:")
    for i in a.ingredients:
        mark = f" [{i.source}]" if i.source != "history" else ""
        print(f"    {i.item_id:6s} {i.name:32s} × {i.amount:3d}  "
              f"× {fmt_price(i.unit_price):>14s} = {fmt_price(i.total_price):>14s}{mark}")

    print(f"\n  💰 Себестоимость: {fmt_price(a.total_cost)}")
    print(f"  💵 Выручка:       {fmt_price(a.result_revenue)}")
    print(f"  📈 Прибыль:       {fmt_price(a.profit)}  ({fmt_pct(a.margin_pct)})")
    if a.missing_ingredients:
        print(f"  ⚠️  Нет цен на {a.missing_ingredients} ингредиент(ов) — расчёт неполный")


# ---------- общий контекст ----------
def build_context(args):
    listing = load_listing()
    item_index = build_item_index(listing)
    hideout = load_hideout_recipes()
    token = fetch_token()["access_token"]
    price_service = PriceService(
        token,
        region=args.region,
        fallback_to_lots=not args.no_fallback,
    )
    return item_index, hideout, price_service


# ---------- команды ----------
def cmd_recipe(args) -> int:
    item_index, hideout, price_service = build_context(args)
    recipes = find_recipes_by_result(hideout, args.item_id)
    if not recipes:
        print(f"Рецепт для «{args.item_id}» не найден.")
        return 1
    print(f"Найдено рецептов: {len(recipes)}")
    for r in recipes:
        print_analysis(analyze_recipe(r, item_index, price_service, lang=args.lang))
    return 0


def cmd_batch(args) -> int:
    item_index, hideout, price_service = build_context(args)
    recipes = filter_recipes(hideout, bench=args.bench,
                             category_id=args.category, perk_id=args.perk)
    if not recipes:
        print("Под фильтр не попал ни один рецепт.")
        return 1
    if len(recipes) > args.max_recipes:
        print(f"⚠️  Найдено {len(recipes)} рецептов, ограничиваю до {args.max_recipes} "
              f"(это ~{args.max_recipes * 5} HTTP-запросов). Увеличь через --max-recipes.")
        recipes = recipes[:args.max_recipes]

    print(f"Анализирую {len(recipes)} рецептов...")
    analyses: list[RecipeAnalysis] = []
    for i, r in enumerate(recipes, 1):
        analyses.append(analyze_recipe(r, item_index, price_service, lang=args.lang))
        sys.stdout.write(f"\r  {i}/{len(recipes)}")
        sys.stdout.flush()
    print()

    full = [a for a in analyses if a.margin_pct is not None]
    partial = [a for a in analyses if a.margin_pct is None]
    print(f"\nС полными ценами: {len(full)}, без данных: {len(partial)}")

    full.sort(key=lambda x: x.margin_pct, reverse=True)

    print(f"\n🏆 ТОП-{args.top} по марже:")
    for a in full[:args.top]:
        print(f"  {fmt_pct(a.margin_pct):>8s}  {a.result_name:36s} "
              f"прибыль {fmt_price(a.profit):>12s}, "
              f"себест. {fmt_price(a.total_cost):>12s}")

    losers = [a for a in full if a.profit < 0]
    if losers:
        print(f"\n💀 Убыточные ({len(losers)}):")
        for a in losers[-5:]:
            print(f"  {fmt_pct(a.margin_pct):>8s}  {a.result_name:36s} "
                  f"убыток {fmt_price(a.profit):>12s}")
    return 0


# ---------- entrypoint ----------
def main() -> int:
    p = argparse.ArgumentParser(description="Stalcraft crafting calculator")
    p.add_argument("--region", default=DEFAULT_REGION)
    p.add_argument("--lang", default="ru")
    p.add_argument("--no-fallback", action="store_true",
                   help="Не использовать /lots, если нет истории")

    sub = p.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("recipe", help="Анализ рецепта по itemId результата")
    p1.add_argument("item_id")
    p1.set_defaults(func=cmd_recipe)

    p2 = sub.add_parser("batch", help="Пакетный анализ по фильтру")
    p2.add_argument("--bench", choices=["workbench", "laboratory_table", "kitchen_table"])
    p2.add_argument("--category", help="ammunition / armor / materials / medicine / ...")
    p2.add_argument("--perk", help="ammunition / engineering / cooking / ...")
    p2.add_argument("--top", type=int, default=10)
    p2.add_argument("--max-recipes", type=int, default=30)
    p2.set_defaults(func=cmd_batch)

    args = p.parse_args()
    try:
        return args.func(args)
    except requests.HTTPError as e:
        print(f"[HTTP ERROR] {e.response.status_code}: {e.response.text[:300]}")
        return 1
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())