"""
scripts/analyze.py — сводка по истории: ликвидность и лучшее время.

  python -m scripts.analyze zz1o2 --days 7
  python -m scripts.analyze zz1o2 --days 30 --name "Фасолевый суп"
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


# ──────────────────────────────────────────────────────────────────
#  Ликвидность
# ──────────────────────────────────────────────────────────────────
def _liquidity(deals, snapshots, days):
    n_days = max(days, 1)
    units = sum(d["amount"] for d in deals)
    rub = sum(d["price"] for d in deals)
    units_per_day = units / n_days
    rub_per_day = rub / n_days

    # активные лоты — медиана по всем снапшотам
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

    # классификация
    if units_per_day >= 50 and (days_to_sell is None or days_to_sell <= 2):
        level = "🟢 ВЫСОКАЯ"
    elif units_per_day >= 5 and (days_to_sell is None or days_to_sell <= 7):
        level = "🟡 СРЕДНЯЯ"
    else:
        level = "🔴 НИЗКАЯ"

    return {
        "deals": len(deals), "units": units, "rub": rub,
        "deals_per_day": len(deals) / n_days,
        "units_per_day": units_per_day,
        "rub_per_day": rub_per_day,
        "active_amount": active_amount, "active_lots": active_lots,
        "min_unit": min_unit, "median_sold": median_sold,
        "depth_amount": depth_amount,
        "days_to_sell": days_to_sell, "turnover": turnover,
        "spread_pct": spread_pct, "level": level,
    }


def _print_liquidity(liq, days, n_snapshots):
    print(f"\n━━━ ЛИКВИДНОСТЬ (окно {days} дн.) ━━━")
    print(f"  Сделок:        {liq['deals']:>6}  "
          f"({liq['deals_per_day']:.1f}/день)")
    print(f"  Единиц:        {liq['units']:>6}  "
          f"({liq['units_per_day']:.1f}/день)")
    print(f"  Оборот:        {fmt_price(liq['rub_per_day'])}/день")
    print()
    print(f"  Активных лотов (медиана):   {liq['active_lots']:.0f}  "
          f"[по {n_snapshots} снапшотам]")
    print(f"  Объём стакана (медиана):    {liq['active_amount']:.0f} ед.")
    print(f"  Глубина ≤ +10% от min:      {liq['depth_amount']:.0f} ед.")
    print()
    print(f"  Min цена (медиана):         {fmt_price(liq['min_unit'])}/шт")
    print(f"  Медиана продаж:             {fmt_price(liq['median_sold'])}/шт")
    if liq["spread_pct"] is not None:
        sign = "ниже" if liq["spread_pct"] < 0 else "выше"
        print(f"  Спред:                      "
              f"{abs(liq['spread_pct']):.1f}% ({sign} медианы продаж)")
    if liq["days_to_sell"] is not None:
        print(f"  Разгрести стакан:           {liq['days_to_sell']:.1f} дн.")
    if liq["turnover"] is not None:
        print(f"  Оборачиваемость:            {liq['turnover']*100:.0f}% в день")
    print(f"\n  ➜ Ликвидность: {liq['level']}")


# ──────────────────────────────────────────────────────────────────
#  Лучшее время
# ──────────────────────────────────────────────────────────────────
def _best_time(deals, days):
    if not deals:
        return

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

    print(f"\n━━━ ЛУЧШЕЕ ВРЕМЯ (часы: {_TZ_LABEL}) ━━━")
    print(f"  Общая медиана: {fmt_price(overall)}/шт\n")

    # --- по часам ---
    if by_hour:
        print("  По часам (только часы с ≥3 сделками):")
        print(f"    {'час':>4} {'сделок':>7} {'медиана':>12} {'откл.':>8}")
        shown = 0
        for h in range(24):
            prices = by_hour.get(h, [])
            if len(prices) < 3:
                continue
            shown += 1
            med = statistics.median(prices)
            delta = (med - overall) / overall * 100 if overall else 0
            marker = " ← купить" if delta < -3 else (" ← продать" if delta > 3 else "")
            print(f"    {h:>4} {len(prices):>7} {fmt_price(med):>12} "
                  f"{delta:>+7.1f}%{marker}")
        if shown == 0:
            print("    (мало данных — нужно ≥3 сделок на час)")

    # --- по дням недели ---
    if by_wd:
        unique_days = len(by_day)
        print(f"\n  По дням недели (дней в выборке: {unique_days}):")
        names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        shown = 0
        for wd in range(7):
            prices = by_wd.get(wd, [])
            if len(prices) < 3:
                continue
            shown += 1
            med = statistics.median(prices)
            delta = (med - overall) / overall * 100 if overall else 0
            marker = " ← купить" if delta < -3 else (" ← продать" if delta > 3 else "")
            print(f"    {names[wd]:>2} {len(prices):>5} {fmt_price(med):>12} "
                  f"{delta:>+7.1f}%{marker}")
        if shown == 0:
            print("    (мало данных — нужна выборка за несколько дней недели)")

    # --- тренд по дням ---
    if len(by_day) >= 2:
        print(f"\n  Тренд по дням (последние {min(7, len(by_day))}):")
        days_sorted = sorted(by_day.keys())
        for day in days_sorted[-7:]:
            med = statistics.median(by_day[day])
            bar = "█" * max(1, int((med / overall) * 10)) if overall else ""
            print(f"    {day}  {fmt_price(med):>10}  {bar}")


# ──────────────────────────────────────────────────────────────────
#  Общая сводка
# ──────────────────────────────────────────────────────────────────
def _data_quality_warnings(deals, snapshots, days):
    warnings = []
    if len(snapshots) < 3:
        warnings.append(
            f"снапшотов: {len(snapshots)} — для стабильных метрик "
            f"ликвидности нужно ≥3 (лучше 10+)"
        )
    unique_days = len({d.get("time", "")[:10] for d in deals if d.get("time")})
    if unique_days < 3:
        warnings.append(
            f"дней со сделками: {unique_days} — для трендов нужно ≥3 дня"
        )
    if len(deals) < 30:
        warnings.append(
            f"сделок: {len(deals)} — для медиан нужно ≥30"
        )
    if warnings:
        print("\n  ⚠️  ДАННЫХ МАЛО (продолжайте сбор):")
        for w in warnings:
            print(f"     · {w}")


# ──────────────────────────────────────────────────────────────────
#  Entrypoint
# ──────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="Анализ истории сделок и снапшотов")
    p.add_argument("item_id", nargs="?", default=None,
                   help="itemId для анализа (или --all)")
    p.add_argument("--days", type=int, default=7,
                   help="Окно анализа в днях (по умолчанию 7)")
    p.add_argument("--name", default=None, help="Имя для заголовка")
    p.add_argument("--all", action="store_true",
                   help="Показать все tracked itemId (без детального анализа)")
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

    since = _since_iso(args.days)
    deals = load_deals(args.item_id, since=since)
    snapshots = load_snapshots(args.item_id, since=since)

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

    _best_time(deals, args.days)
    _data_quality_warnings(deals, snapshots, args.days)

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())