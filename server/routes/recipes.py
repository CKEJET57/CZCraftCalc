from __future__ import annotations

from fastapi import APIRouter

from server.deps import get_state
from server.schemas import RecipeReq
from services.application import recipe_operation

router = APIRouter(tags=["recipes"])


@router.post("/recipe")
def recipe(req: RecipeReq) -> dict:
    return recipe_operation(get_state(), req.model_dump())
