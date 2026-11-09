from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.characters import fetch_character_profile
from core.options import AnalysisOptions
from server.deps import get_state
from server.schemas import CharacterReq

router = APIRouter(tags=["characters"])


@router.post("/character")
def character(req: CharacterReq) -> dict:
    opts = AnalysisOptions(
        region=req.region, lang=req.lang,
        verbose=req.verbose, no_heartbeat=True,
    )
    ctx = get_state().build_context(opts)
    profile = fetch_character_profile(
        ctx.price_service.token, req.region, req.name,
    )
    if profile is None:
        raise HTTPException(404, f"Персонаж «{req.name}» не найден в {req.region}")
    return profile