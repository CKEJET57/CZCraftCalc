"""Подготовка истории сделок и расчёт статистики."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HistoryResult:
    item_id: str
    item_name: str
    deals: list[dict]
    stats: dict
    page: int
    page_size: int
    total_pages: int
    raw_sample: dict | None = None


def analyze_history(item_id: str, opts, ctx, *,
                    limit: int = 200,
                    sort: str = "newest",
                    days: int | None = None,
                    show: int = 30,
                    page: int = 0) -> HistoryResult | None:
    """Возвращает историю сделок + статистику. None если сделок нет."""
    import statistics
    from datetime import datetime, timedelta, timezone
    from storage.listing import get_item_name

    history = ctx.price_service.get_history(item_id, limit)
    name = get_item_name(ctx.item_index, item_id, opts.lang)

    if not history:
        return HistoryResult(
            item_id=item_id, item_name=name, deals=[], stats={},
            page=0, page_size=0, total_pages=1,
        )

    deals: list[dict] = []
    for d in history:
        try:
            price = float(d.get("price", 0))
            amount = int(d.get("amount", 0))
        except (TypeError, ValueError):
            continue
        if amount <= 0 or price <= 0:
            continue
        deals.append({
            "price": price,
            "amount": amount,
            "unit": float(d.get("unit") or (price / amount)),
            "time": d.get("time") or d.get("timestamp"),
            "deals": int(d.get("deals") or 1),
            "min_unit": float(d.get("min_unit") or d.get("unit") or (price / amount)),
            "max_unit": float(d.get("max_unit") or d.get("unit") or (price / amount)),
        })
    if not deals:
        return HistoryResult(item_id, name, [], {}, 0, 0, 1)

    if days is not None and days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        filtered = []
        for d in deals:
            if not d["time"]:
                continue
            try:
                dt = datetime.fromisoformat(d["time"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt >= cutoff:
                filtered.append(d)
        deals = filtered
        if not deals:
            return HistoryResult(item_id, name, [], {"empty_reason": f"no deals for last {days}d"}, 0, 0, 1)

    if sort == "newest":
        deals.sort(key=lambda d: d["time"] or "", reverse=True)
    elif sort == "oldest":
        deals.sort(key=lambda d: d["time"] or "")
    elif sort == "price-asc":
        deals.sort(key=lambda d: d["unit"])
    elif sort == "price-desc":
        deals.sort(key=lambda d: d["unit"], reverse=True)

    units = sorted(d["unit"] for d in deals)
    n = len(units)
    trim = int(n * 0.1)
    core = units[trim: n - trim] if trim else units
    stats = {
        "n_deals": sum(d["deals"] for d in deals),
        "total_units": sum(d["amount"] for d in deals),
        "total_rub": sum(d["price"] for d in deals),
        "min": min(d["min_unit"] for d in deals),
        "max": max(d["max_unit"] for d in deals),
        "median": statistics.median(units),
        "median_trim10": statistics.median(core) if core else 0.0,
    }

    if show <= 0:
        show_n = n
        page = 0
        total_pages = 1
    else:
        show_n = show
        total_pages = max(1, (n + show_n - 1) // show_n)
        page = max(0, min(page, total_pages - 1))

    start = page * show_n
    end = min(start + show_n, n)

    return HistoryResult(
        item_id=item_id, item_name=name,
        deals=deals[start:end], stats=stats,
        page=page, page_size=show_n, total_pages=total_pages,
        raw_sample=history[0] if opts.verbose else None,
    )
