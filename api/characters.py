"""
api/characters.py — публичный профиль персонажа.
"""

import requests

from config import EAPI_BASE


def fetch_character_profile(token: str, region: str, name: str) -> dict | None:
    """
    GET /{region}/character/by-name/{name}/profile

    Возвращает dict с профилем или None, если персонаж не найден (404).
    Бросает RuntimeError при 401 (неверный токен).
    """
    url = f"{EAPI_BASE}/{region}/character/by-name/{name}/profile"
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        timeout=15,
    )
    if resp.status_code == 404:
        return None
    if resp.status_code == 401:
        raise RuntimeError("401 Unauthorized — токен недействителен")
    resp.raise_for_status()
    return resp.json()