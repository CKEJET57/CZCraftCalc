"""
scripts/analyze.py — сводка по истории: ликвидность и лучшее время.

  python -m scripts.analyze zz1o2 --days 7
  python -m scripts.analyze zz1o2 --days 30 --name "Фасолевый суп"

Функции _liquidity / _best_time / _data_quality_warnings возвращают данные.
Печать вынесена в _print_* и CLI-обёртку.
"""

import argparse
import sys

from core.display import fmt_price
from services.history_store import load_deals, load_snapshots
from services.market_analysis import (
    _TZ, _liquidity, _best_time, _data_quality_warnings, load_item_data,
)

# --- Windows без tzdata: graceful fallback ---
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(LOCAL_TIMEZONE)
    _TZ_LABEL = LOCAL_TIMEZONE
except Exception:
    _TZ = None
    _TZ_LABEL = "UTC (tzdata не установлен — pip install tzdata)"


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