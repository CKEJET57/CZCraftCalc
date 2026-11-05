"""
services/history_store.py — хранилище истории сделок и снапшотов лотов.

Структура:
  database/history/
  ├── deals/<item_id>.jsonl        — сделки из /history (с дедупом)
  ├── snapshots/<item_id>.jsonl    — снапшоты /lots (одна строка = один момент)
  └── .state.json                  — служебное состояние

Снапшот — компактный: summary + top-50 дешёвых лотов.
Полный список не храним: раздувает файлы без пользы для метрик.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from config import DB_DIR

HISTORY_DIR = DB_DIR / "history"
DEALS_DIR = HISTORY_DIR / "deals"
SNAPSHOTS_DIR = HISTORY_DIR / "snapshots"
STATE_FILE = HISTORY_DIR / ".state.json"

SNAPSHOT_LOTS_LIMIT = 50   # сколько лотов сохраняем в снапшоте


# ──────────────────────────────────────────────────────────────────
#  Пути
# ──────────────────────────────────────────────────────────────────
def _ensure_dirs() -> None:
    DEALS_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def deals_path(item_id: str) -> Path:
    return DEALS_DIR / f"{item_id}.jsonl"


def snapshots_path(item_id: str) -> Path:
    return SNAPSHOTS_DIR / f"{item_id}.jsonl"


# ──────────────────────────────────────────────────────────────────
#  Deals (поток /history)
# ──────────────────────────────────────────────────────────────────
def _deal_hash(item_id: str, raw: dict) -> str:
    raw_key = (f"{item_id}|{raw.get('time')}|"
               f"{raw.get('price')}|{raw.get('amount')}")
    return hashlib.sha1(raw_key.encode()).hexdigest()


def normalize_deal(item_id: str, raw: dict) -> dict | None:
    """Приводит raw-сделку из API к записи для файла. None если невалидна."""
    try:
        price = float(raw.get("price", 0))
        amount = int(raw.get("amount", 0))
    except (TypeError, ValueError):
        return None
    if price <= 0 or amount <= 0:
        return None
    return {
        "item": item_id,
        "price": price,
        "amount": amount,
        "unit": price / amount,
        "time": raw.get("time") or raw.get("timestamp"),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "_hash": _deal_hash(item_id, raw),
    }


def load_deal_hashes(item_id: str) -> set[str]:
    path = deals_path(item_id)
    if not path.exists():
        return set()
    hashes: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
                h = d.get("_hash")
                if h:
                    hashes.add(h)
            except json.JSONDecodeError:
                continue
    return hashes


def append_deals(item_id: str, deals: list[dict]) -> int:
    if not deals:
        return 0
    _ensure_dirs()
    with deals_path(item_id).open("a", encoding="utf-8") as f:
        for d in deals:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return len(deals)


def load_deals(item_id: str, since: str | None = None) -> list[dict]:
    """Все сделки item (опционально — с since по time, ISO8601)."""
    path = deals_path(item_id)
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since and (d.get("time") or "") < since:
                continue
            out.append(d)
    return out


# ──────────────────────────────────────────────────────────────────
#  Snapshots (снимок /lots)
# ──────────────────────────────────────────────────────────────────
def normalize_lot(raw: dict) -> dict | None:
    """Компактная запись лота: amount, current, buyout, unit, start, end."""
    try:
        amount = int(raw.get("amount", 0))
        current = float(raw.get("currentPrice", 0) or 0)
        buyout = float(raw.get("buyoutPrice", 0) or 0)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    # цена для покупателя: buyout, если задан, иначе current
    effective = buyout if buyout > 0 else current
    if effective <= 0:
        return None
    return {
        "amount": amount,
        "current": current,
        "buyout": buyout,
        "unit": effective / amount,
        "start": raw.get("startTime"),
        "end": raw.get("endTime"),
    }


def build_snapshot(item_id: str, total: int, raw_lots: list[dict]) -> dict | None:
    """Собирает снапшот: summary + top-50 самых дешёвых лотов."""
    lots = [norm for raw in raw_lots if (norm := normalize_lot(raw)) is not None]
    if not lots:
        return None

    units = sorted(l["unit"] for l in lots)
    n = len(units)
    summary = {
        "n_lots": n,
        "total_amount": sum(l["amount"] for l in lots),
        "min_unit": units[0],
        "median_unit": units[n // 2],
        "max_unit": units[-1],
        "p25_unit": units[n // 4],
        "p75_unit": units[3 * n // 4],
    }

    # глубина: сколько лотов в пределах +10% от min
    depth_cutoff = units[0] * 1.1
    depth_lots = [l for l in lots if l["unit"] <= depth_cutoff]
    summary["depth_10pct_lots"] = len(depth_lots)
    summary["depth_10pct_amount"] = sum(l["amount"] for l in depth_lots)

    top = sorted(lots, key=lambda l: l["unit"])[:SNAPSHOT_LOTS_LIMIT]

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "item": item_id,
        "total": int(total),                 # что отдал API в total
        "sampled": n,                        # сколько лотов пришло в ответе
        "summary": summary,
        "lots": top,
    }


def append_snapshot(item_id: str, snapshot: dict) -> int:
    if not snapshot:
        return 0
    _ensure_dirs()
    with snapshots_path(item_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    return 1


def load_snapshots(item_id: str, since: str | None = None) -> list[dict]:
    path = snapshots_path(item_id)
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since and (d.get("ts") or "") < since:
                continue
            out.append(d)
    return out


# ──────────────────────────────────────────────────────────────────
#  Общее
# ──────────────────────────────────────────────────────────────────
def tracked_items() -> list[str]:
    items: set[str] = set()
    for d in (DEALS_DIR, SNAPSHOTS_DIR):
        if d.exists():
            items.update(p.stem for p in d.glob("*.jsonl"))
    return sorted(items)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state: dict) -> None:
    _ensure_dirs()
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def trim_old(item_id: str, days: int = 30) -> tuple[int, int]:
    """Удаляет записи старше N дней из deals и snapshots. Возвращает (d_removed, s_removed)."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    d_removed = 0
    path = deals_path(item_id)
    if path.exists():
        kept = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (d.get("time") or "") >= cutoff:
                kept.append(line)
            else:
                d_removed += 1
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    s_removed = 0
    path = snapshots_path(item_id)
    if path.exists():
        kept = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (d.get("ts") or "") >= cutoff:
                kept.append(line)
            else:
                s_removed += 1
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    return d_removed, s_removed