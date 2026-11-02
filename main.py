"""
main.py — CLI калькулятора крафта + запуск интерактивного меню.

Команды:
  menu                 — интерактивное меню (по умолчанию без аргументов)
  recipe <item_id>     — анализ одного предмета
  batch                — пакетный анализ / топ по категориям
  exclusions <action>  — управление исключениями
  help [topic]         — справка
"""

import argparse
import sys
import time

import requests

from api.auth import fetch_token
from cli.help import print_operations, print_topic, print_unknown_topic
from cli.render import (
    fmt_pct, fmt_price, print_analysis, print_stats, prefetch_prices,
)
from config import DEFAULT_REGION
from services.craft import CraftCalculator, analyze_recipe
from services.price import PriceService, phase
from storage.exclusions import (
    add_exclusions, clear_exclusions, load_exclusions, remove_exclusions,
)
from storage.hideout import (
    extract_category_id, filter_recipes, find_recipes_by_result,
    load_hideout_recipes,
)
from storage.listing import build_item_index, get_item_name, load_listing


# ---------- контекст ----------
def _merge_exclusions(args) -> set[str]:
    items = load_exclusions()
    extra = getattr(args, "exclude", "") or ""
    if extra:
        items.update(x.strip() for x in extra.split(",") if x.strip())
    return items


class Context:
    def __init__(self, item_index, hideout, price_service, craft_calc, exclusions):
        self.item_index = item_index
        self.hideout = hideout
        self.price_service = price_service
        self.craft_calc = craft_calc
        self.exclusions = exclusions


def build_context(args) -> Context:
    with phase("Загрузка listing + рецептов"):
        listing = load_listing()
        item_index = build_item_index(listing)
        hideout = load_hideout_recipes()

    with phase("OAuth: получение токена"):
        token = fetch_token()["access_token"]

    exclusions = _merge_exclusions(args)

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
        craft_calc = CraftCalculator(
            hideout, price_service,
            max_depth=args.max_depth,
            exclusions=exclusions,
        )
    return Context(item_index, hideout, price_service, craft_calc, exclusions)


def _opts_from_args(args) -> dict:
    return {
        "recursive": args.recursive,
        "fee": args.fee,
        "show_ids": args.show_ids,
        "explain": args.explain,
        "explain_tree": args.explain_tree,
        "ignore_missing": args.ignore_missing,
        "lang": args.lang,
        "workers": args.workers,
    }


# ---------- общие функции анализа ----------
def run_recipe(item_id: str, opts: dict, ctx: Context) -> None:
    recipes = find_recipes_by_result(ctx.hideout, item_id)
    if not recipes:
        print(f"Рецепт для «{item_id}» не найден.")
        return
    print(f"Найдено рецептов: {len(recipes)}")
    if ctx.exclusions:
        print(f"Исключений: {len(ctx.exclusions)}")

    prefetch_prices(ctx.price_service, ctx.craft_calc, recipes,
                    opts, ctx.item_index, ctx.exclusions)

    for r in recipes:
        a = analyze_recipe(
            r, ctx.item_index, ctx.price_service,
            fee_pct=opts["fee"], craft_calc=ctx.craft_calc, lang=opts["lang"],
            ignore_missing=opts.get("ignore_missing", False),
            exclusions=ctx.exclusions,
        )
        print_analysis(a, ctx.item_index, craft_calc=ctx.craft_calc,
                       explain=opts.get("explain", False),
                       explain_tree=opts.get("explain_tree", False),
                       show_ids=opts.get("show_ids", False))


# ---------- команды ----------
def cmd_help(args) -> int:
    topic = getattr(args, "topic", None)
    if not topic:
        print_operations()
        return 0
    if not print_topic(topic):
        print_unknown_topic(topic)
        return 1
    return 0


def cmd_menu(args) -> int:
    from cli.menu import run_menu
    return run_menu()


