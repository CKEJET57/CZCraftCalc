"""Локальное хранилище почасовых рыночных агрегатов из ветки market-data."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import DB_DIR

REPOSITORY_URL = "https://github.com/CKEJET57/CZCraftCalc.git"
BRANCH = "market-data"
MARKET_DIR = DB_DIR / "market-data"
DEALS_DIR = MARKET_DIR / "deals"
INDEX_FILE = MARKET_DIR / "top_items.json"
_sync_lock = threading.Lock()
_data_lock = threading.Lock()
_rows_cache: dict[str, list[dict]] = {}


def _parse_hour(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def sync_market_data() -> dict:
    """Заменяет локальный mirror только после успешной полной загрузки."""
    with _sync_lock:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="cz-market-sync-") as tmp:
            checkout = Path(tmp) / "repo"
            subprocess.run(
                ["git", "clone", "--depth", "1", "--filter=blob:none",
                 "--sparse", "--branch", BRANCH, REPOSITORY_URL, str(checkout)],
                check=True, capture_output=True, text=True, timeout=600,
            )
            subprocess.run(
                ["git", "sparse-checkout", "set",
                 "database/history/deals", "database/market"],
                cwd=checkout, check=True, capture_output=True, text=True, timeout=120,
            )
            source_deals = checkout / "database" / "history" / "deals"
            source_index = checkout / "database" / "market" / "top_items.json"
            if not source_deals.is_dir() or not source_index.is_file():
                raise RuntimeError("В ветке market-data отсутствуют опубликованные данные.")

            stage = DB_DIR / ".market-data-staging"
            if stage.exists():
                shutil.rmtree(stage)
            (stage / "deals").mkdir(parents=True)
            for source in source_deals.glob("*.jsonl"):
                shutil.copy2(source, stage / "deals" / source.name)
            shutil.copy2(source_index, stage / "top_items.json")
            payload = json.loads((stage / "top_items.json").read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                shutil.rmtree(stage)
                raise RuntimeError("Индекс top_items.json имеет неверный формат.")

            old = DB_DIR / ".market-data-old"
            if old.exists():
                shutil.rmtree(old)
            if MARKET_DIR.exists():
                MARKET_DIR.replace(old)
            try:
                stage.replace(MARKET_DIR)
            except Exception:
                if old.exists() and not MARKET_DIR.exists():
                    old.replace(MARKET_DIR)
                raise
            if old.exists():
                shutil.rmtree(old)

            with _data_lock:
                _rows_cache.clear()
            return {"ok": True, "files": sum(1 for _ in DEALS_DIR.glob("*.jsonl")),
                    "hour": payload.get("hour")}


def market_data_status() -> dict:
    if not INDEX_FILE.is_file() or not DEALS_DIR.is_dir():
        return {"available": False, "hour": None, "files": 0}
    try:
        index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        return {"available": True, "hour": index.get("hour"),
                "files": sum(1 for _ in DEALS_DIR.glob("*.jsonl"))}
    except (OSError, ValueError):
        return {"available": False, "hour": None, "files": 0}


def load_item_hours(item_id: str, days: int | None = None) -> list[dict]:
    """Возвращает почасовые агрегаты предмета в хронологическом порядке."""
    item_id = str(item_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item_id):
        return []
    with _data_lock:
        rows = _rows_cache.get(item_id)
    if rows is None:
        path = DEALS_DIR / f"{item_id}.jsonl"
        loaded: list[dict] = []
        if path.is_file():
            with path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row, dict) and row.get("hour"):
                        loaded.append(row)
        loaded.sort(key=lambda row: row.get("hour") or "")
        with _data_lock:
            _rows_cache[item_id] = loaded
        rows = loaded
    if days is not None and days > 0:
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        rows = [row for row in rows
                if (dt := _parse_hour(row.get("hour"))) is not None
                and dt.timestamp() >= cutoff]
    return list(rows)


def latest_market_hour() -> str | None:
    try:
        payload = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        return payload.get("hour")
    except (OSError, ValueError):
        return None


def latest_item_price(item_id: str) -> tuple[float | None, int]:
    # Для всех ингредиентов используем один общий час из опубликованного индекса.
    hour = latest_market_hour()
    if not hour:
        return None, 0
    for row in reversed(load_item_hours(item_id)):
        if row.get("hour") == hour:
            try:
                value = row.get("median_unit")
                return (float(value), int(row.get("deals") or 0)) if value is not None else (None, 0)
            except (TypeError, ValueError):
                return None, 0
    return None, 0


class MarketDataPriceService:
    """Совместимый интерфейс цены без OAuth и HTTP-запросов."""
    def get(self, item_id: str):
        from services.price import PriceInfo
        price, samples = latest_item_price(item_id)
        return PriceInfo(str(item_id), price,
                         "market-data" if price is not None else "none", samples)

    def is_cached(self, item_id: str) -> bool:
        # Локальное чтение не требует предварительной загрузки в сетевой кэш.
        return True

    def prefetch(self, item_ids, workers: int = 4, progress=None) -> None:
        unique = list(dict.fromkeys(str(value) for value in item_ids if value))
        for index, item_id in enumerate(unique, 1):
            self.get(item_id)
            if progress:
                progress(index, len(unique), item_id)

    def get_history(self, item_id: str, limit: int | None = None) -> list[dict]:
        rows = load_item_hours(item_id)
        if limit is not None and limit > 0:
            rows = rows[-limit:]
        return [{
            "price": float(row.get("turnover") or 0),
            "amount": int(row.get("amount") or 0),
            "unit": float(row.get("median_unit") or 0),
            "time": row.get("hour"),
            "deals": int(row.get("deals") or 0),
            "min_unit": row.get("min_unit"), "max_unit": row.get("max_unit"),
            "avg_unit": row.get("avg_unit"),
        } for row in rows]

    def close(self) -> None:
        return None
