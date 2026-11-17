"""历史归档时间解析测试。"""

from __future__ import annotations

import unittest

from backfill import _convert_article


class BackfillTests(unittest.TestCase):
    def test_date_gmt_is_preserved_as_utc(self) -> None:
        item = _convert_article(
            {
                "date_gmt": "2026-10-05T12:34:56",
                "link": "https://example.com/plugin",
                "title": {"rendered": "AI music plugin update"},
                "excerpt": {"rendered": "<p>New software features.</p>"},
            },
            source="MusicTech",
            category="音乐科技",
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["publish_time"], "2026-10-05T12:34:56+00:00")
        self.assertEqual(item["summary"], "New software features.")

    def test_missing_date_is_not_saved(self) -> None:
        item = _convert_article(
            {
                "link": "https://example.com/no-date",
                "title": {"rendered": "AI music software"},
                "excerpt": {"rendered": "No publication date"},
            },
            source="MusicTech",
            category="音乐科技",
        )
        self.assertIsNone(item)


if __name__ == "__main__":
    unittest.main()
