from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.analysis import analyze_history
from core.options import AnalysisOptions
from server.deps import get_state
from server.schemas import HistoryReq
from server.serializers import serialize_history

router = APIRouter(tags=["history"])


@router.post("/history")
def history(req: HistoryReq) -> dict:
    opts = AnalysisOptions(
        region=req.region, lang=req.lang,
        no_history=req.no_history,
        no_heartbeat=True, verbose=False,
    )
    ctx = get_state().build_context(opts)
    result = analyze_history(
        req.item_id, opts, ctx,
        limit=req.limit, sort=req.sort,
        days=req.days, show=req.show, page=req.page,
    )
    if result is None:
        raise HTTPException(404, f"Нет истории для {req.item_id}")
    return serialize_history(result)