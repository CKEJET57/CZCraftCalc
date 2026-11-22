from __future__ import annotations

from fastapi import APIRouter, Query

from server.deps import get_state
from services.top_items import get_top_items

router = APIRouter(tags=["market"])


@router.get("/top-items")
def top_items(limit: int = Query(100, ge=1, le=500)) -> dict:
    return get_top_items(get_state(), limit=limit)
