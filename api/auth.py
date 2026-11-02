"""
api/auth.py — OAuth 2.0 client_credentials.
"""

import requests

from config import CLIENT_ID, CLIENT_SECRET, OAUTH_URL


def fetch_token() -> dict:
    """
    POST /oauth/token (client_credentials).
    Возвращает dict с access_token и expires_in.
    """
    resp = requests.post(
        OAUTH_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": "",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Нет access_token в ответе: {data}")
    return data