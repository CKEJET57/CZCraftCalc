from __future__ import annotations

from fastapi import APIRouter

from core.analysis import analyze_batch
from server.deps import get_state
from server.routes._helpers import opts_from_req
from server.schemas import BatchReq
from server.serializers import serialize_batch
from storage.hideout import filter_recipes

router = APIRouter(tags=["batch"])


@router.post("/batch")
def batch(req: BatchReq) -> dict:
    opts = opts_from_req(req)
    ctx = get_state().build_context(opts)
    recipes = filter_recipes(
        ctx.hideout,
        bench=req.bench, category_id=req.category, perk_id=req.perk,
    )
    result = analyze_batch(
        opts, ctx, recipes,
        per_category=req.per_category,
        top=req.top,
        max_recipes=req.max_recipes,
        sort=req.sort,
    )
    return serialize_batch(result)