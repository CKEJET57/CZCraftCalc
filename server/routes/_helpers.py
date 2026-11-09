"""Внутренние утилиты: конвертеры схем → AnalysisOptions."""
from __future__ import annotations

from core.options import AnalysisOptions
from server.schemas import AnalysisReqBase


def opts_from_req(req: AnalysisReqBase) -> AnalysisOptions:
    return AnalysisOptions(
        region=req.region,
        lang=req.lang,
        fee=req.fee,
        recursive=req.recursive,
        max_depth=req.max_depth,
        no_fallback=req.no_fallback,
        no_history=req.no_history,
        workers=req.workers,
        no_heartbeat=True,   # в API heartbeat не нужен
        verbose=False,       # не логируем HTTP в stderr
        ignore_missing=req.ignore_missing,
        exclude=",".join(req.exclude),
    )