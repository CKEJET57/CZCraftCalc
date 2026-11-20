"""Совместимый фасад аналитики.

Реализация разделена по областям ответственности. Импорты из core.analysis
сохранены, чтобы не ломать существующие CLI, HTTP и внешние вызовы.
"""
from core.batch_analysis import (
    BatchResult,
    BatchSection,
    _filter_recipes,
    _group_recipes,
    _round_robin,
    analyze_batch,
)
from core.history_analysis import HistoryResult, analyze_history
from core.prefetch import collect_prefetch_items, prefetch
from core.recipe_analysis import analyze_recipe_by_id

__all__ = [
    "BatchSection",
    "BatchResult",
    "HistoryResult",
    "collect_prefetch_items",
    "prefetch",
    "analyze_recipe_by_id",
    "analyze_batch",
    "analyze_history",
]
