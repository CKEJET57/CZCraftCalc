"""
api/auction.py — запросы к аукциону.
"""

import requests

from config import DEFAULT_LOTS_LIMIT, EAPI_BASE


def fetch_lots(
    token: str,
    item_id: str,
    region: str,
    limit: int = DEFAULT_LOTS_LIMIT,
) -> dict:
    """GET /{region}/auction/{itemId}/lots"""
    url = f"{EAPI_BASE}/{region}/auction/{item_id}/lots"
    resp = requests.get(
        url,
        params={"limit": limit, "additional": "true"},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=20,
    )
    if resp.status_code == 401:
        raise RuntimeError("401 Unauthorized — токен протух или неверный")
    resp.raise_for_status()
    return resp.json()