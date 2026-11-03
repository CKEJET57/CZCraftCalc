"""
scripts/collect_history.py — сбор истории сделок и снапшотов лотов.

  python -m scripts.collect_history --items zz1o2 rwol5 404p --verbose
  python -m scripts.collect_history --auto --every 1800
"""

import argparse
import sys
import time
from datetime import datetime, timezone

from api.auth import fetch_token
from config import DEFAULT_REGION
from services.history_store import (
    append_deals, append_snapshot, build_snapshot,
    load_deal_hashes, load_state, normalize_deal,
    save_state, tracked_items,
)
from services.price import PriceService


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def collect_once(price_service: PriceService, items: list[str],
                 limit: int = 200, verbose: bool = False) -> dict:
    state = load_state()
    summary = {"items": 0, "new_deals": 0, "snapshots": 0, "errors": 0}

    for item_id in items:
        summary["items"] += 1
        ts_now = datetime.now(timezone.utc).isoformat()

        # ─── 1. Deals ───
        try:
            history = price_service.get_history(item_id, limit)
        except Exception as e:
            summary["errors"] += 1
            _log(f"  ✗ {item_id}/history: {type(e).__name__}: {e}")
            history = []

        new_deals = []
        if history:
            seen = load_deal_hashes(item_id)
            for raw in history:
                norm = normalize_deal(item_id, raw)
                if norm is None or norm["_hash"] in seen:
                    continue
                seen.add(norm["_hash"])
                new_deals.append(norm)
            summary["new_deals"] += append_deals(item_id, new_deals)

        # ─── 2. Snapshot ───
        try:
            lots_data = price_service.get_lots(item_id, limit)
        except Exception as e:
            summary["errors"] += 1
            _log(f"  ✗ {item_id}/lots: {type(e).__name__}: {e}")
            lots_data = {"total": 0, "lots": []}

        snap = build_snapshot(item_id, lots_data["total"], lots_data["lots"])
        if snap:
            append_snapshot(item_id, snap)
            summary["snapshots"] += 1

        # ─── 3. State ───
        state[item_id] = {
            "last_run": ts_now,
            "last_deals": len(new_deals),
            "last_snapshot": bool(snap),
            "lots_total": lots_data["total"],
            "lots_sampled": len(lots_data["lots"]),
        }

        if verbose or new_deals or snap:
            extra = (f", snapshot lots={len(lots_data['lots'])}"
                     f" total={lots_data['total']}")
            _log(f"  · {item_id}: +{len(new_deals)} deals{extra}")

    save_state(state)
    return summary


def run_daemon(price_service, items, interval, limit, verbose):
    _log(f"Демон: itemId={len(items)}, интервал={interval}с ({interval//60}мин)")
    try:
        while True:
            t0 = time.time()
            _log(f"▶ проход ({len(items)} itemId)")
            summary = collect_once(price_service, items, limit, verbose)
            _log(f"✓ items={summary['items']} "
                 f"new_deals={summary['new_deals']} "
                 f"snapshots={summary['snapshots']} "
                 f"errors={summary['errors']} ({time.time()-t0:.1f}s)")
            sleep_for = max(0, interval - (time.time() - t0))
            _log(f"⏸  пауза {sleep_for:.0f}с")
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        _log("⏹  остановлено")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--items", nargs="+", default=None)
    p.add_argument("--auto", action="store_true")
    p.add_argument("--every", type=int, default=None)
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--region", default=DEFAULT_REGION)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    items: list[str] = []
    if args.items:
        items.extend(args.items)
    if args.auto:
        items.extend(tracked_items())
    items = list(dict.fromkeys(items))

    if not items:
        print("Нет itemId: --items или создай историю для --auto")
        return 1

    try:
        token = fetch_token()["access_token"]
    except Exception as e:
        print(f"[FATAL] OAuth: {type(e).__name__}: {e}")
        return 1

    ps = PriceService(
        token, region=args.region,
        use_history=True, max_requests=10_000,
        heartbeat=False, verbose=args.verbose,
    )
    try:
        if args.every:
            run_daemon(ps, items, args.every, args.limit, args.verbose)
            return 0
        summary = collect_once(ps, items, args.limit, args.verbose)
        _log(f"✓ items={summary['items']} new_deals={summary['new_deals']} "
             f"snapshots={summary['snapshots']} errors={summary['errors']}")
        return 0
    finally:
        ps.stop_heartbeat()


if __name__ == "__main__":
    sys.exit(main())