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
from scripts.import_issue import parse_issue_body


class GitHubScriptTests(unittest.TestCase):
    def test_issue_form_is_parsed(self) -> None:
        body = """### 平台分类

微信公众号

### 账号或来源

机器之心

### 标题

AI 音乐工具发布

### 原文链接

https://mp.weixin.qq.com/s/example
"""
        fields = parse_issue_body(body)
        self.assertEqual(fields["平台分类"], "微信公众号")
        self.assertEqual(fields["标题"], "AI 音乐工具发布")

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
                )
            self.assertEqual(payload["total"], 1)
            self.assertGreater(payload["items"][0]["relevance_score"], 0)
            self.assertTrue(output_path.exists())


if __name__ == "__main__":
    unittest.main()
