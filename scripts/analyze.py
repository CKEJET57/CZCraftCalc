"""
scripts/analyze.py — сводка по истории: ликвидность и лучшее время.

  python -m scripts.analyze zz1o2 --days 7
  python -m scripts.analyze zz1o2 --days 30 --name "Фасолевый суп"

Функции _liquidity / _best_time / _data_quality_warnings возвращают данные.
Печать вынесена в _print_* и CLI-обёртку.
"""

import argparse
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from config import LOCAL_TIMEZONE
from core.display import fmt_price
from services.history_store import load_deals, load_snapshots

# --- Windows без tzdata: graceful fallback ---
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(LOCAL_TIMEZONE)
    _TZ_LABEL = LOCAL_TIMEZONE
except Exception:
    _TZ = None
    _TZ_LABEL = "UTC (tzdata не установлен — pip install tzdata)"


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


def _print_liquidity(liq, days, n_snapshots):
    print(f"\n━━━ ЛИКВИДНОСТЬ (окно {days} дн.) ━━━")
    print(f"  Сделок:        {liq['deals']:>6}  ({liq['deals_per_day']:.1f}/день)")
    print(f"  Единиц:        {liq['units']:>6}  ({liq['units_per_day']:.1f}/день)")
    print(f"  Оборот:        {fmt_price(liq['rub_per_day'])}/день")
    print()
    print(f"  Активных лотов (медиана):   {liq['active_lots']:.0f}  [по {n_snapshots} снапшотам]")
    print(f"  Объём стакана (медиана):    {liq['active_amount']:.0f} ед.")
    print(f"  Глубина ≤ +10% от min:      {liq['depth_amount']:.0f} ед.")
    print()
    print(f"  Min цена (медиана):         {fmt_price(liq['min_unit'])}/шт")
    print(f"  Медиана продаж:             {fmt_price(liq['median_sold'])}/шт")
    if liq["spread_pct"] is not None:
        sign = "ниже" if liq["spread_pct"] < 0 else "выше"
        print(f"  Спред:                      {abs(liq['spread_pct']):.1f}% ({sign} медианы продаж)")
    if liq["days_to_sell"] is not None:
        print(f"  Разгрести стакан:           {liq['days_to_sell']:.1f} дн.")
    if liq["turnover"] is not None:
        print(f"  Оборачиваемость:            {liq['turnover']*100:.0f}% в день")
    print(f"\n  ➜ Ликвидность: {liq['level']}")


# ──────────────────────────────────────────────────────────────────
#  Лучшее время
# ──────────────────────────────────────────────────────────────────
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


def _print_best_time(best, days):
    if not best.get("by_hour") and not best.get("by_weekday") and not best.get("by_day"):
        return

    overall = best.get("overall_median", 0)
    print(f"\n━━━ ЛУЧШЕЕ ВРЕМЯ (часы: {_TZ_LABEL}) ━━━")
    print(f"  Общая медиана: {fmt_price(overall)}/шт\n")

    if best["by_hour"]:
        print("  По часам (только часы с ≥3 сделками):")
        print(f"    {'час':>4} {'сделок':>7} {'медиана':>12} {'откл.':>8}")
        for b in best["by_hour"]:
            marker = " ← купить" if b["action"] == "buy" else (" ← продать" if b["action"] == "sell" else "")
            print(f"    {b['hour']:>4} {b['n']:>7} {fmt_price(b['median']):>12} {b['dev_pct']:>+7.1f}%{marker}")
    else:
        print("    (мало данных — нужно ≥3 сделок на час)")

    if best["by_weekday"]:
        names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        print("\n  По дням недели:")
        for b in best["by_weekday"]:
            marker = " ← купить" if b["action"] == "buy" else (" ← продать" if b["action"] == "sell" else "")
            print(f"    {names[b['weekday']]:>2} {b['n']:>5} {fmt_price(b['median']):>12} {b['dev_pct']:>+7.1f}%{marker}")

    if len(best["by_day"]) >= 2:
        print(f"\n  Тренд по дням (последние {len(best['by_day'])}):")
        for b in best["by_day"]:
            bar = "█" * max(1, int((b["median"] / overall) * 10)) if overall else ""
            print(f"    {b['date']}  {fmt_price(b['median']):>10}  {bar}")


# ──────────────────────────────────────────────────────────────────
#  Качество данных
# ──────────────────────────────────────────────────────────────────
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


def _print_warnings(warnings):
    if not warnings:
        return
    print("\n  ⚠️  ДАННЫХ МАЛО (продолжайте сбор):")
    for w in warnings:
        print(f"     · {w}")


# ──────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="Анализ истории сделок и снапшотов")
    p.add_argument("item_id", nargs="?", default=None, help="itemId для анализа (или --all)")
    p.add_argument("--days", type=int, default=7, help="Окно анализа в днях (по умолчанию 7)")
    p.add_argument("--name", default=None, help="Имя для заголовка")
    p.add_argument("--all", action="store_true", help="Показать все tracked itemId (без детального анализа)")
    args = p.parse_args()

    if args.all:
        from services.history_store import tracked_items
        items = tracked_items()
        if not items:
            print("Нет отслеживаемых предметов.")
            return 1
        print(f"Отслеживается {len(items)} предметов:\n")
        for iid in items:
            d = load_deals(iid)
            s = load_snapshots(iid)
            print(f"  {iid:10s}  deals={len(d):>5}  snapshots={len(s):>4}")
        return 0

    if not args.item_id:
        print("Укажи item_id или --all")
        return 1

    deals, snapshots = load_item_data(args.item_id, args.days)

    title = f"{args.name or ''} ({args.item_id})".strip()
    print(f"\n╔══════════════════════════════════════════════════════════╗")
    print(f"  📊 Анализ: {title}")
    print(f"╚══════════════════════════════════════════════════════════╝")
    print(f"  Период: {args.days} дн.")
    print(f"  Записей: deals={len(deals)}, snapshots={len(snapshots)}")

    if not deals and not snapshots:
        print("\n  ⚠️  Нет данных. Соберите через:")
        print(f"    python -m scripts.collect_history --items {args.item_id}")
        return 1

    liq = _liquidity(deals, snapshots, args.days)
    _print_liquidity(liq, args.days, len(snapshots))

    best = _best_time(deals, args.days)
    _print_best_time(best, args.days)

    _print_warnings(_data_quality_warnings(deals, snapshots, args.days))

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())