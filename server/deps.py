"""Совместимый фасад состояния для HTTP-адаптера."""
from services.app_state import AppState, get_state

__all__ = ["AppState", "get_state"]
