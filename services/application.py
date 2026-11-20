"""Прикладные операции калькулятора, не зависящие от HTTP или IPC."""
from __future__ import annotations

import json
from functools import lru_cache

from config import DB_DIR
from core.batch_analysis import analyze_batch
from core.history_analysis import analyze_history
from core.recipe_analysis import analyze_recipe_by_id
from core.options import AnalysisOptions
from services.serialization import serialize_batch, serialize_history, serialize_recipe_list
from storage.hideout import filter_recipes


BARTER_FILE = DB_DIR / "barter_recipes.json"


def _options(payload: dict) -> AnalysisOptions:
    return AnalysisOptions(
        region=payload.get("region", "RU"),
        lang=payload.get("lang", "ru"),
        fee=payload.get("fee", 5.0),
        recursive=payload.get("recursive", False),
        max_depth=payload.get("max_depth", 12),
        no_fallback=payload.get("no_fallback", False),
        no_history=payload.get("no_history", False),
        workers=payload.get("workers", 4),
        no_heartbeat=True,
        verbose=False,
        ignore_missing=payload.get("ignore_missing", False),
        exclude=",".join(payload.get("exclude") or []),
        use_local_data=payload.get("use_local_data", False),
    )


@lru_cache(maxsize=1)
def _barter_index() -> dict[str, list[dict]]:
    if not BARTER_FILE.exists():
        return {}
    data = json.loads(BARTER_FILE.read_text(encoding="utf-8"))
    idx: dict[str, list[dict]] = {}
    for settle in data:
        title = (settle.get("settlementTitle") or {}).get("lines", {}).get("ru", "Бартер")
        for r in settle.get("recipes", []):
            if r.get("item"):
                idx.setdefault(r["item"], []).append({"title": title, "recipe": r})
    return idx





def _name(ctx, item_id: str, lang: str) -> str:
    entry = ctx.item_index.get(item_id) if hasattr(ctx.item_index, "get") else None
    if not entry:
        return item_id
    name = entry.get("name") if isinstance(entry, dict) else getattr(entry, "name", None)
    if isinstance(name, dict):
        lines = name.get("lines") or name
        return lines.get(lang) or lines.get("ru") or item_id
    return name or item_id


def _price(ctx, item_id: str):
    try:
        return ctx.price(item_id)
    except Exception:
        return None





def _barter_recipes(item_id: str, ctx, lang: str, fee: float) -> list[dict]:
    out = []
    for entry in _barter_index().get(item_id, []):
        title = entry["title"]
        for offer in entry["recipe"].get("offers", []):
            ings, cost_sum, missing = [], 0.0, 0
            for req in offer.get("requiredItems", []):
                rid, amt = req["item"], req["amount"]
                p = _price(ctx, rid)
                tp = p * amt if p is not None else None
                if p is None:
                    missing += 1
                else:
                    cost_sum += tp
                ings.append({
                    "item_id": rid, "name": _name(ctx, rid, lang), "amount": amt,
                    "unit_price": p, "total_price": tp,
                    "source": "barter", "craft_path": None,
                })
            cost_sum += offer.get("cost") or 0
            total_cost = None if missing else cost_sum
            gross = _price(ctx, item_id)
            if gross is not None and total_cost is not None:
                fee_amt = gross * fee / 100
                net = gross - fee_amt
                profit = net - total_cost
                margin = profit / total_cost * 100 if total_cost > 0 else None
            else:
                fee_amt = net = profit = margin = None
            out.append({
                "result_item_id": item_id,
                "result_name": _name(ctx, item_id, lang),
                "result_amount": 1,
                "category": "Бартер",
                "subcategory": title,
                "bench": "barter",
                "requirements": {"perks": {}, "features": []},
                "ingredients": ings,
                "ingredients_cost": None if missing else cost_sum,
                "energy": 0, "energy_cost": 0,
                "total_cost": total_cost,
                "revenue_gross": gross, "fee_pct": fee,
                "fee_amount": fee_amt, "revenue_net": net,
                "profit": profit, "margin_pct": margin,
                "missing_ingredients": missing, "missing_energy": False,
                "partial": missing > 0 or gross is None,
                "excluded_summary": {},
                "required_total": {
                    i["item_id"]: {"amount": i["amount"], "source": "barter", "name": i["name"]}
                    for i in ings
                },
                "full_tree": {},
                "kind": "barter",
            })
    return out





def _dedupe(recipes: list[dict]) -> list[dict]:
    """Склеивает рецепты с одинаковым результатом, станком и составом ингредиентов.
    Из группы оставляет самый выгодный, а subcategory объединяет через ' / '."""
    groups: dict[tuple, list[dict]] = {}
    for r in recipes:
        key = (
            r.get("result_item_id"),
            r.get("result_amount"),
            r.get("bench"),
            tuple(sorted(
                (i.get("item_id"), i.get("amount"))
                for i in r.get("ingredients") or []
            )),
        )
        groups.setdefault(key, []).append(r)

    out: list[dict] = []
    for group in groups.values():
        best = max(
            group,
            key=lambda r: (r.get("profit") is not None, r.get("profit") or 0),
        )
        titles: list[str] = []
        for r in group:
            sc = r.get("subcategory")
            if sc and sc not in titles:
                titles.append(sc)
        if len(titles) > 1:
            best = {**best, "subcategory": " / ".join(titles)}
        out.append(best)
    return out




def recipe_operation(state, payload: dict) -> dict:
    item_id = str(payload.get("item_id") or "")
    opts = _options(payload)
    ctx = state.build_context(opts)
    analyses = analyze_recipe_by_id(item_id, opts, ctx)
    if analyses:
        recipes = serialize_recipe_list(analyses, ctx.item_index, opts.lang)
        for result in recipes:
            result["kind"] = "craft"
        return {"item_id": item_id, "recipes": _dedupe(recipes)}
    barter = _barter_recipes(item_id, ctx, opts.lang, opts.fee)
    return {"item_id": item_id, "recipes": _dedupe(barter) if barter else []}


def batch_operation(state, payload: dict) -> dict:
    opts = _options(payload)
    ctx = state.build_context(opts)
    recipes = filter_recipes(
        ctx.hideout,
        bench=payload.get("bench"),
        category_id=payload.get("category"),
        perk_id=payload.get("perk"),
    )
    result = analyze_batch(
        opts, ctx, recipes,
        per_category=payload.get("per_category", False),
        top=payload.get("top"),
        max_recipes=payload.get("max_recipes"),
        sort=payload.get("sort", "margin"),
    )
    return serialize_batch(result, ctx.item_index, opts.lang)


def history_operation(state, payload: dict) -> dict | None:
    opts = AnalysisOptions(
        region=payload.get("region", "RU"),
        lang=payload.get("lang", "ru"),
        no_history=payload.get("no_history", False),
        no_heartbeat=True,
        verbose=False,
    )
    ctx = state.build_context(opts)
    result = analyze_history(
        str(payload.get("item_id") or ""), opts, ctx,
        limit=payload.get("limit", 200),
        sort=payload.get("sort", "newest"),
        days=payload.get("days"),
        show=payload.get("show", 30),
        page=payload.get("page", 0),
    )
    return serialize_history(result) if result is not None else None
