"""
core/runner.py — оркестрация анализа: единая логика для CLI и меню.
"""

import sys
import time

from config import ENERGY_ITEM_ID, EXCLUDED_TOP_CATEGORIES
from core.display import (
    fmt_pct, fmt_price, print_analysis, print_stats,
)
from services.craft import analyze_recipe
from services.price import phase
from storage.hideout import (
    extract_category_id, find_recipes_by_result,
)
from storage.listing import get_item_name


# ──────────────────────────────────────────────────────────────────
#  Перевод названий сортировки для вывода
# ──────────────────────────────────────────────────────────────────
_SORT_LABEL = {
    "margin": "марже",
    "profit": "прибыли",
}


def _sort_label(sort: str) -> str:
    return _SORT_LABEL.get(sort, sort)


# ──────────────────────────────────────────────────────────────────
#  Prefetch (внутренний)
# ──────────────────────────────────────────────────────────────────
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


def _prefetch(ctx, recipes: list[dict], opts) -> None:
    if ctx.craft_calc is not None:
        items = (ctx.craft_calc.collect_tree_items(recipes)
                 if opts.recursive
                 else _direct_items(recipes, ctx.exclusions))
    else:
        items = _direct_items(recipes, ctx.exclusions)

    todo = [i for i in items if not ctx.price_service._is_cached(i)]
    if not todo:
        print(f"→ Все {len(items)} itemId в кэше")
        return
    label = f"Prefetch цен ({len(todo)} itemId, workers={opts.workers})"
    print()
    with phase(label, label_width=55):
        def _progress(done, total, current_id):
            name = get_item_name(ctx.item_index, current_id)
            sys.stdout.write(f"\r   [{done:3d}/{total:3d}] {name[:40]:40s}")
            sys.stdout.flush()
        ctx.price_service.prefetch(todo, workers=opts.workers, progress=_progress)
    print()


# ──────────────────────────────────────────────────────────────────
#  Recipe
# ──────────────────────────────────────────────────────────────────
def run_recipe(item_id: str, opts, ctx) -> None:
    recipes = find_recipes_by_result(ctx.hideout, item_id)
    if not recipes:
        print(f"Рецепт для «{item_id}» не найден.")
        return
    print(f"Найдено рецептов: {len(recipes)}")
    if ctx.exclusions:
        print(f"Исключений: {len(ctx.exclusions)}")

    _prefetch(ctx, recipes, opts)

    for r in recipes:
        a = analyze_recipe(
            r, ctx.item_index, ctx.price_service,
            fee_pct=opts.fee, craft_calc=ctx.craft_calc, lang=opts.lang,
            ignore_missing=opts.ignore_missing,
            exclusions=ctx.exclusions,
        )
        print_analysis(a, ctx.item_index, craft_calc=ctx.craft_calc,
                       explain=opts.explain,
                       explain_tree=opts.explain_tree,
                       show_ids=opts.show_ids)

    print_stats(ctx.price_service, ctx.craft_calc)


