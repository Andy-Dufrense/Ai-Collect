"""GitHub 静态数据脚本测试，不访问网络。"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from database import get_news_count, initialize_database, save_news_items
from scripts import github_update
from scripts.github_update import (
    ExportValidationError,
    export_static_site,
    import_existing_news,
    validate_static_payload,
)


class GitHubScriptTests(unittest.TestCase):
    @staticmethod
    def _payload(total: int) -> dict:
        return {
            "generated_at": "2026-11-20T00:00:00+00:00",
            "total": total,
            "items": [
                {
                    "title": f"AI 音乐工具 {index}",
                    "link": f"https://example.com/{index}",
                    "source": "测试源",
                    "publish_time": "2026-11-19T00:00:00+00:00",
                }
                for index in range(total)
            ],
        }

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
        self.assertIn("function safeExternalUrl(value)", script)
        self.assertIn("function cleanDisplayTitle(value)", script)
        self.assertIn("function chooseDisplayTitle(item)", script)
        self.assertIn("isSuspiciousTranslatedTitle(translated)", script)
        self.assertIn("function itemSearchText(item)", script)
        self.assertIn("item.source ||", script)
        self.assertIn("item.display_source ||", script)
        self.assertIn("terms.some((term) => matchesSearchTerm(text, term))", script)

    def test_workflow_has_tests_timeout_and_push_retry(self) -> None:
        project_dir = Path(__file__).resolve().parent.parent
        workflow = (
            project_dir / ".github" / "workflows" / "update-pages.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("timeout-minutes: 90", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn('python-version: "3.14"', workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("git rebase origin/main", workflow)

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

    def test_payload_validation_rejects_unsafe_links_and_large_drops(
        self,
    ) -> None:
        unsafe_payload = self._payload(1)
        unsafe_payload["items"][0]["link"] = "javascript:alert(1)"
        with self.assertRaises(ExportValidationError):
            validate_static_payload(unsafe_payload)

        with self.assertRaises(ExportValidationError):
            validate_static_payload(self._payload(10), previous_total=20)

        with self.assertRaises(ExportValidationError):
            validate_static_payload(self._payload(0))

    def test_large_drop_does_not_overwrite_existing_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "drop-guard.db"
            output_path = Path(temp_dir) / "public" / "data" / "news.json"
            output_path.parent.mkdir(parents=True)
            previous_payload = self._payload(100)
            previous_text = json.dumps(previous_payload, ensure_ascii=False)
            output_path.write_text(previous_text, encoding="utf-8")
            with patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}):
                initialize_database()
                save_news_items(
                    [
                        {
                            "title": "AI 吉他工具发布",
                            "link": "https://example.com/only-one",
                            "source": "MusicRadar",
                            "publish_time": datetime.now(timezone.utc).isoformat(),
                            "summary": "AI 音乐制作",
                            "category": "音乐科技",
                            "dedupe_key": "only-one",
                        }
                    ],
                    datetime.now(timezone.utc),
                )
                with self.assertRaises(ExportValidationError):
                    export_static_site(
                        output_path,
                        copy_style=False,
                        translate_titles=False,
                    )

            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                previous_text,
            )

    def test_fetch_and_backfill_failures_still_export_old_data(self) -> None:
        fake_result = SimpleNamespace(
            successful_sources=0,
            source_count=0,
            matched_entries=0,
            new_count=0,
        )
        with (
            patch.dict(os.environ, {"BACKFILL_DAYS": "60"}),
            patch.object(github_update, "import_existing_news", return_value=0),
            patch.object(
                github_update,
                "backfill_history",
                side_effect=RuntimeError("backfill failed"),
            ),
            patch.object(
                github_update,
                "fetch_and_save_news",
                side_effect=RuntimeError("fetch failed"),
            ),
            patch.object(
                github_update,
                "export_static_site",
                return_value={"total": 1},
            ) as export_mock,
        ):
            exit_code = github_update.main()

        self.assertEqual(exit_code, 0)
        export_mock.assert_called_once()

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

    def test_translation_failure_does_not_block_export(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "translation-failure.db"
            output_path = Path(temp_dir) / "public" / "data" / "news.json"
            with (
                patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}),
                patch(
                    "scripts.github_update.translate_items",
                    side_effect=RuntimeError("translation failed"),
                ),
            ):
                initialize_database()
                save_news_items(
                    [
                        {
                            "title": "AI 吉他工具发布",
                            "link": "https://example.com/translation-failure",
                            "source": "MusicRadar",
                            "publish_time": datetime.now(timezone.utc).isoformat(),
                            "summary": "AI 音乐制作",
                            "category": "音乐科技",
                            "dedupe_key": "translation-failure",
                        }
                    ],
                    datetime.now(timezone.utc),
                )
                payload = export_static_site(
                    output_path,
                    copy_style=False,
                )

        self.assertEqual(payload["total"], 1)


if __name__ == "__main__":
    unittest.main()
