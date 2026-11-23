"""Расчёты рыночной аналитики, общие для CLI, HTTP и Desktop."""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from config import LOCAL_TIMEZONE
from services.history_store import load_deals, load_snapshots

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(LOCAL_TIMEZONE)
except Exception:
    _TZ = None


def _since_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_item_data(item_id: str, days: int = 7):
    """Загружает сделки и снапшоты за окно в днях. Общая точка входа для CLI и API."""
    since = _since_iso(days)
    return load_deals(item_id, since=since), load_snapshots(item_id, since=since)


# ──────────────────────────────────────────────────────────────────
#  Ликвидность
# ──────────────────────────────────────────────────────────────────
def _liquidity(deals, snapshots, days):
    n_days = max(days, 1)
    units = sum(d["amount"] for d in deals)
    rub = sum(d["price"] for d in deals)
    units_per_day = units / n_days
    rub_per_day = rub / n_days

    snap_amounts = [s["summary"]["total_amount"] for s in snapshots]
    snap_lots = [s["summary"]["n_lots"] for s in snapshots]
    snap_min = [s["summary"]["min_unit"] for s in snapshots]
    snap_depth = [s["summary"]["depth_10pct_amount"] for s in snapshots]

    active_amount = statistics.median(snap_amounts) if snap_amounts else 0
    active_lots = statistics.median(snap_lots) if snap_lots else 0
    min_unit = statistics.median(snap_min) if snap_min else 0
    depth_amount = statistics.median(snap_depth) if snap_depth else 0

    median_sold = statistics.median([d["unit"] for d in deals]) if deals else 0

    days_to_sell = (active_amount / units_per_day) if units_per_day > 0 else None
    turnover = (units_per_day / (active_amount + units_per_day)
                if (active_amount + units_per_day) > 0 else None)
    spread_pct = ((min_unit - median_sold) / median_sold * 100
                  if median_sold > 0 and min_unit > 0 else None)

    if units_per_day >= 50 and (days_to_sell is None or days_to_sell <= 2):
        level, level_code = "🟢 ВЫСОКАЯ", "HIGH"
    elif units_per_day >= 5 and (days_to_sell is None or days_to_sell <= 7):
        level, level_code = "🟡 СРЕДНЯЯ", "MEDIUM"
    else:
        level, level_code = "🔴 НИЗКАЯ", "LOW"

    return {
        "deals": len(deals),
        "units": units,
        "rub": rub,
        "deals_per_day": len(deals) / n_days,
        "units_per_day": units_per_day,
        "rub_per_day": rub_per_day,
        "active_amount": active_amount,
        "active_lots": active_lots,
        "min_unit": min_unit,
        "median_sold": median_sold,
        "depth_amount": depth_amount,
        "days_to_sell": days_to_sell,
        "turnover": turnover,
        "spread_pct": spread_pct,
        "level": level,
        "level_code": level_code,
    }


def _best_time(deals, days):
    """Возвращает {'by_hour': [...], 'by_weekday': [...], 'by_day': [...], 'overall_median': float}.
    Дневная выборка обрезана до последних 7 дней (для тренда)."""
    empty = {"by_hour": [], "by_weekday": [], "by_day": [], "overall_median": 0}
    if not deals:
        return empty

    by_hour: dict[int, list[float]] = defaultdict(list)
    by_wd: dict[int, list[float]] = defaultdict(list)
    by_day: dict[str, list[float]] = defaultdict(list)

    for d in deals:
        dt = _parse_iso(d.get("time"))
        if not dt:
            continue
        local = dt.astimezone(_TZ) if _TZ is not None else dt
        by_hour[local.hour].append(d["unit"])
        by_wd[local.weekday()].append(d["unit"])
        by_day[local.strftime("%Y-%m-%d")].append(d["unit"])

    all_units = [d["unit"] for d in deals]
    overall = statistics.median(all_units) if all_units else 0

    def make_bucket(prices: list[float]):
        if len(prices) < 3:
            return None
        med = statistics.median(prices)
        delta = (med - overall) / overall * 100 if overall else 0
        action = "buy" if delta < -3 else ("sell" if delta > 3 else None)
        return med, delta, action

    by_hour_out = []
    for h in range(24):
        prices = by_hour.get(h, [])
        b = make_bucket(prices)
        if b is None:
            continue
        med, delta, action = b
        by_hour_out.append({
            "hour": h, "n": len(prices), "median": med,
            "dev_pct": delta, "action": action,
        })

    by_wd_out = []
    for wd in range(7):
        prices = by_wd.get(wd, [])
        b = make_bucket(prices)
        if b is None:
            continue
        med, delta, action = b
        by_wd_out.append({
            "weekday": wd, "n": len(prices), "median": med,
            "dev_pct": delta, "action": action,
        })

    by_day_out = []
    for day in sorted(by_day.keys()):
        prices = by_day[day]
        med = statistics.median(prices)
        delta = (med - overall) / overall * 100 if overall else 0
        by_day_out.append({
            "date": day, "n": len(prices), "median": med,
            "dev_pct": delta, "action": None,
        })

    return {
        "by_hour": by_hour_out,
        "by_weekday": by_wd_out,
        "by_day": by_day_out[-7:],
        "overall_median": overall,
    }