# ──────────────────────────────────────────────────────────────────
#  Batch
# ──────────────────────────────────────────────────────────────────
def run_batch(opts, ctx, recipes: list[dict], *,
              per_category: bool = False,
              top: int | None = None,
              max_recipes: int | None = None,
              sort: str = "margin") -> None:
    """
    Пакетный анализ ПРЕДВАРИТЕЛЬНО отфильтрованного списка рецептов.
    Категории из EXCLUDED_TOP_CATEGORIES исключаются ВСЕГДА
    (и в per_category, и в общем топе).
    """
    if not recipes:
        print("Нет рецептов для анализа.")
        return

    # ─── фильтр неинтересных категорий (работает в обоих режимах) ───
    recipes = [
        r for r in recipes
        if (extract_category_id(r) or "other") not in EXCLUDED_TOP_CATEGORIES
    ]
    if not recipes:
        print("После фильтра не осталось рецептов.")
        return

    groups, cat_names, order = _group_recipes(recipes, opts.lang)

    # ─── лимиты ───
    if per_category:
        limit = max_recipes or 0
        if limit > 0:
            for cid in order:
                groups[cid] = groups[cid][:limit]
    else:
        limit = max_recipes if max_recipes is not None else 30
        if limit > 0 and len(recipes) > limit:
            print(f"⚠️  Ограничиваю до {limit} рецептов (--max-recipes), "
                  f"по всем категориям поровну.")
            flat = _round_robin(groups, order, limit)
            groups, cat_names, order = _group_recipes(flat, opts.lang)

    all_recipes = [r for cid in order for r in groups[cid]]

    if per_category:
        print(f"Категорий: {len(order)}, рецептов: {len(all_recipes)}")
    else:
        print(f"Найдено рецептов: {len(all_recipes)}")
    if ctx.exclusions:
        print(f"Исключений: {len(ctx.exclusions)}")

    _prefetch(ctx, all_recipes, opts)

    print(f"\n▶ Анализ {len(all_recipes)} рецептов"
          f"{' [recursive]' if opts.recursive else ''}")
    t0 = time.time()
    analyses = []
    for i, r in enumerate(all_recipes, 1):
        name = get_item_name(ctx.item_index, r["result"][0]["item"], opts.lang)
        sys.stdout.write(f"\r   [{i:3d}/{len(all_recipes):3d}] "
                         f"{name[:36]:36s} ({time.time()-t0:5.1f}s)")
        sys.stdout.flush()
        analyses.append(analyze_recipe(
            r, ctx.item_index, ctx.price_service,
            fee_pct=opts.fee, craft_calc=ctx.craft_calc, lang=opts.lang,
            ignore_missing=opts.ignore_missing,
            exclusions=ctx.exclusions,
        ))
    print(f"\r   ✓ готово за {time.time()-t0:.1f}s" + " " * 40)

    top_n = top if top is not None else (5 if per_category else 10)
    sort_key = ((lambda x: x.margin_pct) if sort == "margin"
                else (lambda x: x.profit))
    sort_label = _sort_label(sort)

    if per_category:
        for cid in order:
            cat = [a for a in analyses
                   if (extract_category_id(a.recipe) or "other") == cid]
            full = [a for a in cat if a.margin_pct is not None]
            full.sort(key=sort_key, reverse=True)
            print(f"\n{'═' * 66}")
            print(f"  🏆 {cat_names[cid]} — топ-{top_n} по {sort_label}")
            print(f"{'─' * 66}")
            if not full:
                print("  нет рецептов с полными ценами")
                continue
            for i, a in enumerate(full[:top_n], 1):
                _print_top_line(i, a)
    else:
        full = [a for a in analyses if a.margin_pct is not None]
        partial = [a for a in analyses if a.margin_pct is None]
        print(f"\nС полными ценами: {len(full)}, без данных: {len(partial)}")
        full.sort(key=sort_key, reverse=True)
        print(f"\n🏆 ТОП-{top_n} по {sort_label}:")
        for a in full[:top_n]:
            print(f"  {fmt_pct(a.margin_pct):>8s}  {a.result_name:36s} "
                  f"прибыль {fmt_price(a.profit):>12s}, "
                  f"себест. {fmt_price(a.total_cost):>12s}")

    print_stats(ctx.price_service, ctx.craft_calc)


# ──────────────────────────────────────────────────────────────────
#  Character profile
# ──────────────────────────────────────────────────────────────────
def run_character(name: str, opts, ctx) -> None:
    """Запрашивает профиль персонажа и печатает его."""
    from api.characters import fetch_character_profile

    token = ctx.price_service.token
    profile = fetch_character_profile(token, opts.region, name)

    if profile is None:
        print(f"Персонаж «{name}» не найден в регионе {opts.region}.")
        return

    print(f"\n=== Профиль: {profile.get('name', name)} ===")
    print(f"  UUID: {profile.get('uuid', '—')}")
    print(f"  Альянс: {profile.get('alliance', '—')}")

    clan = profile.get("clan") or {}
    info = clan.get("info") or {}
    member = clan.get("member") or {}
    if info:
        print(f"  Клан: {info.get('name', '—')} [{info.get('tag', '—')}]")
        print(f"  Роль: {member.get('rank', '—')}")
        print(f"  Статус: {member.get('status', '—')}")
    else:
        print("  Клан: —")

    stats = profile.get("stats") or profile.get("statistics") or {}
    if stats:
        print("\n  Статистика:")
        for k, v in stats.items():
            if isinstance(v, (int, float, str)):
                print(f"    {k}: {v}")

    if opts.verbose:
        print(f"\n  Ключи ответа: {list(profile.keys())}")


# ──────────────────────────────────────────────────────────────────
#  Вспомогательное
# ──────────────────────────────────────────────────────────────────
def _group_recipes(recipes, lang):
    groups: dict[str, list[dict]] = {}
    cat_names: dict[str, str] = {}
    order: list[str] = []
    for r in recipes:
        cid = extract_category_id(r) or "other"
        if cid not in groups:
            groups[cid] = []
            order.append(cid)
            cat_names[cid] = r["category"]["lines"].get(lang) or cid
        groups[cid].append(r)
    return groups, cat_names, order


def _round_robin(groups: dict[str, list[dict]], order: list[str],
                 limit: int) -> list[dict]:
    """Берёт по одному рецепту из каждой категории по кругу, пока не наберёт limit."""
    queues = {cid: list(groups[cid]) for cid in order}
    picked: list[dict] = []
    while len(picked) < limit and any(queues.values()):
        for cid in order:
            if queues[cid] and len(picked) < limit:
                picked.append(queues[cid].pop(0))
    return picked


def _print_top_line(i: int, a) -> None:
    gift = (f" 🎁{sum(a.excluded_summary.values())}"
            if a.excluded_summary else "")
    print(f"  {i:2d}. {fmt_pct(a.margin_pct):>8s}  "
          f"{a.result_name:32s} "
          f"прибыль {fmt_price(a.profit):>10s}, "
          f"себест. {fmt_price(a.total_cost):>10s}{gift}")