def cmd_exclusions(args) -> int:
    action = getattr(args, "action", None)
    if action == "list":
        items = load_exclusions()
        if not items:
            print("Исключений нет.")
            return 0
        item_index = build_item_index(load_listing())
        print(f"Исключено предметов: {len(items)} "
              f"(database/exclusions.json)")
        for iid in sorted(items):
            print(f"  {iid:8s} {get_item_name(item_index, iid)}")
        return 0
    if action == "add":
        items = add_exclusions(set(args.items))
        print(f"Добавлено. Всего исключений: {len(items)}")
        return 0
    if action == "remove":
        items = remove_exclusions(set(args.items))
        print(f"Удалено. Всего исключений: {len(items)}")
        return 0
    if action == "clear":
        clear_exclusions()
        print("Список исключений очищен.")
        return 0
    return 1


def cmd_recipe(args) -> int:
    ctx = build_context(args)
    try:
        run_recipe(args.item_id, _opts_from_args(args), ctx)
        print_stats(ctx.price_service, ctx.craft_calc)
    finally:
        ctx.price_service.stop_heartbeat()
    return 0


def cmd_batch(args) -> int:
    ctx = build_context(args)
    try:
        recipes = filter_recipes(ctx.hideout, bench=args.bench,
                                 category_id=args.category, perk_id=args.perk)
        if not recipes:
            print("Под фильтр не попал ни один рецепт.")
            return 1

        groups, cat_names, order = {}, {}, []
        for r in recipes:
            cid = extract_category_id(r) or "other"
            if cid not in groups:
                groups[cid] = []
                order.append(cid)
                cat_names[cid] = (r["category"]["lines"].get(args.lang) or cid)
            groups[cid].append(r)

        if args.per_category:
            limit = args.max_recipes or 0
            if limit > 0:
                for cid in order:
                    groups[cid] = groups[cid][:limit]
        else:
            limit = args.max_recipes if args.max_recipes is not None else 30
            if limit > 0 and len(recipes) > limit:
                print(f"⚠️  Ограничиваю до {limit} рецептов (--max-recipes).")
                flat = [r for cid in order for r in groups[cid]][:limit]
                groups, cat_names, order = {}, {}, []
                for r in flat:
                    cid = extract_category_id(r) or "other"
                    if cid not in groups:
                        groups[cid] = []
                        order.append(cid)
                        cat_names[cid] = (r["category"]["lines"].get(args.lang) or cid)
                    groups[cid].append(r)

        all_recipes = [r for cid in order for r in groups[cid]]

        if args.per_category:
            print(f"Категорий: {len(order)}, рецептов: {len(all_recipes)}")
        else:
            print(f"Найдено рецептов: {len(all_recipes)}")
        if ctx.exclusions:
            print(f"Исключений: {len(ctx.exclusions)}")

        opts = _opts_from_args(args)
        prefetch_prices(ctx.price_service, ctx.craft_calc, all_recipes,
                        opts, ctx.item_index, ctx.exclusions)

        print(f"\n▶ Анализ {len(all_recipes)} рецептов"
              f"{' [recursive]' if args.recursive else ''}")
        t0 = time.time()
        analyses = []
        for i, r in enumerate(all_recipes, 1):
            name = get_item_name(ctx.item_index, r["result"][0]["item"])
            sys.stdout.write(f"\r   [{i:3d}/{len(all_recipes):3d}] "
                             f"{name[:36]:36s} ({time.time()-t0:5.1f}s)")
            sys.stdout.flush()
            analyses.append(analyze_recipe(
                r, ctx.item_index, ctx.price_service,
                fee_pct=args.fee, craft_calc=ctx.craft_calc, lang=args.lang,
                ignore_missing=args.ignore_missing,
                exclusions=ctx.exclusions,
            ))
        print(f"\r   ✓ готово за {time.time()-t0:.1f}s" + " " * 40)

        key = ((lambda x: x.margin_pct) if args.sort == "margin"
               else (lambda x: x.profit))
        top = args.top if args.top is not None else (5 if args.per_category else 10)

        if args.per_category:
            for cid in order:
                cat = [a for a in analyses
                       if (extract_category_id(a.recipe) or "other") == cid]
                full = [a for a in cat if a.margin_pct is not None]
                full.sort(key=key, reverse=True)
                print(f"\n{'═' * 66}")
                print(f"  🏆 {cat_names[cid]} — топ-{top} по {args.sort}")
                print(f"{'─' * 66}")
                if not full:
                    print("  нет рецептов с полными ценами")
                    continue
                for i, a in enumerate(full[:top], 1):
                    gift = (f" 🎁{sum(a.excluded_summary.values())}"
                            if a.excluded_summary else "")
                    print(f"  {i:2d}. {fmt_pct(a.margin_pct):>8s}  "
                          f"{a.result_name:32s} "
                          f"прибыль {fmt_price(a.profit):>10s}, "
                          f"себест. {fmt_price(a.total_cost):>10s}{gift}")
        else:
            full = [a for a in analyses if a.margin_pct is not None]
            partial = [a for a in analyses if a.margin_pct is None]
            print(f"\nС полными ценами: {len(full)}, без данных: {len(partial)}")
            full.sort(key=key, reverse=True)
            print(f"\n🏆 ТОП-{top} по {args.sort}:")
            for a in full[:top]:
                print(f"  {fmt_pct(a.margin_pct):>8s}  {a.result_name:36s} "
                      f"прибыль {fmt_price(a.profit):>12s}, "
                      f"себест. {fmt_price(a.total_cost):>12s}")

        print_stats(ctx.price_service, ctx.craft_calc)
    finally:
        ctx.price_service.stop_heartbeat()
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
    p.add_argument("--explain", action="store_true")
    p.add_argument("--explain-tree", action="store_true")
    p.add_argument("--ignore-missing", action="store_true")
    p.add_argument("--exclude", default="")
    p.add_argument("--show-ids", action="store_true")


