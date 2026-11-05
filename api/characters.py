"""
api/characters.py — публичный профиль персонажа.
"""
from __future__ import annotations

import requests
from urllib.parse import quote

from api.errors import ApiAuthError
from config import EAPI_BASE


def fetch_character_profile(token: str, region: str, name: str) -> dict | None:
    """
    GET /{region}/character/by-name/{name}/profile

    Возвращает dict с профилем или None, если персонаж не найден (404).
    Бросает ApiAuthError при 401 (неверный токен).
    """
    safe_name = quote(name, safe="")
    url = f"{EAPI_BASE}/{region}/character/by-name/{safe_name}/profile"
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        timeout=(10, 15),
    )
    if resp.status_code == 404:
        return None
    if resp.status_code == 401:
        raise ApiAuthError("401 — токен недействителен")
    resp.raise_for_status()
    return resp.json()