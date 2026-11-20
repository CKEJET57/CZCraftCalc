"""Пакетный анализ рецептов и формирование рейтингов."""
from __future__ import annotations

from dataclasses import dataclass, field

from config import EXCLUDED_TOP_CATEGORIES
from services.craft import RecipeAnalysis, analyze_recipe
from storage.hideout import extract_category_id
from core.prefetch import prefetch


@dataclass
class BatchSection:
    category_id: str | None
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
