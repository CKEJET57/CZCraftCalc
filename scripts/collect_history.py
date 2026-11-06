"""
scripts/collect_history.py — сбор истории сделок и снапшотов лотов.

  python -m scripts.collect_history --items zz1o2 rwol5 404p --verbose
  python -m scripts.collect_history --auto --every 1800
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from api.auth import fetch_token
from api.errors import ApiAuthError, ApiRateLimitError
from config import DEFAULT_REGION
from services.history_store import (
    append_deals, append_snapshot, build_snapshot,
    load_deal_hashes, load_state, normalize_deal,
    save_state, tracked_items, trim_old,
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
        except (ApiAuthError, ApiRateLimitError):
            raise
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
        except (ApiAuthError, ApiRateLimitError):
            raise
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


def run_daemon(price_service, items, interval, limit, verbose,
               keep_days: int | None = None):
    _log(f"Демон: itemId={len(items)}, интервал={interval}с ({interval//60}мин)")
    try:
        while True:
            if keep_days is not None:
                td = ts = 0
                for iid in items:
                    d, s = trim_old(iid, keep_days)
                    td += d
                    ts += s
                if td or ts:
                    _log(f"trim(>{keep_days}д): -{td} deals, -{ts} snapshots")

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
    p.add_argument("--items", nargs="+", default=None,
                   help="itemId (можно несколько)")
    p.add_argument("--auto", action="store_true",
                   help="Все itemId, для которых уже есть история")
    p.add_argument("--all-listing", action="store_true",
                   help="Все itemId из database/listing_craft.json")
    p.add_argument("--every", type=int, default=None,
                   help="Режим демона: интервал в секундах")
    p.add_argument("--limit", type=int, default=200,
                   help="Сделок/лотов запрашивать у API (по умолчанию 200)")
    p.add_argument("--region", default=DEFAULT_REGION)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--keep-days", type=int, default=None,
                   help="Перед проходом удалять записи старше N дней")
    p.add_argument("--dry-run", action="store_true",
                   help="Только показать, что будет обработано")
    args = p.parse_args()

    # ─── сбор itemId ───
    items: list[str] = []
    if args.items:
        items.extend(args.items)
    if args.auto:
        items.extend(tracked_items())
    if args.all_listing:
        from config import LISTING_CRAFT_FILE
        from storage.listing import load_listing, extract_item_id
        listing = load_listing(LISTING_CRAFT_FILE)
        items.extend(
            iid for iid in (extract_item_id(x) for x in listing) if iid
            )
    items = list(dict.fromkeys(items))   # дедуп, с сохранением порядка

    if not items:
        print("Нет itemId: --items / --auto / --all-listing")
        return 1

    # ─── dry-run: без OAuth, без записи ───
    if args.dry_run:
        _log(f"dry-run: itemId={len(items)}")
        for iid in items[:20]:
            _log(f"  · {iid}")
        if len(items) > 20:
            _log(f"  … ещё {len(items) - 20}")
        return 0

    # ─── trim один раз (для режима демона он ещё раз сработает внутри) ───
    if args.keep_days is not None and not args.every:
        td = ts = 0
        for iid in items:
            d, s = trim_old(iid, args.keep_days)
            td += d
            ts += s
        if td or ts:
            _log(f"trim(>{args.keep_days}д): -{td} deals, -{ts} snapshots")

    # ─── OAuth и запуск ───
    try:
        token = fetch_token()["access_token"]
    except ApiAuthError as e:
        print(f"[FATAL] Ошибка авторизации OAuth: {e}")
        return 2
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
            run_daemon(ps, items, args.every, args.limit, args.verbose,
                       keep_days=args.keep_days)
            return 0
        summary = collect_once(ps, items, args.limit, args.verbose)
        _log(f"✓ items={summary['items']} new_deals={summary['new_deals']} "
             f"snapshots={summary['snapshots']} errors={summary['errors']}")
        return 0
    except ApiAuthError as e:
        _log(f"✗ Ошибка авторизации API: {e}")
        return 2
    except ApiRateLimitError as e:
        _log(f"✗ API ограничил частоту запросов: {e}")
        return 3
    finally:
        ps.close()


if __name__ == "__main__":
    sys.exit(main())