def _data_quality_warnings(deals, snapshots, days):
    """Возвращает список предупреждений (пустой, если данных достаточно)."""
    warnings = []
    if len(snapshots) < 3:
        warnings.append(
            f"снапшотов: {len(snapshots)} — для стабильных метрик ликвидности нужно ≥3 (лучше 10+)"
        )
    unique_days = len({d.get("time", "")[:10] for d in deals if d.get("time")})
    if unique_days < 3:
        warnings.append(f"дней со сделками: {unique_days} — для трендов нужно ≥3 дня")
    if len(deals) < 30:
        warnings.append(f"сделок: {len(deals)} — для медиан нужно ≥30")
    return warnings


def analyze_market(item_id: str, days: int = 7) -> dict:
    """Возвращает рыночную аналитику в общем JSON-совместимом формате."""
    deals, snapshots = load_item_data(item_id, days)
    if not deals and not snapshots:
        return {
            "item_id": item_id,
            "days": days,
            "liquidity": None,
            "best_time": None,
            "warnings": ["Нет данных: сначала соберите историю через collect_history"],
        }
    return {
        "item_id": item_id,
        "days": days,
        "liquidity": _liquidity(deals, snapshots, days),
        "best_time": _best_time(deals, days),
        "warnings": _data_quality_warnings(deals, snapshots, days),
    }



def analyze_market_from_market_data(item_id: str, days: int = 7) -> dict:
    """Аналитика только по почасовым агрегатам; активные лоты не моделируются."""
    from services.market_data import load_item_hours

    rows = load_item_hours(item_id, days)
    if not rows:
        return {
            "item_id": item_id, "days": days, "liquidity": None,
            "best_time": None,
            "warnings": ["Нет локальных почасовых данных. Синхронизируйте market-data."],
        }

    deals = sum(int(row.get("deals") or 0) for row in rows)
    units = sum(int(row.get("amount") or 0) for row in rows)
    rub = sum(float(row.get("turnover") or 0) for row in rows)
    first_hour = _parse_iso(rows[0].get("hour"))
    covered_days = (
        (datetime.now(timezone.utc) - first_hour.astimezone(timezone.utc)).days + 1
        if first_hour else days
    )
    n_days = max(1, min(days, covered_days))
    medians = [float(row.get("median_unit") or 0) for row in rows
               if float(row.get("median_unit") or 0) > 0]
    overall = statistics.median(medians) if medians else 0.0

    by_hour: dict[int, list[tuple[float, int]]] = defaultdict(list)
    by_weekday: dict[int, list[tuple[float, int]]] = defaultdict(list)
    by_day: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for row in rows:
        dt = _parse_iso(row.get("hour"))
        price = float(row.get("median_unit") or 0)
        count = int(row.get("deals") or 0)
        if not dt or price <= 0:
            continue
        local = dt.astimezone(_TZ) if _TZ is not None else dt
        by_hour[local.hour].append((price, count))
        by_weekday[local.weekday()].append((price, count))
        by_day[local.strftime("%Y-%m-%d")].append((price, count))

    def bucket(values, key, key_name):
        result = []
        for label in sorted(values):
            entries = values[label]
            sample_n = sum(n for _, n in entries)
            if sample_n <= 0:
                continue
            median = statistics.median(price for price, _ in entries)
            delta = (median - overall) / overall * 100 if overall else 0
            result.append({key_name: label, "n": sample_n, "median": median,
                           "dev_pct": delta,
                           "action": "buy" if delta < -3 else ("sell" if delta > 3 else None)})
        return result

    units_per_day = units / n_days
    level, level_code = (
        ("🟢 ВЫСОКАЯ", "HIGH") if units_per_day >= 50 else
        ("🟡 СРЕДНЯЯ", "MEDIUM") if units_per_day >= 5 else
        ("🔴 НИЗКАЯ", "LOW")
    )
    return {
        "item_id": item_id, "days": days,
        "liquidity": {
            "deals": deals, "units": units, "rub": rub,
            "deals_per_day": deals / n_days, "units_per_day": units / n_days,
            "rub_per_day": rub / n_days,
            "active_amount": None, "active_lots": None, "min_unit": None,
            "median_sold": overall, "depth_amount": None,
            "days_to_sell": None, "turnover": None, "spread_pct": None,
            "level": level, "level_code": level_code,
        },
        "best_time": {
            "by_hour": bucket(by_hour, "hour", "hour"),
            "by_weekday": bucket(by_weekday, "weekday", "weekday"),
            "by_day": bucket(by_day, "date", "date")[-7:],
            "overall_median": overall,
        },
        "warnings": [
            f"Расчёт охватывает {n_days} дн. фактических данных (в ветке market-data хранится ограниченная история).",
            "Данные агрегированы по часам: отдельные сделки недоступны.",
            "Активные лоты, глубина рынка и спред не рассчитываются: snapshots отсутствуют.",
        ],
    }
