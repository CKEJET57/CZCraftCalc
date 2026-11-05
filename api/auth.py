"""
api/auth.py — OAuth 2.0 client_credentials.

Фичи:
  - requests.Session (keep-alive) — второй запрос в 2× быстрее
  - retry с экспоненциальной паузой на сетевые ошибки и 5xx
  - timeout=(connect, read) вместо единого
  - безопасное сообщение об ошибке (не печатает data целиком)
"""

import sys
import time

import requests

from config import CLIENT_ID, CLIENT_SECRET, OAUTH_URL

_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Ленивая инициализация Session — один на процесс."""
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def fetch_token(max_retries: int = 3, verbose: bool = False) -> dict:
    """
    POST /oauth/token (client_credentials).
    Возвращает dict с access_token и expires_in.

    Retry на:
      - ConnectionError, Timeout, 5xx
    Не retry на:
      - 401/403 (неверный client_secret — бессмысленно повторять)
      - 400 (неверный запрос)
    """
    last_err: Exception | None = None

    for attempt in range(max_retries):
        try:
            resp = _get_session().post(
                OAUTH_URL,
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type": "client_credentials",
                    "scope": "",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=(10, 15),
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            if attempt < max_retries - 1:
                delay = 2 ** attempt
                if verbose:
                    sys.stderr.write(
                        f"  [auth] {type(e).__name__} — retry через {delay}s "
                        f"({attempt + 1}/{max_retries})\n"
                    )
                time.sleep(delay)
                continue
            break

        # 4xx — не retry, сразу ошибка
        if 400 <= resp.status_code < 500:
            if resp.status_code == 401:
                raise RuntimeError(
                    "401 OAuth: неверный client_id или client_secret. "
                    "Проверьте .env / переменные окружения."
                )
            raise RuntimeError(
                f"OAuth {resp.status_code}: {resp.text[:200]}"
            )

        # 5xx — retry
        if resp.status_code >= 500:
            last_err = RuntimeError(f"OAuth {resp.status_code}: {resp.text[:200]}")
            if attempt < max_retries - 1:
                delay = 2 ** attempt
                if verbose:
                    sys.stderr.write(
                        f"  [auth] {resp.status_code} — retry через {delay}s "
                        f"({attempt + 1}/{max_retries})\n"
                    )
                time.sleep(delay)
                continue
            break

        # 200
        try:
            data = resp.json()
        except ValueError as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            break

        if "access_token" not in data:
            keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
            raise RuntimeError(f"Нет access_token в ответе (keys: {keys})")
        return data

    raise RuntimeError(
        f"Не удалось получить токен после {max_retries} попыток: {last_err}"
    )