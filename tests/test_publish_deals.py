import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ.setdefault("STALCRAFT_CLIENT_SECRET", "test-only")

from scripts import publish_deals as publisher


class PublishDealsTests(unittest.TestCase):
    def test_hourly_aggregate_uses_weighted_average_and_median(self):
        hour = datetime(2026, 11, 19, 14, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        content = publisher.aggregate_hour(hour, {
            "401j": [
                {"amount": 2, "price": 100, "unit": 50},
                {"amount": 3, "price": 180, "unit": 60},
            ]
        })
        row = json.loads(content)
        self.assertEqual(row["deals"], 2)
        self.assertEqual(row["amount"], 5)
        self.assertEqual(row["turnover"], 280)
        self.assertEqual(row["avg_unit"], 56)
        self.assertEqual(row["median_unit"], 55)

    def test_grouping_does_not_modify_source_deals(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "deals"
            source_dir.mkdir()
            source = source_dir / "401j.jsonl"
            original = json.dumps({
                "item": "401j", "price": 100, "amount": 2, "unit": 50,
                "time": "2026-11-19T10:15:00+00:00",
            }) + "\n"
            source.write_text(original, encoding="utf-8")
            now = datetime(2026, 11, 19, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))
            with patch.object(publisher, "HISTORY_DEALS_DIR", source_dir):
                grouped = publisher.load_and_group(now, ZoneInfo("Europe/Moscow"))
            self.assertEqual(len(grouped), 1)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_current_hour_is_not_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "deals"
            source_dir.mkdir()
            source = source_dir / "401j.jsonl"
            source.write_text(json.dumps({
                "item": "401j", "price": 100, "amount": 2, "unit": 50,
                "time": "2026-11-19T12:15:00+00:00",
            }) + "\n", encoding="utf-8")
            now = datetime(2026, 11, 19, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))
            with patch.object(publisher, "HISTORY_DEALS_DIR", source_dir):
                grouped = publisher.load_and_group(now, ZoneInfo("Europe/Moscow"))
            self.assertEqual(grouped, {})


if __name__ == "__main__":
    unittest.main()
