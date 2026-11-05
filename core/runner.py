"""
core/runner.py — оркестрация анализа: единая логика для CLI и меню.
"""
from __future__ import annotations

import statistics
import sys
import time
from datetime import datetime, timedelta, timezone

from config import ENERGY_ITEM_ID, EXCLUDED_TOP_CATEGORIES, LOCAL_TIMEZONE
from core.display import (
    fmt_pct, fmt_price, print_analysis, print_stats,
)
from services.craft import analyze_recipe
from services.price import phase
from storage.hideout import (
    extract_category_id, find_recipes_by_result,
)
from storage.listing import get_item_name


try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(LOCAL_TIMEZONE)
except Exception:
    _TZ = None

# ──────────────────────────────────────────────────────────────────
#  Перевод названий сортировки для вывода
# ──────────────────────────────────────────────────────────────────
_SORT_LABEL = {
    "margin": "марже",
    "profit": "прибыли",
}


def _sort_label(sort: str) -> str:
    return _SORT_LABEL.get(sort, sort)

def _fmt_datetime(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return iso_str
    if _TZ is not None:
        dt = dt.astimezone(_TZ)
    return dt.strftime("%d.%m.%Y %H:%M")


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

    todo = [i for i in items if not ctx.price_service.is_cached(i)]
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
#  History (сырые сделки)
# ──────────────────────────────────────────────────────────────────
def run_history(item_id: str, opts, ctx,
                limit: int = 200,
                sort: str = "newest",
                days: int | None = None,
                show: int = 30,
                page: int = 0) -> None:
    """История покупок предмета с статистикой и постраничным списком сделок."""
    history = ctx.price_service.get_history(item_id, limit)
    name = get_item_name(ctx.item_index, item_id, opts.lang)

    print(f"\n=== История покупок: {name} ({item_id}) ===")

    if not history:
        print("  Сделок не найдено (или история недоступна).")
        return

    # --- нормализация ---
    deals: list[dict] = []
    for d in history:
        try:
            price = float(d.get("price", 0))
            amount = int(d.get("amount", 0))
        except (TypeError, ValueError):
            continue
        if amount <= 0 or price <= 0:
            continue
        deals.append({
            "price": price,
            "amount": amount,
            "unit": price / amount,
            "time": d.get("time") or d.get("timestamp"),
        })

    if not deals:
        print("  Нет валидных сделок.")
        return

    # --- фильтр по дням ---
    if days is not None and days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        filtered = []
        for d in deals:
            if not d["time"]:
                continue
            try:
                dt = datetime.fromisoformat(d["time"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt >= cutoff:
                filtered.append(d)
        deals = filtered
        if not deals:
            print(f"  Нет сделок за последние {days} дн.")
            return

    # --- сортировка ---
    if sort == "newest":
        deals.sort(key=lambda d: d["time"] or "", reverse=True)
    elif sort == "oldest":
        deals.sort(key=lambda d: d["time"] or "")
    elif sort == "price-asc":
        deals.sort(key=lambda d: d["unit"])
    elif sort == "price-desc":
        deals.sort(key=lambda d: d["unit"], reverse=True)

    # --- статистика ---
    units = sorted(d["unit"] for d in deals)
    n = len(units)
    trim = int(n * 0.1)
    core = units[trim: n - trim] if trim else units
    median_all = statistics.median(units) if units else 0.0
    median_trim = statistics.median(core) if core else 0.0
    total_rub = sum(d["price"] for d in deals)
    total_units = sum(d["amount"] for d in deals)

    print(f"  Сделок: {n}  |  единиц: {total_units}  |  "
          f"сумма: {fmt_price(total_rub)}")
    print("\n  💰 Цена за штуку:")
    print(f"     min:              {fmt_price(units[0])}")
    print(f"     max:              {fmt_price(units[-1])}")
    print(f"     median:           {fmt_price(median_all)}")
    print(f"     median (trim10%): {fmt_price(median_trim)}")

    # --- постраничный вывод ---
    if show <= 0:
        show_n = n
        page = 0
        total_pages = 1
    else:
        show_n = show
        total_pages = max(1, (n + show_n - 1) // show_n)
        page = max(0, min(page, total_pages - 1))

    start = page * show_n
    end = min(start + show_n, n)

    labels = {
        "newest": "последние",
        "oldest": "первые",
        "price-asc": "самые дешёвые",
        "price-desc": "самые дорогие",
    }
    label = labels.get(sort, "первые")

    if total_pages > 1:
        print(f"\n  📋 {label} ({start + 1}–{end} из {n}, "
              f"стр. {page + 1}/{total_pages}):")
    else:
        print(f"\n  📋 {label} {show_n} сделок:")

    for i, d in enumerate(deals[start:end], start + 1):
        when = _fmt_datetime(d["time"]) if d["time"] else "—"
        print(f"    {i:3d}. {when:20s}  {fmt_price(d['unit']):>10s}/шт  "
              f"× {d['amount']:4d}  = {fmt_price(d['price']):>12s}")

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(f"--page {page - 1} (назад)")
        if page < total_pages - 1:
            nav.append(f"--page {page + 1} (вперёд)")
        if nav:
            print(f"\n  💡 {' · '.join(nav)}")

    if opts.verbose:
        print(f"\n  Первый raw-элемент: {history[0]}")

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

    # --- основное ---
    print(f"\n=== {profile.get('username') or name} ===")
    print(f"  UUID: {profile.get('uuid', '—')}")
    print(f"  Альянс: {profile.get('alliance', '—')}")
    print(f"  Статус: {profile.get('status', '—')}")

    last_login = profile.get("lastLogin")
    if last_login:
        print(f"  Последний вход: {_fmt_datetime(last_login)}")

    # --- клан ---
    clan = profile.get("clan") or {}
    info = clan.get("info") or {}
    member = clan.get("member") or {}
    if info:
        clan_name = info.get("name", "—")
        clan_tag = info.get("tag", "—")
        print(f"\n  Клан: {clan_name} [{clan_tag}]")
        if info.get("level"):
            print(f"    Уровень: {info['level']} "
                  f"({info.get('levelPoints', 0)} очков)")
        if info.get("alliance"):
            print(f"    Альянс клана: {info['alliance']}")
        if info.get("leader"):
            print(f"    Лидер: {info['leader']}")
        if info.get("memberCount") is not None:
            print(f"    Участников: {info['memberCount']}")
        if member:
            print(f"    Роль: {member.get('rank', '—')}")
            if member.get("joinTime"):
                print(f"    В клане с: {_fmt_datetime(member['joinTime'])}")
    else:
        print("\n  Клан: —")

    # --- статистика: список {id, type, value} ---
    stats = profile.get("stats") or []
    if stats:
        print("\n  Статистика:")
        for s in stats:
            if not isinstance(s, dict):
                continue
            sid = s.get("id", "?")
            stype = s.get("type", "?")
            value = s.get("value")
            if value in ({}, None):
                continue
            if isinstance(value, dict):
                for vk, vv in value.items():
                    print(f"    {sid}.{vk}: {vv}")
            else:
                print(f"    {sid}: {value} ({stype})")

    # --- достижения ---
    ach = profile.get("displayedAchievements") or []
    if ach:
        print(f"\n  Показанные достижения ({len(ach)}):")
        for a in ach[:10]:
            print(f"    • {a}")
        if len(ach) > 10:
            print(f"    … ещё {len(ach) - 10}")

    # --- отладка ---
    if opts.verbose:
        print(f"\n  Ключи ответа: {list(profile.keys())}")
        print(f"  Первый stats-элемент: {stats[0] if stats else '—'}")


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