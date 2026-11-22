import json
import os

os.environ.setdefault("STALCRAFT_CLIENT_SECRET", "test-only")

from scripts.publish_deals import build_top_items_index


def test_top_items_index_uses_one_latest_hour_and_sorts_by_deals():
    contents = {
        "item-a": "\n".join([
            json.dumps({
                "item": "item-a", "hour": "2026-11-22T10:00:00+03:00",
                "deals": 12, "turnover": 1200, "median_unit": 100,
            }),
            json.dumps({
                "item": "item-a", "hour": "2026-11-22T11:00:00+03:00",
                "deals": 5, "turnover": 500, "median_unit": 100,
            }),
        ]),
        "item-b": json.dumps({
            "item": "item-b", "hour": "2026-11-22T11:00:00+03:00",
            "deals": 20, "turnover": 2000, "median_unit": 100,
        }),
        "item-c": json.dumps({
            "item": "item-c", "hour": "2026-11-22T10:00:00+03:00",
            "deals": 99, "turnover": 9900, "median_unit": 100,
        }),
    }

    result = json.loads(build_top_items_index(contents))

    assert result["hour"] == "2026-11-22T11:00:00+03:00"
    assert [row["item"] for row in result["items"]] == ["item-b", "item-a"]
    assert result["items"][0] == {
        "item": "item-b", "deals": 20, "turnover": 2000.0, "median_unit": 100.0,
    }


def test_top_items_index_returns_empty_when_there_are_no_valid_rows():
    result = json.loads(build_top_items_index({"item-a": "not-json"}))
    assert result == {"hour": None, "items": []}
