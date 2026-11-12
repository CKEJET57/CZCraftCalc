from __future__ import annotations

from fastapi import APIRouter, Query

from scripts.analyze import (
    _liquidity,
    _best_time,
    _data_quality_warnings,
    load_item_data,
)

router = APIRouter(tags=["analysis"])


@router.get("/market-analysis/{item_id}")
def market_analysis(item_id: str, days: int = Query(7, ge=1, le=90)):
    deals, snapshots = load_item_data(item_id, days)

    if not deals and not snapshots:
        return {
            "item_id": item_id,
            "days": days,
            "liquidity": None,
            "best_time": None,
            "warnings": ["Нет данных: сначала соберите историю через collect_history"],
        }

    return {
        "item_id": item_id,
        "days": days,
        "liquidity": _liquidity(deals, snapshots, days),
        "best_time": _best_time(deals, days),
        "warnings": _data_quality_warnings(deals, snapshots, days),
    }