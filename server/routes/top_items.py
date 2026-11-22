from __future__ import annotations

import requests
from fastapi import APIRouter, HTTPException, Query

from server.deps import get_state
from services.top_items import get_top_items

router = APIRouter(tags=["market"])


@router.get("/top-items")
def top_items(limit: int = Query(100, ge=1, le=500)) -> dict:
    try:
        return get_top_items(get_state(), limit=limit)
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Рейтинг ещё не опубликован или временно недоступен. Повторите запрос позже.",
        ) from exc
