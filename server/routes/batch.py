from __future__ import annotations

from fastapi import APIRouter

from server.deps import get_state
from server.schemas import BatchReq
from services.application import batch_operation

router = APIRouter(tags=["batch"])


@router.post("/batch")
def batch(req: BatchReq) -> dict:
    return batch_operation(get_state(), req.model_dump())
