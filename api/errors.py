"""
api/errors.py — общие исключения API.
"""


class ApiAuthError(RuntimeError):
    """401 — токен протух или неверный."""