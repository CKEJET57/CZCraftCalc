"""
api/errors.py — общие исключения API.
"""


class ApiAuthError(RuntimeError):
    """401 — токен протух или неверный."""

class ApiRateLimitError(RuntimeError):
    """429 — API ограничил частоту запросов после повторных попыток."""
