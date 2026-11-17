"""
核心逻辑自动化测试。

这些测试不会访问网络，因此即使 RSSHub 临时不可用也能稳定运行。
主要验证关键词双重过滤、忽略大小写、英文词边界、数据库去重和页面渲染。
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from database import (
    clear_worker_heartbeat,
    get_all_news,
    get_latest_fetch_run,
    get_last_fetch_time,
    get_news_count,
    get_worker_heartbeat,
    initialize_database,
    record_fetch_run,
    set_worker_heartbeat,
    save_news_items,
)
from news_filter import is_relevant_news


class NewsFilterTests(unittest.TestCase):
    """验证需求中的关键词过滤规则。"""

    def test_keeps_news_with_ai_and_music_keywords(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "某公司发布 AI 作曲工具",
                "新工具可以根据一句提示生成完整音乐。",
            )
        )

    def test_is_case_insensitive(self) -> None:
        self.assertTrue(is_relevant_news("AIGC TOOL FOR MUSIC", "音乐生成"))

    def test_english_ai_music_news_is_supported(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "New AI music production tool launched",
                "A machine-learning assistant for guitar players.",
            )
        )

    def test_ai_and_music_can_appear_in_different_fields(self) -> None:
        self.assertTrue(is_relevant_news("大模型新进展", "可用于实时编曲"))

    def test_accepts_news_with_only_one_category(self) -> None:
        self.assertTrue(is_relevant_news("AI 芯片销量创新高", "半导体行业资讯"))
        self.assertTrue(is_relevant_news("本周热门音乐榜单", "多位歌手发布新歌"))

    def test_does_not_treat_letters_inside_english_word_as_ai(self) -> None:
        self.assertFalse(is_relevant_news("Daily news about technology", "普通行业晨报"))

    def test_ai_audio_feature_is_now_supported(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "AI 智能主机发布",
                "设备支持音频播放、蓝牙连接和会议纪要功能。",
            )
        )

    def test_ai_music_cross_topic_has_higher_ranking_than_ai_only(self) -> None:
        from ranking import _relevance_score

        ai_only = {"title": "AI 芯片新进展", "summary": "人工智能产业消息"}
        cross_topic = {
            "title": "AI 吉他工具发布",
            "summary": "人工智能用于音乐和乐器创作",
        }
        self.assertGreater(
            _relevance_score(cross_topic),
            _relevance_score(ai_only),
        )

    def test_ai_audio_creation_is_still_supported(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "AI 音频创作工具更新",
                "支持生成旋律、混音和导出音色。",
            )
        )


class DatabaseTests(unittest.TestCase):
    """使用临时目录测试数据库，确保不会碰正式 news.db。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test_news.db"
        self.environment = patch.dict(
            os.environ,
            {"NEWS_DB_PATH": str(self.database_path)},
        )
        self.environment.start()
        initialize_database()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_duplicate_link_is_ignored(self) -> None:
        fetched_at = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)
        item = {
            "title": "AI 音乐工具发布",
            "link": "https://example.com/news/1",
            "source": "测试源",
            "publish_time": "2026-11-16T07:30:00+00:00",
            "summary": "测试简介",
        }

        first_count = save_news_items([item], fetched_at)
        second_count = save_news_items([item], fetched_at)

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)
        self.assertEqual(get_news_count(), 1)

    def test_news_is_sorted_newest_first(self) -> None:
        fetched_at = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)
        base = {
            "source": "测试源",
            "summary": "测试简介",
        }
        save_news_items(
            [
                {
                    **base,
                    "title": "较旧资讯",
                    "link": "https://example.com/old",
                    "publish_time": "2026-11-15T08:00:00+00:00",
                },
                {
                    **base,
                    "title": "最新资讯",
                    "link": "https://example.com/new",
                    "publish_time": "2026-11-16T07:00:00+00:00",
                },
            ],
            fetched_at,
        )

        news_items = get_all_news()
        self.assertEqual(news_items[0]["title"], "最新资讯")
        self.assertEqual(news_items[1]["title"], "较旧资讯")
        self.assertIsNotNone(get_last_fetch_time())

    def test_fetch_run_status_is_persisted(self) -> None:
        fetched_at = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)
        record_fetch_run(
            fetched_at=fetched_at,
            source_count=2,
            successful_sources=1,
            total_entries=20,
            matched_entries=3,
            new_count=2,
            errors=["示例源请求失败"],
        )

        latest_run = get_latest_fetch_run()
        self.assertIsNotNone(latest_run)
        assert latest_run is not None
        self.assertEqual(latest_run["failed_sources"], 1)
        self.assertEqual(latest_run["new_count"], 2)
        self.assertEqual(latest_run["errors"], ["示例源请求失败"])

    def test_worker_heartbeat_can_be_saved_and_cleared(self) -> None:
        heartbeat_at = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)
        set_worker_heartbeat(heartbeat_at)
        self.assertEqual(
            get_worker_heartbeat(),
            "2026-11-16T08:00:00+00:00",
        )

        clear_worker_heartbeat()
        self.assertIsNone(get_worker_heartbeat())

    def test_stable_dedupe_key_updates_link_without_new_row(self) -> None:
        fetched_at = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
        base_item = {
            "title": "AI 音乐工具发布",
            "source": "测试公众号",
            "publish_time": "2026-11-17T07:00:00+00:00",
            "summary": "测试简介",
            "category": "搜狗微信",
            "dedupe_key": "sogou:stable-key",
        }
        first_count = save_news_items(
            [{**base_item, "link": "https://weixin.sogou.com/link?token=old"}],
            fetched_at,
        )
        second_count = save_news_items(
            [{**base_item, "link": "https://weixin.sogou.com/link?token=new"}],
            fetched_at,
        )

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)
        self.assertEqual(get_news_count(), 1)
        self.assertIn("token=new", get_all_news()[0]["link"])

    def test_none_publish_time_is_saved_as_null(self) -> None:
        fetched_at = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
        save_news_items(
            [
                {
                    "title": "AI 音乐资讯",
                    "link": "https://example.com/no-time",
                    "source": "测试源",
                    "publish_time": None,
                    "summary": "无发布时间",
                }
            ],
            fetched_at,
        )
        self.assertIsNone(get_all_news()[0]["publish_time"])


