from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.deps import get_state
from server.schemas import HistoryReq
from services.application import history_operation

router = APIRouter(tags=["history"])


@router.post("/history")
def history(req: HistoryReq) -> dict:
    result = history_operation(get_state(), req.model_dump())
    if result is None:
        raise HTTPException(404, f"Нет истории для {req.item_id}")
    return result
