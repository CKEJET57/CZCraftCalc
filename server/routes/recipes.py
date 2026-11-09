from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.analysis import analyze_recipe_by_id
from server.deps import get_state
from server.routes._helpers import opts_from_req
from server.schemas import RecipeReq
from server.serializers import serialize_recipe_list

router = APIRouter(tags=["recipes"])


@router.post("/recipe")
def recipe(req: RecipeReq) -> dict:
    """Анализ всех рецептов для item_id."""
    opts = opts_from_req(req)
    ctx = get_state().build_context(opts)
    analyses = analyze_recipe_by_id(req.item_id, opts, ctx)
    if not analyses:
        raise HTTPException(404, f"Рецепт для item_id={req.item_id} не найден")
    return {"item_id": req.item_id, 
            "recipes": serialize_recipe_list(
                analyses, ctx.item_index, opts.lang)}