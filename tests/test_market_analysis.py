from __future__ import annotations

from services import market_analysis as market


def test_market_analysis_returns_empty_payload_without_history(monkeypatch):
    monkeypatch.setattr(market, "load_item_data", lambda item_id, days: ([], []))

    result = market.analyze_market("item-1", 14)

    assert result == {
        "item_id": "item-1",
        "days": 14,
        "liquidity": None,
        "best_time": None,
        "warnings": ["Нет данных: сначала соберите историю через collect_history"],
    }


def test_market_analysis_preserves_liquidity_and_warning_contract(monkeypatch):
    deals = [
        {"amount": 10, "price": 1000, "unit": 100, "time": "2026-01-01T12:00:00+00:00"}
        for _ in range(30)
    ]
    snapshots = [{
        "summary": {
            "total_amount": 50,
            "n_lots": 5,
            "min_unit": 90,
            "depth_10pct_amount": 20,
        }
    } for _ in range(3)]
    monkeypatch.setattr(market, "load_item_data", lambda item_id, days: (deals, snapshots))

    result = market.analyze_market("item-1", 7)

    assert result["item_id"] == "item-1"
    assert result["days"] == 7
    assert result["liquidity"]["units"] == 300
    assert result["liquidity"]["rub"] == 30000
    assert result["liquidity"]["active_amount"] == 50
    assert result["liquidity"]["active_lots"] == 5
    assert result["liquidity"]["level_code"] == "MEDIUM"
    assert result["best_time"]["overall_median"] == 100
    assert result["warnings"] == ["дней со сделками: 1 — для трендов нужно ≥3 дня"]
