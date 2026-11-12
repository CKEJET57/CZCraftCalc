from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter

from config import DB_DIR
from core.analysis import analyze_recipe_by_id
from server.deps import get_state
from server.routes._helpers import opts_from_req
from server.schemas import RecipeReq
from server.serializers import serialize_recipe_list

router = APIRouter(tags=["recipes"])

BARTER_FILE = DB_DIR / "barter_recipes.json"


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

@router.post("/recipe")
def recipe(req: RecipeReq) -> dict:
    opts = opts_from_req(req)
    ctx = get_state().build_context(opts)

    analyses = analyze_recipe_by_id(req.item_id, opts, ctx)
    if analyses:
        recipes = serialize_recipe_list(analyses, ctx.item_index, opts.lang)
        for r in recipes:
            r["kind"] = "craft"
        return {"item_id": req.item_id, "recipes": _dedupe(recipes)}

    barter = _barter_recipes(req.item_id, ctx, opts.lang, opts.fee)
    if barter:
        return {"item_id": req.item_id, "recipes": _dedupe(barter)}

    return {"item_id": req.item_id, "recipes": []}