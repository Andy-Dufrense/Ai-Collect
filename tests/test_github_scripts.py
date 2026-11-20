"""GitHub 静态数据脚本测试，不访问网络。"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from database import get_news_count, initialize_database, save_news_items
from scripts.github_update import export_static_site, import_existing_news


class GitHubScriptTests(unittest.TestCase):
    def test_static_page_uses_numbered_pagination(self) -> None:
        project_dir = Path(__file__).resolve().parent.parent
        page = (project_dir / "public" / "index.html").read_text(
            encoding="utf-8"
        )
        script = (project_dir / "public" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="page-numbers"', page)
        self.assertNotIn('id="page-info"', page)
        self.assertIn("Math.max(1, currentPage - 2)", script)
        self.assertIn("Math.min(totalPages, currentPage + 2)", script)
        self.assertIn('createCell("page-ellipsis", "…")', script)
        self.assertIn('button.setAttribute("aria-current", "page")', script)
        self.assertIn("midnight.getTime() + 11 * 3600000", script)
        self.assertIn("midnight.getTime() + 23 * 3600000", script)

    def test_existing_json_can_restore_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "github-test.db"
            json_path = Path(temp_dir) / "news.json"
            json_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "AI 音乐工具",
                                "link": "https://example.com/one",
                                "source": "测试源",
                                "publish_time": "2026-11-17T08:00:00+00:00",
                                "summary": "测试",
                                "category": "音乐科技",
                                "dedupe_key": "example-one",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}):
                initialize_database()
                imported = import_existing_news(json_path)
                self.assertEqual(imported, 1)
                self.assertEqual(get_news_count(), 1)

    def test_export_contains_rank_scores(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "export-test.db"
            output_path = Path(temp_dir) / "public" / "data" / "news.json"
            with patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}):
                initialize_database()
                save_news_items(
                    [
                        {
                            "title": "AI 吉他工具发布",
                            "link": "https://example.com/export",
                            "source": "MusicRadar",
                            "publish_time": datetime.now(timezone.utc).isoformat(),
                            "summary": "AI 音乐制作",
                            "category": "音乐科技",
                            "dedupe_key": "example-export",
                        }
                    ],
                    datetime.now(timezone.utc),
                )
                payload = export_static_site(
                    output_path,
                    copy_style=False,
                    translate_titles=False,
                )
            self.assertEqual(payload["total"], 1)
            self.assertGreater(payload["items"][0]["relevance_score"], 0)
            self.assertIn("is_hardware", payload["items"][0])
            self.assertIn("is_software", payload["items"][0])
            self.assertTrue(output_path.exists())


if __name__ == "__main__":
    unittest.main()