def main() -> int:
    # без аргументов → меню
    if len(sys.argv) == 1:
        from cli.menu import run_menu
        return run_menu()

    p = argparse.ArgumentParser(description="Stalcraft crafting calculator")
    sub = p.add_subparsers(dest="command", required=True)

    p_menu = sub.add_parser("menu", help="Интерактивное меню")
    p_menu.set_defaults(func=cmd_menu)

    p_help = sub.add_parser("help", help="Справочник команд и тем")
    p_help.add_argument("topic", nargs="?", default=None,
                        help="examples | prices | energy | fee | recursive | "
                             "troubleshoot | exclusions | menu | all")
    p_help.set_defaults(func=cmd_help)

    p_excl = sub.add_parser("exclusions",
                            help="Управление исключениями (нулевая стоимость)")
    excl_sub = p_excl.add_subparsers(dest="action", required=True)

    ex_list = excl_sub.add_parser("list", help="Показать исключённые предметы")
    ex_list.set_defaults(func=cmd_exclusions)
    ex_add = excl_sub.add_parser("add", help="Добавить предметы")
    ex_add.add_argument("items", nargs="+")
    ex_add.set_defaults(func=cmd_exclusions)
    ex_rm = excl_sub.add_parser("remove", help="Удалить предметы")
    ex_rm.add_argument("items", nargs="+")
    ex_rm.set_defaults(func=cmd_exclusions)
    ex_clear = excl_sub.add_parser("clear", help="Очистить все исключения")
    ex_clear.set_defaults(func=cmd_exclusions)

    p1 = sub.add_parser("recipe", help="Анализ рецептов по itemId результата")
    p1.add_argument("item_id")
    add_common_args(p1)
    p1.set_defaults(func=cmd_recipe)

    p2 = sub.add_parser("batch", help="Пакетный анализ по фильтру")
    p2.add_argument("--bench", choices=["workbench", "laboratory_table", "kitchen_table"])
    p2.add_argument("--category")
    p2.add_argument("--perk")
    p2.add_argument("--top", type=int, default=None)
    p2.add_argument("--max-recipes", type=int, default=None)
    p2.add_argument("--sort", choices=["margin", "profit"], default="margin")
    p2.add_argument("--per-category", action="store_true")
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