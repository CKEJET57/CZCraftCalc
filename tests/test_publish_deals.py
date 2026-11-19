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
    def test_aggregate_is_one_jsonl_row_per_hour(self):
        hour = datetime(2026, 11, 19, 14, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        content = publisher.aggregate_item("401j", {
            hour: [
                {"amount": 2, "price": 100, "unit": 50},
                {"amount": 3, "price": 180, "unit": 60},
            ]
        }, "2026-11-19T11:00:00+00:00")
        row = json.loads(content)
        self.assertEqual(row["item"], "401j")
        self.assertEqual(row["deals"], 2)
        self.assertEqual(row["amount"], 5)
        self.assertEqual(row["turnover"], 280)
        self.assertEqual(row["avg_unit"], 56)
        self.assertEqual(row["median_unit"], 55)
        self.assertIn('"item":"401j"', content)
        self.assertTrue(content.endswith("\\n"))

    def test_grouping_does_not_modify_source_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "deals"
            source_dir.mkdir()
            source = source_dir / "401j.jsonl"
            original = json.dumps({
                "item": "401j", "price": 100, "amount": 2, "unit": 50,
                "time": "2026-11-19T10:15:00+00:00",
            }) + "\\n"
            source.write_text(original, encoding="utf-8")
            now = datetime(2026, 11, 19, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))
            with patch.object(publisher, "HISTORY_DEALS_DIR", source_dir):
                grouped = publisher.read_source_deals(now, ZoneInfo("Europe/Moscow"))
            self.assertEqual(len(grouped["401j"]), 1)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_current_hour_is_not_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "deals"
            source_dir.mkdir()
            source = source_dir / "401j.jsonl"
            source.write_text(json.dumps({
                "item": "401j", "price": 100, "amount": 2, "unit": 50,
                "time": "2026-11-19T12:15:00+00:00",
            }) + "\\n", encoding="utf-8")
            now = datetime(2026, 11, 19, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))
            with patch.object(publisher, "HISTORY_DEALS_DIR", source_dir):
                grouped = publisher.read_source_deals(now, ZoneInfo("Europe/Moscow"))
            self.assertEqual(grouped, {})

    def test_merge_updates_hour_without_duplicates(self):
        old = json.dumps({"hour": "2026-11-19T10:00:00+03:00", "deals": 2})
        fresh = json.dumps({"hour": "2026-11-19T10:00:00+03:00", "deals": 3})
        merged = publisher.merge_hourly(old + "\\n", fresh + "\\n")
        rows = [json.loads(line) for line in merged.splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["deals"], 3)


if __name__ == "__main__":
    unittest.main()
