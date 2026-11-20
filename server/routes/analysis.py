from __future__ import annotations

from fastapi import APIRouter, Query

from services.market_analysis import analyze_market

router = APIRouter(tags=["analysis"])


@router.get("/market-analysis/{item_id}")
def market_analysis(item_id: str, days: int = Query(7, ge=1, le=90)):
    return analyze_market(item_id, days)
