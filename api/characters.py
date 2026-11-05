from urllib.parse import quote
import requests
from config import EAPI_BASE


def fetch_character_profile(token: str, region: str, name: str) -> dict | None:
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
        raise RuntimeError("401 Unauthorized — токен недействителен")
    resp.raise_for_status()
    return resp.json()