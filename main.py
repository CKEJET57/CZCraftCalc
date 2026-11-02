"""
main.py — тонкий CLI dispatcher.
Вся логика анализа — в core/runner.py.
"""

import argparse
import sys

import requests

from cli.help import print_operations, print_topic, print_unknown_topic
from config import DEFAULT_REGION
from core.context import build_context
from core.options import AnalysisOptions
from core.runner import run_batch, run_recipe
from storage.exclusions import (
    add_exclusions, clear_exclusions, load_exclusions, remove_exclusions,
)
from storage.hideout import filter_recipes
from storage.listing import build_item_index, get_item_name, load_listing


# ────────── команды ──────────
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
    opts = AnalysisOptions.from_args(args)
    ctx = build_context(opts)
    try:
        run_recipe(args.item_id, opts, ctx)
    finally:
        ctx.close()
    return 0


def cmd_batch(args) -> int:
    opts = AnalysisOptions.from_args(args)
    ctx = build_context(opts)
    try:
        recipes = filter_recipes(ctx.hideout, bench=args.bench,
                                 category_id=args.category, perk_id=args.perk)
        if not recipes:
            print("Под фильтр не попал ни один рецепт.")
            return 1
        run_batch(
            opts, ctx, recipes,
            per_category=args.per_category,
            top=args.top,
            max_recipes=args.max_recipes,
            sort=args.sort,
        )
    finally:
        ctx.close()
    return 0


# ────────── entrypoint ──────────
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
    for name, help_text in [
        ("list", "Показать исключённые предметы"),
        ("add", "Добавить предметы"),
        ("remove", "Удалить предметы"),
        ("clear", "Очистить все исключения"),
    ]:
        pp = excl_sub.add_parser(name, help=help_text)
        if name in ("add", "remove"):
            pp.add_argument("items", nargs="+", help="itemId")
        pp.set_defaults(func=cmd_exclusions)

    p1 = sub.add_parser("recipe", help="Анализ рецептов по itemId")
    p1.add_argument("item_id")
    add_common_args(p1)
    p1.set_defaults(func=cmd_recipe)

    p2 = sub.add_parser("batch", help="Пакетный анализ по фильтру")
    p2.add_argument("--bench", choices=["workbench", "laboratory_table",
                                        "kitchen_table"])
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