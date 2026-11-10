# server/routes/_helpers.py
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
        no_heartbeat=True,
        verbose=False,
        ignore_missing=req.ignore_missing,
        exclude=",".join(req.exclude),
        use_local_data=req.use_local_data,
    )