class FlaskPageTests(unittest.TestCase):
    """验证首页能读取数据库并渲染新闻卡片。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {"NEWS_DB_PATH": str(Path(self.temp_dir.name) / "page_test.db")},
        )
        self.environment.start()
        initialize_database()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_index_renders_saved_news(self) -> None:
        save_news_items(
            [
                {
                    "title": "AI 吉他音色分析",
                    "link": "https://example.com/guitar-ai",
                    "source": "测试源",
                    "publish_time": "2026-11-16T07:00:00+00:00",
                    "summary": "机器学习帮助分析吉他音色。",
                }
            ],
            datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc),
        )

        # 在测试方法内部导入，确保其他测试修改环境变量时不受模块缓存影响。
        from app import app

        response = app.test_client().get("/")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("AI 吉他音色分析", page)
        self.assertIn("测试源", page)
        self.assertIn("总收录", page)

    def test_index_shows_auto_sync_when_heartbeat_is_fresh(self) -> None:
        set_worker_heartbeat(datetime.now(timezone.utc))
        from app import app

        response = app.test_client().get("/")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("自动同步中", page)

    def test_page_redacts_proxy_credentials_in_error_summary(self) -> None:
        record_fetch_run(
            fetched_at=datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc),
            source_count=1,
            successful_sources=0,
            total_entries=0,
            matched_entries=0,
            new_count=0,
            errors=["ProxyError http://demo:secret@127.0.0.1:7890"],
        )
        from app import app

        response = app.test_client().get("/")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("127.0.0.1:7890", page)
        self.assertNotIn("demo:secret", page)

    def test_manual_entry_is_saved_with_category(self) -> None:
        from app import app

        client = app.test_client()
        response = client.post(
            "/add_manual",
            data={
                "category": "微信公众号",
                "source": "测试公众号",
                "title": "AI 吉他创作新工具",
                "link": "https://mp.weixin.qq.com/s/manual-test",
                "summary": "用于测试手动录入。",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_news_count(), 1)
        self.assertEqual(get_all_news()[0]["category"], "微信公众号")

    def test_manual_entry_rejects_invalid_link(self) -> None:
        from app import app

        response = app.test_client().post(
            "/add_manual",
            data={
                "title": "无效链接",
                "link": "javascript:alert(1)",
            },
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("完整的 http", page)
        self.assertEqual(get_news_count(), 0)

    def test_admin_routes_can_be_protected_by_basic_auth(self) -> None:
        import app as app_module

        client = app_module.app.test_client()
        with patch.object(app_module, "ADMIN_TOKEN", "test-secret"):
            unauthorized = client.get("/add_manual")
            self.assertEqual(unauthorized.status_code, 401)

            authorized = client.get(
                "/add_manual",
                auth=("admin", "test-secret"),
            )
            self.assertEqual(authorized.status_code, 200)


if __name__ == "__main__":
    unittest.main()
