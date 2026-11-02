"""
main.py — CLI калькулятора крафта.

Фичи:
  - id только для [нет] / [ноль] / неизвестных (или с --show-ids)
  - исключения (нулевая стоимость): exclusions add / --exclude
  - согласованное округление
  - help + автопомощь
"""

import argparse
import sys
import time

import requests

from api.auth import fetch_token
from cli.help import print_operations, print_topic, print_unknown_topic
from config import DEFAULT_REGION, ENERGY_ITEM_ID
from services.craft import (
    CraftCalculator, IngredientCost, RecipeAnalysis, analyze_recipe,
)
from services.price import PriceService, phase
from storage.exclusions import (
    add_exclusions, clear_exclusions, load_exclusions, remove_exclusions,
)
from storage.hideout import (
    extract_category_id, filter_recipes, find_recipes_by_result,
    load_hideout_recipes,
)
from storage.listing import build_item_index, get_item_name, load_listing


# ---------- форматирование ----------
def fmt_price(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{round(v):,} ₽".replace(",", " ")


def fmt_pct(v: float | None) -> str:
    return f"{v:+.1f}%" if v is not None else "—"


# ---------- вывод ингредиентов ----------
def print_ingredient_line(ing: IngredientCost, indent: int = 2,
                          explain: bool = False,
                          show_ids: bool = False) -> None:
    pad = " " * indent
    tag = {"market": "рынок", "craft": "крафт",
           "none": "нет", "excluded": "ноль"}[ing.source]

    is_abnormal = (ing.source in ("none", "excluded")
                   or ing.name.startswith("[неизвестный"))
    if show_ids or is_abnormal:
        id_col = f"{ing.item_id:6s} "
    else:
        id_col = "       "

    line = (f"{pad}{id_col}{ing.name:30s} × {ing.amount:3d}  "
            f"[{tag:6s}]  × {fmt_price(ing.unit_price):>12s} = "
            f"{fmt_price(ing.total_price):>12s}")
    if explain and ing.craft_path and ing.craft_path.why:
        line += f"   ← {ing.craft_path.why}"
    print(line)


def print_ingredient_tree(ing, item_index, indent=2, max_depth_display=2,
                          current=0, explain=False, show_ids=False) -> None:
    print_ingredient_line(ing, indent, explain=explain, show_ids=show_ids)
    if ing.craft_path and ing.craft_path.children and current < max_depth_display:
        cp = ing.craft_path
        energy_note = ""
        if cp.energy_cost and cp.energy_cost > 0:
            energy_note = f", энергия {fmt_price(cp.energy_cost)}"
        print(f"{' ' * (indent + 2)}↳ крафт: {cp.craft_runs}× "
              f"(выход {cp.craft_yield}){energy_note}")
        for child in cp.children:
            if child.unit_price is None:
                c_unit = c_total = None
            else:
                c_unit = round(child.unit_price)
                c_total = c_unit * child.amount
            child_ing = IngredientCost(
                item_id=child.item_id,
                name=get_item_name(item_index, child.item_id),
                amount=child.amount,
                unit_price=c_unit, total_price=c_total,
                source=child.source,
                craft_path=child,
            )
            print_ingredient_tree(child_ing, item_index,
                                  indent + 4, max_depth_display,
                                  current + 1, explain=explain,
                                  show_ids=show_ids)


def print_analysis(a: RecipeAnalysis, item_index: dict[str, dict],
                   craft_calc: CraftCalculator | None = None,
                   explain: bool = False,
                   explain_tree: bool = False,
                   show_ids: bool = False) -> None:
    print(f"\n=== {a.result_name} ×{a.result_amount} ===")
    print(f"  Верстак: {a.recipe['bench']} / {a.category_ru} / {a.subcategory_ru}")
    reqs = a.recipe.get("requirements", {})
    print(f"  Перки: {reqs.get('perks', {})}")
    print(f"  Фичи: {', '.join(reqs.get('features', [])) or '—'}")

    print("\n  Ингредиенты:")
    for i in a.ingredients:
        print_ingredient_tree(i, item_index, explain=explain, show_ids=show_ids)

    # 🎁 учтено как ноль
    if a.excluded_summary:
        total_units = sum(a.excluded_summary.values())
        print(f"\n  🎁 Учтено как ноль ({len(a.excluded_summary)} вид., "
              f"{total_units} ед.):")
        for iid, amt in a.excluded_summary.items():
            print(f"     {get_item_name(item_index, iid):30s} × {amt:3d}")

    # 📦 листья выбранного пути (что покупать / уже есть)
    if a.required_total:
        total_units = sum(amt for amt, _ in a.required_total.values())
        src_priority = {"market": 0, "none": 1, "excluded": 2}
        items_sorted = sorted(
            a.required_total.items(),
            key=lambda kv: (src_priority.get(kv[1][1], 99),
                            get_item_name(item_index, kv[0])),
        )
        print(f"\n  📦 Всего потребуется ({len(a.required_total)} вид., "
              f"{total_units} ед.):")
        for iid, (amt, src) in items_sorted:
            tag = {"market": "рынок", "none": "нет",
                   "excluded": "ноль"}.get(src, src)
            id_part = f"{iid:6s} " if (show_ids or src == "none") else "       "
            print(f"     [{tag:5s}]  {id_part}{get_item_name(item_index, iid):30s} "
                  f"× {amt:4d}")

    # 🌳 базовые ресурсы, если всё крафтить самим
    if a.full_tree:
        total_units = sum(amt for amt, _ in a.full_tree.values())
        src_priority = {"market": 0, "lots": 0, "none": 1}
        items_sorted = sorted(
            a.full_tree.items(),
            key=lambda kv: (src_priority.get(kv[1][1], 99),
                            get_item_name(item_index, kv[0])),
        )
        print(f"\n  🌳 Если всё крафтить ({len(a.full_tree)} вид., "
              f"{total_units} ед.):")
        for iid, (amt, src) in items_sorted:
            tag = {"market": "рынок", "lots": "рынок",
                   "none": "нет"}.get(src, src)
            id_part = f"{iid:6s} " if (show_ids or src == "none") else "       "
            print(f"     [{tag:5s}]  {id_part}{get_item_name(item_index, iid):30s} "
                  f"× {amt:4d}")

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
        missing_ids = [i.item_id for i in a.ingredients if i.source == "none"]
        print(f"  ⚠️  Нет цен на {a.missing_ingredients} ингредиент(ов): "
              f"{', '.join(missing_ids)}")

    if a.missing_energy:
        print(f"  ⚠️  Нет цены на {ENERGY_ITEM_ID} — энергия не учтена")

    has_excludable = any(i.source in ("market", "craft") for i in a.ingredients)
    if a.missing_ingredients:
        ids = [i.item_id for i in a.ingredients if i.source == "none"]
        print(f"\n  💡 Исключить: main.py exclusions add {' '.join(ids)}")
    elif has_excludable:
        if show_ids:
            print(f"\n  💡 Исключить: main.py exclusions add <id>")
        else:
            print(f"\n  💡 --show-ids → itemId;  "
                  f"main.py exclusions add <id> → исключить")

# ---------- контекст ----------
def _merge_exclusions(args) -> set[str]:
    items = load_exclusions()
    extra = getattr(args, "exclude", "") or ""
    if extra:
        items.update(x.strip() for x in extra.split(",") if x.strip())
    return items


def build_context(args):
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
    return item_index, hideout, price_service, craft_calc, exclusions


def _direct_items(recipes: list[dict], exclusions: set[str]) -> set[str]:
    items = set() if ENERGY_ITEM_ID in exclusions else {ENERGY_ITEM_ID}
    for r in recipes:
        for res in r.get("result", []):
            items.add(res["item"])
        for ing in r.get("ingredients", []):
            if ing["item"] in exclusions:
                continue
            items.add(ing["item"])
    return items


def _prefetch(price_service, craft_calc, recipes, recursive: bool,
              workers: int, item_index: dict, exclusions: set[str]) -> None:
    if craft_calc is not None:
        items = (craft_calc.collect_tree_items(recipes) if recursive
                 else _direct_items(recipes, exclusions))
    else:
        items = _direct_items(recipes, exclusions)
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
        extra = (f"  exclusions={cs['exclusions']}"
                 if cs.get("exclusions") else "")
        print(f"🧮 Resolve: calls={cs['resolve_calls']}  "
              f"cache_hits={cs['cache_hits']}  memo={cs['memo_size']}{extra}")
    if st["budget_exhausted"]:
        print("⚠️  Бюджет запросов исчерпан — часть цен не получена.")


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
    item_index, hideout, price_service, craft_calc, exclusions = build_context(args)
    recipes = find_recipes_by_result(hideout, args.item_id)
    if not recipes:
        print(f"Рецепт для «{args.item_id}» не найден.")
        price_service.stop_heartbeat()
        return 1
    print(f"Найдено рецептов: {len(recipes)}")
    if exclusions:
        print(f"Исключений: {len(exclusions)}")

    _prefetch(price_service, craft_calc, recipes, args.recursive,
              args.workers, item_index, exclusions)

    for r in recipes:
        analysis = analyze_recipe(
            r, item_index, price_service,
            fee_pct=args.fee, craft_calc=craft_calc, lang=args.lang,
            ignore_missing=args.ignore_missing,
            exclusions=exclusions,
        )
        print_analysis(analysis, item_index, craft_calc=craft_calc,
                       explain=args.explain, explain_tree=args.explain_tree,
                       show_ids=args.show_ids)

    _print_stats(price_service, craft_calc)
    price_service.stop_heartbeat()
    return 0


def cmd_batch(args) -> int:
    item_index, hideout, price_service, craft_calc, exclusions = build_context(args)
    recipes = filter_recipes(hideout, bench=args.bench,
                             category_id=args.category, perk_id=args.perk)
    if not recipes:
        print("Под фильтр не попал ни один рецепт.")
        price_service.stop_heartbeat()
        return 1

    # --- группировка по категориям ---
    groups: dict[str, list[dict]] = {}
    cat_names: dict[str, str] = {}
    order: list[str] = []
    for r in recipes:
        cid = extract_category_id(r) or "other"
        if cid not in groups:
            groups[cid] = []
            order.append(cid)
            cat_names[cid] = r["category"]["lines"].get(args.lang) or cid
        groups[cid].append(r)

    if args.per_category:
        limit = args.max_recipes or 0
        if limit > 0:
            for cid in order:
                if len(groups[cid]) > limit:
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
                    cat_names[cid] = r["category"]["lines"].get(args.lang) or cid
                groups[cid].append(r)

    all_recipes = [r for cid in order for r in groups[cid]]

    if args.per_category:
        print(f"Категорий: {len(order)}, рецептов: {len(all_recipes)}")
        if limit == 0 and len(all_recipes) > 100:
            print(f"⚠️  Анализ ВСЕХ {len(all_recipes)} рецептов может занять "
                  f"несколько минут (recursive={args.recursive}).")
            print(f"    Ограничь --max-recipes N (например, 20) или Ctrl+C.")
    else:
        print(f"Найдено рецептов: {len(all_recipes)}")
    if exclusions:
        print(f"Исключений: {len(exclusions)}")

    _prefetch(price_service, craft_calc, all_recipes, args.recursive,
              args.workers, item_index, exclusions)

    print(f"\n▶ Анализ {len(all_recipes)} рецептов"
          f"{' [recursive]' if args.recursive else ''}")
    t0 = time.time()
    all_analyses: list[RecipeAnalysis] = []
    for i, r in enumerate(all_recipes, 1):
        name = get_item_name(item_index, r["result"][0]["item"])
        sys.stdout.write(f"\r   [{i:3d}/{len(all_recipes):3d}] {name[:36]:36s} "
                         f"({time.time()-t0:5.1f}s)")
        sys.stdout.flush()
        all_analyses.append(analyze_recipe(
            r, item_index, price_service,
            fee_pct=args.fee, craft_calc=craft_calc, lang=args.lang,
            ignore_missing=args.ignore_missing,
            exclusions=exclusions,
        ))
    print(f"\r   ✓ готово за {time.time()-t0:.1f}s" + " " * 40)

    key = ((lambda x: x.margin_pct) if args.sort == "margin"
           else (lambda x: x.profit))
    top = args.top if args.top is not None else (5 if args.per_category else 10)

    if args.per_category:
        for cid in order:
            cat = [a for a in all_analyses
                   if (extract_category_id(a.recipe) or "other") == cid]
            full = [a for a in cat if a.margin_pct is not None]
            full.sort(key=key, reverse=True)

            print(f"\n{'═' * 66}")
            print(f"  🏆 {cat_names.get(cid, cid)}  ({cid}) — "
                  f"топ-{top} по {args.sort}")
            print(f"{'─' * 66}")
            print(f"  всего рецептов: {len(cat)}, "
                  f"с полными ценами: {len(full)}")
            print()

            if not full:
                print("  нет рецептов с полными ценами")
                continue

            for i, a in enumerate(full[:top], 1):
                gift = (f" 🎁{sum(a.excluded_summary.values())}"
                        if a.excluded_summary else "")
                mark = "  ⚠️ partial" if a.partial else ""
                print(f"  {i:2d}. {fmt_pct(a.margin_pct):>8s}  "
                      f"{a.result_name:32s} "
                      f"прибыль {fmt_price(a.profit):>10s}, "
                      f"себест. {fmt_price(a.total_cost):>10s}{gift}{mark}")

            losers = [a for a in full if a.profit < 0]
            if losers:
                print(f"\n  💀 убыточных: {len(losers)} "
                      f"(худший: {fmt_pct(losers[0].margin_pct)} "
                      f"{losers[0].result_name})")
    else:
        full = [a for a in all_analyses if a.margin_pct is not None]
        partial = [a for a in all_analyses if a.margin_pct is None]
        print(f"\nС полными ценами: {len(full)}, без данных: {len(partial)}")
        full.sort(key=key, reverse=True)

        print(f"\n🏆 ТОП-{top} по {args.sort}:")
        for a in full[:top]:
            mark = " (⚠️ partial)" if a.partial else ""
            gift = f" 🎁" if a.excluded_summary else ""
            print(f"  {fmt_pct(a.margin_pct):>8s}  {a.result_name:36s} "
                  f"прибыль {fmt_price(a.profit):>12s}, "
                  f"себест. {fmt_price(a.total_cost):>12s}{gift}{mark}")

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
    p.add_argument("--explain", action="store_true",
                   help="Показать, почему выбран рынок или крафт")
    p.add_argument("--explain-tree", action="store_true",
                   help="Показать, из-за каких базовых предметов нет цены")
    p.add_argument("--ignore-missing", action="store_true",
                   help="Считать приблизительно, если не хватает цен")
    # NEW
    p.add_argument("--exclude", default="",
                   help="itemId через запятую: считать нулевой стоимостью")
    p.add_argument("--show-ids", action="store_true",
                   help="Показывать itemId в выводе ингредиентов")


def main() -> int:
    if len(sys.argv) == 1:
        print_operations()
        return 0

    p = argparse.ArgumentParser(description="Stalcraft crafting calculator")
    sub = p.add_subparsers(dest="command", required=True)

    p_help = sub.add_parser("help", help="Справочник команд и тем")
    p_help.add_argument("topic", nargs="?", default=None,
                        help="examples | prices | energy | fee | recursive | "
                             "troubleshoot | exclusions | all")
    p_help.set_defaults(func=cmd_help)

    # NEW: exclusions
    p_excl = sub.add_parser("exclusions",
                            help="Управление исключениями (нулевая стоимость)")
    excl_sub = p_excl.add_subparsers(dest="action", required=True)

    ex_list = excl_sub.add_parser("list", help="Показать исключённые предметы")
    ex_list.set_defaults(func=cmd_exclusions)

    ex_add = excl_sub.add_parser("add", help="Добавить предметы")
    ex_add.add_argument("items", nargs="+", help="itemId предметов")
    ex_add.set_defaults(func=cmd_exclusions)

    ex_rm = excl_sub.add_parser("remove", help="Удалить предметы")
    ex_rm.add_argument("items", nargs="+", help="itemId предметов")
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
    p2.add_argument("--top", type=int, default=None,
                    help="Сколько в топе (10 / с --per-category: 5)")
    p2.add_argument("--max-recipes", type=int, default=None,
                    help="Лимит (30 без --per-category, без лимита с ним). 0 = нет")
    p2.add_argument("--sort", choices=["margin", "profit"], default="margin")
    p2.add_argument("--per-category", action="store_true",
                    help="Показать топ-N отдельно для каждой категории")
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