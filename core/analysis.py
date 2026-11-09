"""
core/analysis.py — чистые функции анализа: возвращают данные, не печатают.

Используется и CLI (core.runner), и HTTP-сервером (server.routes).
Побочные эффекты — только те, что внутри ctx (HTTP + кэш PriceService).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config import ENERGY_ITEM_ID, EXCLUDED_TOP_CATEGORIES
from services.craft import RecipeAnalysis, analyze_recipe
from storage.hideout import extract_category_id, find_recipes_by_result


# ─── batch ────────────────────────────────────────────────────────
@dataclass
class BatchSection:
    category_id: str | None          # None = общий топ
    category_name: str
    items: list[RecipeAnalysis]


@dataclass
class BatchResult:
    total_analyzed: int
    with_full_price: int
    without_data: int
    top_n: int
    sort: str
    per_category: bool
    sections: list[BatchSection] = field(default_factory=list)


# ─── история ──────────────────────────────────────────────────────
@dataclass
class HistoryResult:
    item_id: str
    item_name: str
    deals: list[dict]
    stats: dict
    page: int
    page_size: int
    total_pages: int
    raw_sample: dict | None = None


# ─── prefetch ─────────────────────────────────────────────────────
def collect_prefetch_items(opts, ctx, recipes: list[dict]) -> set[str]:
    if ctx.craft_calc is not None and opts.recursive:
        return ctx.craft_calc.collect_tree_items(recipes)
    items = set() if ENERGY_ITEM_ID in ctx.exclusions else {ENERGY_ITEM_ID}
    for r in recipes:
        for res in r.get("result", []):
            items.add(res["item"])
        for ing in r.get("ingredients", []):
            if ing["item"] in ctx.exclusions:
                continue
            items.add(ing["item"])
    return items


def prefetch(opts, ctx, recipes: list[dict], progress=None) -> int:
    items = collect_prefetch_items(opts, ctx, recipes)
    todo = [i for i in items if not ctx.price_service.is_cached(i)]
    if todo:
        ctx.price_service.prefetch(todo, workers=opts.workers, progress=progress)
    return len(todo)


# ─── recipe ───────────────────────────────────────────────────────
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
def _filter_recipes(recipes: list[dict]) -> list[dict]:
    return [
        r for r in recipes
        if (extract_category_id(r) or "other") not in EXCLUDED_TOP_CATEGORIES
    ]


def _group_recipes(recipes: list[dict], lang: str):
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
    queues = {cid: list(groups[cid]) for cid in order}
    picked: list[dict] = []
    while len(picked) < limit and any(queues.values()):
        for cid in order:
            if queues[cid] and len(picked) < limit:
                picked.append(queues[cid].pop(0))
    return picked


def analyze_batch(opts, ctx, recipes: list[dict], *,
                  per_category: bool = False,
                  top: int | None = None,
                  max_recipes: int | None = None,
                  sort: str = "margin",
                  progress=None) -> BatchResult:
    """Пакетный анализ. Возвращает данные, не печатает."""
    recipes = _filter_recipes(recipes)
    if not recipes:
        return BatchResult(0, 0, 0, top or 0, sort, per_category)

    groups, cat_names, order = _group_recipes(recipes, opts.lang)

    if per_category:
        limit = max_recipes or 0
        if limit > 0:
            for cid in order:
                groups[cid] = groups[cid][:limit]
    else:
        limit = max_recipes if max_recipes is not None else 30
        if limit > 0 and len(recipes) > limit:
            flat = _round_robin(groups, order, limit)
            groups, cat_names, order = _group_recipes(flat, opts.lang)

    all_recipes = [r for cid in order for r in groups[cid]]
    prefetch(opts, ctx, all_recipes)

    analyses: list[RecipeAnalysis] = []
    for i, r in enumerate(all_recipes, 1):
        analyses.append(analyze_recipe(
            r, ctx.item_index, ctx.price_service,
            fee_pct=opts.fee, craft_calc=ctx.craft_calc, lang=opts.lang,
            ignore_missing=opts.ignore_missing, exclusions=ctx.exclusions,
        ))
        if progress:
            progress(i, len(all_recipes))

    top_n = top if top is not None else (5 if per_category else 10)
    sort_key = (lambda x: x.margin_pct) if sort == "margin" else (lambda x: x.profit)

    full = [a for a in analyses if a.margin_pct is not None]
    result = BatchResult(
        total_analyzed=len(analyses),
        with_full_price=len(full),
        without_data=len(analyses) - len(full),
        top_n=top_n,
        sort=sort,
        per_category=per_category,
    )

    if per_category:
        for cid in order:
            cat = [a for a in analyses
                   if (extract_category_id(a.recipe) or "other") == cid]
            cat_full = [a for a in cat if a.margin_pct is not None]
            cat_full.sort(key=sort_key, reverse=True)
            result.sections.append(BatchSection(
                category_id=cid, category_name=cat_names[cid],
                items=cat_full[:top_n],
            ))
    else:
        full.sort(key=sort_key, reverse=True)
        result.sections.append(BatchSection(
            category_id=None, category_name="ТОП",
            items=full[:top_n],
        ))
    return result


# ─── history ──────────────────────────────────────────────────────
def analyze_history(item_id: str, opts, ctx, *,
                    limit: int = 200,
                    sort: str = "newest",
                    days: int | None = None,
                    show: int = 30,
                    page: int = 0) -> HistoryResult | None:
    """Возвращает историю сделок + статистику. None если сделок нет."""
    import statistics
    from datetime import datetime, timedelta, timezone
    from storage.listing import get_item_name

    history = ctx.price_service.get_history(item_id, limit)
    name = get_item_name(ctx.item_index, item_id, opts.lang)

    if not history:
        return HistoryResult(
            item_id=item_id, item_name=name, deals=[], stats={},
            page=0, page_size=0, total_pages=1,
        )

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
        return HistoryResult(item_id, name, [], {}, 0, 0, 1)

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
            return HistoryResult(item_id, name, [], {"empty_reason": f"no deals for last {days}d"}, 0, 0, 1)

    if sort == "newest":
        deals.sort(key=lambda d: d["time"] or "", reverse=True)
    elif sort == "oldest":
        deals.sort(key=lambda d: d["time"] or "")
    elif sort == "price-asc":
        deals.sort(key=lambda d: d["unit"])
    elif sort == "price-desc":
        deals.sort(key=lambda d: d["unit"], reverse=True)

    units = sorted(d["unit"] for d in deals)
    n = len(units)
    trim = int(n * 0.1)
    core = units[trim: n - trim] if trim else units
    stats = {
        "n_deals": n,
        "total_units": sum(d["amount"] for d in deals),
        "total_rub": sum(d["price"] for d in deals),
        "min": units[0],
        "max": units[-1],
        "median": statistics.median(units),
        "median_trim10": statistics.median(core) if core else 0.0,
    }

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

    return HistoryResult(
        item_id=item_id, item_name=name,
        deals=deals[start:end], stats=stats,
        page=page, page_size=show_n, total_pages=total_pages,
        raw_sample=history[0] if opts.verbose else None,
    )