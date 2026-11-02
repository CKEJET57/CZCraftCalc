"""
main.py — CLI калькулятора крафта.

v4: --explain / --explain-tree / --ignore-missing.
"""

import argparse
import sys
import time

import requests

from cli.help import print_operations, print_topic, print_unknown_topic
from api.auth import fetch_token
from config import DEFAULT_REGION, ENERGY_ITEM_ID
from services.craft import (
    CraftCalculator, IngredientCost, RecipeAnalysis, analyze_recipe,
)
from services.price import PriceService, phase
from storage.hideout import (
    filter_recipes, find_recipes_by_result, load_hideout_recipes,
)
from storage.listing import build_item_index, get_item_name, load_listing

# ---------- справочник ----------
def cmd_help(args) -> int:
    topic = getattr(args, "topic", None)
    if not topic:
        print_operations()
        return 0
    if not print_topic(topic):
        print_unknown_topic(topic)
        return 1
    return 0

# ---------- форматирование ----------
def fmt_price(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{round(v):,} ₽".replace(",", " ")


def fmt_pct(v: float | None) -> str:
    return f"{v:+.1f}%" if v is not None else "—"


def print_ingredient_line(ing: IngredientCost, indent: int = 2,
                          explain: bool = False) -> None:
    pad = " " * indent
    tag = {"market": "рынок", "craft": "крафт", "none": "нет"}[ing.source]
    line = (f"{pad}{ing.item_id:6s} {ing.name:30s} × {ing.amount:3d}  "
            f"[{tag:6s}]  × {fmt_price(ing.unit_price):>12s} = "
            f"{fmt_price(ing.total_price):>12s}")
    if explain and ing.craft_path and ing.craft_path.why:
        line += f"   ← {ing.craft_path.why}"
    print(line)


def print_ingredient_tree(ing, item_index, indent=2, max_depth_display=2,
                          current=0, explain=False) -> None:
    print_ingredient_line(ing, indent, explain=explain)
    if ing.craft_path and ing.craft_path.children and current < max_depth_display:
        cp = ing.craft_path
        energy_note = ""
        if cp.energy_cost and cp.energy_cost > 0:
            energy_note = f", энергия {fmt_price(cp.energy_cost)}"
        print(f"{' ' * (indent + 2)}↳ крафт: {cp.craft_runs}× "
              f"(выход {cp.craft_yield}){energy_note}")
        for child in cp.children:
            child_ing = IngredientCost(
                item_id=child.item_id,
                name=get_item_name(item_index, child.item_id),
                amount=child.amount, unit_price=child.unit_price,
                total_price=child.cost, source=child.source,
                craft_path=child,
            )
            print_ingredient_tree(child_ing, item_index,
                                  indent + 4, max_depth_display,
                                  current + 1, explain=explain)


def print_analysis(a: RecipeAnalysis, item_index: dict[str, dict],
                   craft_calc: CraftCalculator | None = None,
                   explain: bool = False,
                   explain_tree: bool = False) -> None:
    print(f"\n=== {a.result_name} ×{a.result_amount} ===")
    print(f"  Верстак: {a.recipe['bench']} / {a.category_ru} / {a.subcategory_ru}")
    reqs = a.recipe.get("requirements", {})
    print(f"  Перки: {reqs.get('perks', {})}")
    print(f"  Фичи: {', '.join(reqs.get('features', [])) or '—'}")

    print("\n  Ингредиенты:")
    for i in a.ingredients:
        print_ingredient_tree(i, item_index, explain=explain)

    # --explain-tree: почему не удалось
    if explain_tree:
        missing = [i for i in a.ingredients if i.source == "none"]
        if missing:
            print("\n  🔎 Диагностика missing:")
            for m in missing:
                if craft_calc is not None:
                    probs = craft_calc.explain_missing(m.item_id)
                    if probs:
                        print(f"    {m.item_id} ({m.name}) — рецепты требуют "
                              f"без-ценовые: {', '.join(probs)}")
                    else:
                        print(f"    {m.item_id} ({m.name}) — нет цены и "
                              f"нет рабочего рецепта")
                else:
                    print(f"    {m.item_id} ({m.name}) — нет цены на рынке "
                          f"(без --recursive проверить глубже нельзя)")

    # себестоимость
    partial_note = " (частично, ⚠️ ignore-missing)" if a.partial else ""
    print(f"\n  💰 Ингредиенты:   {fmt_price(a.ingredients_cost)}{partial_note}")
    if a.energy_cost is not None:
        j_count = a.energy / 5000 if a.energy > 0 else 0
        print(f"  ⚡ Энергия:       {a.energy:.0f} "
              f"({fmt_price(a.energy_cost)}, ≈{j_count:.2f}× {ENERGY_ITEM_ID})")
    else:
        print(f"  ⚡ Энергия:       {a.energy:.0f} — ⚠️ нет цены на {ENERGY_ITEM_ID}")

    print(f"  💰 Себестоимость: {fmt_price(a.total_cost)}")
    print(f"  💵 Выручка брутто: {fmt_price(a.result_revenue_gross)}")
    print(f"  💸 Комиссия ({a.fee_pct:.1f}%): -{fmt_price(a.fee_amount)}")
    print(f"  💵 Выручка нетто: {fmt_price(a.result_revenue_net)}")
    print(f"  📈 Прибыль:       {fmt_price(a.profit)}  ({fmt_pct(a.margin_pct)})"
          + ("  ⚠️ приблизительно" if a.partial else ""))
    if a.missing_ingredients:
        print(f"  ⚠️  Нет цен на {a.missing_ingredients} ингредиент(ов)")
    if a.missing_energy:
        print(f"  ⚠️  Нет цены на {ENERGY_ITEM_ID} — энергия не учтена")


# ---------- контекст ----------
def build_context(args):
    with phase("Загрузка listing + рецептов"):
        listing = load_listing()
        item_index = build_item_index(listing)
        hideout = load_hideout_recipes()

    with phase("OAuth: получение токена"):
        token = fetch_token()["access_token"]

    price_service = PriceService(
        token,
        region=args.region,
        fallback_to_lots=not args.no_fallback,
        use_history=not args.no_history,
        max_requests=args.max_requests,
        heartbeat=not args.no_heartbeat,
        verbose=args.verbose,
    )
    craft_calc = None
    if args.recursive:
        craft_calc = CraftCalculator(hideout, price_service, max_depth=args.max_depth)
    return item_index, hideout, price_service, craft_calc


def _direct_items(recipes: list[dict]) -> set[str]:
    items = {ENERGY_ITEM_ID}
    for r in recipes:
        for res in r.get("result", []):
            items.add(res["item"])
        for ing in r.get("ingredients", []):
            items.add(ing["item"])
    return items


def _prefetch(price_service, craft_calc, recipes, recursive: bool,
              workers: int, item_index: dict) -> None:
    if craft_calc is not None:
        items = (craft_calc.collect_tree_items(recipes) if recursive
                 else _direct_items(recipes))
    else:
        items = _direct_items(recipes)
    todo = [i for i in items if not price_service._is_cached(i)]
    if not todo:
        print(f"→ Все {len(items)} itemId уже в кэше")
        return
    label = f"Prefetch цен ({len(todo)} itemId, workers={workers})"
    print()
    with phase(label, label_width=55):
        def _progress(done, total, current_id):
            name = get_item_name(item_index, current_id)
            sys.stdout.write(f"\r   [{done:3d}/{total:3d}] {name[:40]:40s}")
            sys.stdout.flush()
        price_service.prefetch(todo, workers=workers, progress=_progress)
    print()


def _print_stats(price_service, craft_calc) -> None:
    st = price_service.stats()
    print(f"\n📊 API: requests={st['requests']}/{st['max_requests']}  "
          f"cache={st['cache_size']}  elapsed={st['elapsed']:.1f}s")
    if craft_calc is not None:
        cs = craft_calc.resolve_stats()
        print(f"🧮 Resolve: calls={cs['resolve_calls']}  "
              f"cache_hits={cs['cache_hits']}  memo={cs['memo_size']}")
    if st["budget_exhausted"]:
        print("⚠️  Бюджет запросов исчерпан — часть цен не получена.")


# ---------- команды ----------
def cmd_recipe(args) -> int:
    item_index, hideout, price_service, craft_calc = build_context(args)
    recipes = find_recipes_by_result(hideout, args.item_id)
    if not recipes:
        print(f"Рецепт для «{args.item_id}» не найден.")
        return 1
    print(f"Найдено рецептов: {len(recipes)}")

    _prefetch(price_service, craft_calc, recipes, args.recursive,
              args.workers, item_index)

    for r in recipes:
        analysis = analyze_recipe(
            r, item_index, price_service,
            fee_pct=args.fee, craft_calc=craft_calc, lang=args.lang,
            ignore_missing=args.ignore_missing,
        )
        print_analysis(analysis, item_index, craft_calc=craft_calc,
                       explain=args.explain, explain_tree=args.explain_tree)

    _print_stats(price_service, craft_calc)
    price_service.stop_heartbeat()
    return 0


def cmd_batch(args) -> int:
    item_index, hideout, price_service, craft_calc = build_context(args)
    recipes = filter_recipes(hideout, bench=args.bench,
                             category_id=args.category, perk_id=args.perk)
    if not recipes:
        print("Под фильтр не попал ни один рецепт.")
        price_service.stop_heartbeat()
        return 1
    if len(recipes) > args.max_recipes:
        print(f"⚠️  Ограничиваю до {args.max_recipes} рецептов.")
        recipes = recipes[:args.max_recipes]

    _prefetch(price_service, craft_calc, recipes, args.recursive,
              args.workers, item_index)

    print(f"\n▶ Анализ {len(recipes)} рецептов"
          f"{' [recursive]' if args.recursive else ''}")
    t0 = time.time()
    analyses: list[RecipeAnalysis] = []
    for i, r in enumerate(recipes, 1):
        name = get_item_name(item_index, r["result"][0]["item"])
        sys.stdout.write(f"\r   [{i:3d}/{len(recipes):3d}] {name[:36]:36s} "
                         f"({time.time()-t0:5.1f}s)")
        sys.stdout.flush()
        analyses.append(analyze_recipe(
            r, item_index, price_service,
            fee_pct=args.fee, craft_calc=craft_calc, lang=args.lang,
            ignore_missing=args.ignore_missing,
        ))
    print(f"\r   ✓ готово за {time.time()-t0:.1f}s" + " " * 40)

    full = [a for a in analyses if a.margin_pct is not None]
    partial = [a for a in analyses if a.margin_pct is None]
    print(f"\nС полными ценами: {len(full)}, без данных: {len(partial)}")

    key = (lambda x: x.margin_pct) if args.sort == "margin" else (lambda x: x.profit)
    full.sort(key=key, reverse=True)

    print(f"\n🏆 ТОП-{args.top} по {args.sort}:")
    for a in full[:args.top]:
        mark = " (⚠️ partial)" if a.partial else ""
        print(f"  {fmt_pct(a.margin_pct):>8s}  {a.result_name:36s} "
              f"прибыль {fmt_price(a.profit):>12s}, "
              f"себест. {fmt_price(a.total_cost):>12s}{mark}")

    losers = [a for a in full if a.profit < 0]
    if losers:
        print(f"\n💀 Убыточные ({len(losers)}):")
        for a in losers[-5:]:
            print(f"  {fmt_pct(a.margin_pct):>8s}  {a.result_name:36s} "
                  f"убыток {fmt_price(a.profit):>12s}")

    _print_stats(price_service, craft_calc)
    price_service.stop_heartbeat()
    return 0


# ---------- entrypoint ----------
def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--region", default=DEFAULT_REGION)
    p.add_argument("--lang", default="ru")
    p.add_argument("--fee", type=float, default=5.0,
                   help="Комиссия аукциона, %% (по умолчанию 5)")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--max-depth", type=int, default=12)
    p.add_argument("--no-fallback", action="store_true")
    p.add_argument("--no-history", action="store_true")
    p.add_argument("--max-requests", type=int, default=500)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--no-heartbeat", action="store_true")
    p.add_argument("--verbose", action="store_true")
    # NEW
    p.add_argument("--explain", action="store_true",
                   help="Показывать, почему выбран рынок/крафт")
    p.add_argument("--explain-tree", action="store_true",
                   help="Показать, из-за каких базовых предметов нет цены")
    p.add_argument("--ignore-missing", action="store_true",
                   help="Считать приблизительно, если не хватает цен")


def main() -> int:
    # без аргументов — сразу справочник, а не сухой usage
    if len(sys.argv) == 1:
        print_operations()
        return 0
    
    p = argparse.ArgumentParser(description="Stalcraft crafting calculator")
    sub = p.add_subparsers(dest="command", required=True)

    p_help = sub.add_parser("help", help="Справочник команд и тем")
    p_help.add_argument(
        "topic", nargs="?", default=None,
        help="examples | prices | energy | fee | recursive | troubleshoot | all",
    )
    p_help.set_defaults(func=cmd_help)
    
    p1 = sub.add_parser("recipe", help="Анализ рецептов по itemId результата")
    p1.add_argument("item_id")
    add_common_args(p1)
    p1.set_defaults(func=cmd_recipe)

    p2 = sub.add_parser("batch", help="Пакетный анализ по фильтру")
    p2.add_argument("--bench", choices=["workbench", "laboratory_table", "kitchen_table"])
    p2.add_argument("--category")
    p2.add_argument("--perk")
    p2.add_argument("--top", type=int, default=10)
    p2.add_argument("--max-recipes", type=int, default=30)
    p2.add_argument("--sort", choices=["margin", "profit"], default="margin")
    add_common_args(p2)
    p2.set_defaults(func=cmd_batch)

    args = p.parse_args()
    try:
        return args.func(args)
    except requests.HTTPError as e:
        print(f"\n[HTTP ERROR] {e.response.status_code}: {e.response.text[:300]}")
        return 1
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        return 130
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())