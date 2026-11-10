"""Pydantic-схемы запросов/ответов."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class AnalysisReqBase(BaseModel):
    region: str = "RU"
    lang: str = "ru"
    fee: float = 5.0
    recursive: bool = False
    max_depth: int = 12
    no_fallback: bool = False
    no_history: bool = False
    workers: int = 4
    ignore_missing: bool = False
    exclude: list[str] = Field(default_factory=list)
    use_local_data: bool = False

class RecipeReq(AnalysisReqBase):
    item_id: str


class BatchReq(AnalysisReqBase):
    bench: Literal["workbench", "laboratory_table", "kitchen_table"] | None = None
    category: str | None = None
    perk: str | None = None
    per_category: bool = False
    top: int | None = None
    max_recipes: int | None = None
    sort: Literal["margin", "profit"] = "margin"


class HistoryReq(BaseModel):
    item_id: str
    region: str = "RU"
    lang: str = "ru"
    no_history: bool = False
    limit: int = 200
    sort: Literal["newest", "oldest", "price-asc", "price-desc"] = "newest"
    days: int | None = None
    show: int = 30
    page: int = 0


class CharacterReq(BaseModel):
    name: str
    region: str = "RU"
    lang: str = "ru"
    verbose: bool = False


class ExclusionsListResp(BaseModel):
    items: list[str]


class ExclusionsChangeReq(BaseModel):
    items: list[str]