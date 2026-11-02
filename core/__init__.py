"""Оркестрация анализа — общая для CLI и меню."""

from core.context import AnalysisContext, build_context
from core.options import AnalysisOptions
from core.runner import run_batch, run_recipe

__all__ = [
    "AnalysisOptions",
    "AnalysisContext",
    "build_context",
    "run_recipe",
    "run_batch",
]