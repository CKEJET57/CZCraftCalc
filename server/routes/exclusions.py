from __future__ import annotations

from fastapi import APIRouter

from server.schemas import ExclusionsChangeReq, ExclusionsListResp
from storage.exclusions import (
    add_exclusions, clear_exclusions, load_exclusions, remove_exclusions,
)

router = APIRouter(tags=["exclusions"])


@router.get("/exclusions", response_model=ExclusionsListResp)
def list_exclusions() -> ExclusionsListResp:
    return ExclusionsListResp(items=sorted(load_exclusions()))


@router.post("/exclusions/add", response_model=ExclusionsListResp)
def add_items(req: ExclusionsChangeReq) -> ExclusionsListResp:
    add_exclusions(set(req.items))
    return ExclusionsListResp(items=sorted(load_exclusions()))


@router.post("/exclusions/remove", response_model=ExclusionsListResp)
def remove_items(req: ExclusionsChangeReq) -> ExclusionsListResp:
    remove_exclusions(set(req.items))
    return ExclusionsListResp(items=sorted(load_exclusions()))


@router.post("/exclusions/clear", response_model=ExclusionsListResp)
def clear_items() -> ExclusionsListResp:
    clear_exclusions()
    return ExclusionsListResp(items=[])