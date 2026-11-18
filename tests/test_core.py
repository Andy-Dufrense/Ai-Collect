"""
核心逻辑自动化测试。

这些测试不会访问网络，因此即使 RSSHub 临时不可用也能稳定运行。
主要验证关键词双重过滤、忽略大小写、英文词边界、数据库去重和页面渲染。
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
    purge_news_outside_retention,
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

    def test_technical_content_is_accepted_but_noise_is_rejected(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "AI 芯片销量创新高",
                "半导体行业资讯",
                category="国内科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "新款手机正式上架",
                "普通硬件产品介绍",
                category="国内科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "本周热门音乐榜单",
                "多位歌手发布新歌",
                category="音乐科技",
            )
        )

    def test_ai_person_and_price_filter(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "OpenAI CEO 谈 AI 行业下一阶段",
                "公司人物与商业动态",
                category="国内科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "新款 AI 手机首发价 5999 元",
                "产品正式上市",
                category="国内科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "Music gear bundle 50% off",
                "Limited sale",
                category="音乐科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "Save up to 81% on UVI audio plugins",
                "Limited promotion",
                category="音乐科技",
            )
        )

    def test_does_not_treat_letters_inside_english_word_as_ai(self) -> None:
        self.assertFalse(is_relevant_news("Daily news about cooking", "普通生活晨报"))

    def test_ai_hardware_is_accepted_as_technology(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "AI 智能主机发布",
                "设备支持音频播放、蓝牙连接和会议纪要功能。",
            )
        )

    def test_direction_hardware_is_accepted_but_generic_hardware_stays_out(
        self,
    ) -> None:
        self.assertTrue(
            is_relevant_news(
                "国产 NPU 与端侧 AI 推理盒子发布",
                "面向开发者的神经网络处理器硬件。",
                category="国内科技",
            )
        )
        self.assertTrue(
            is_relevant_news(
                "New MIDI controller and audio interface launched",
                "USB-C music hardware for studio recording.",
                category="国际科技",
            )
        )
        self.assertTrue(
            is_relevant_news(
                "智能乐器硬件新增触控演奏功能",
                "面向电子乐器开发者。",
                category="国内科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "普通机械键盘硬件新品上架",
                "介绍按键轴体和外观颜色。",
                category="国内科技",
            )
        )
        self.assertTrue(
            is_relevant_news(
                "英伟达发布新一代 AI 服务器，搭载自研 GPU",
                "面向智算中心和端侧推理的硬件产品。",
                category="国内科技",
            )
        )
        self.assertTrue(
            is_relevant_news(
                "国产智能终端搭载新一代 NPU 芯片",
                "芯片面向端侧人工智能推理。",
                category="国内科技",
            )
        )

    def test_music_software_is_relevant(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "AI 音乐编曲插件更新",
                "新增生成式分轨和音色编辑功能。",
            )
        )

    def test_ai_music_software_from_vertical_media_is_relevant(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "Logic Pro 13 adds intelligent assistant workflow",
                "A DAW update with new editing features.",
                category="音乐科技",
            )
        )
        self.assertTrue(
            is_relevant_news(
                "Suno launches Bridge for Ableton Live",
                "AI stems now sync into production projects.",
                category="音乐科技",
            )
        )

    def test_executive_and_artist_gossip_is_rejected(self) -> None:
        self.assertFalse(
            is_relevant_news(
                "唱片公司 CEO 卸任",
                "音乐行业高管变动。",
                category="音乐科技",
            )
        )

    def test_music_only_and_ai_development_are_kept(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "爱音乐，更爱古筝",
                "音乐学习与乐器介绍",
                category="搜狗微信",
            )
        )
        self.assertTrue(
            is_relevant_news(
                "开发者发布 AI 编程工具",
                "该软件提供模型接口和开源 SDK",
                category="国内科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "普通手机产品上架",
                "介绍外观颜色和电池容量",
                category="国内科技",
            )
        )

    def test_ai_music_cross_topic_has_higher_ranking_than_ai_only(self) -> None:
        from ranking import _relevance_score

        ai_only = {
            "title": "AI 编程工具新进展",
            "summary": "人工智能软件开发",
        }
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

    def test_hardware_and_software_flags_are_saved(self) -> None:
        fetched_at = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
        save_news_items(
            [
                {
                    "title": "新型 MIDI 控制器硬件发布",
                    "link": "https://example.com/content-hardware",
                    "source": "测试源",
                    "publish_time": "2026-11-17T07:00:00+00:00",
                    "summary": "实体演奏设备。",
                    "category": "音乐科技",
                },
                {
                    "title": "AI 音乐制作插件更新",
                    "link": "https://example.com/content-software",
                    "source": "测试源",
                    "publish_time": "2026-11-17T06:00:00+00:00",
                    "summary": "新增编曲功能。",
                    "category": "音乐科技",
                },
            ],
            fetched_at,
        )
        by_title = {item["title"]: item for item in get_all_news()}
        self.assertTrue(by_title["新型 MIDI 控制器硬件发布"]["is_hardware"])
        self.assertFalse(by_title["新型 MIDI 控制器硬件发布"]["is_software"])
        self.assertFalse(by_title["AI 音乐制作插件更新"]["is_hardware"])
        self.assertTrue(by_title["AI 音乐制作插件更新"]["is_software"])

    def test_github_spam_is_rejected_before_database_insert(self) -> None:
        fetched_at = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
        inserted = save_news_items(
            [
                {
                    "title": (
                        "GitHub - 新更新：美国海外住宅代理做直播与账号多开"
                        " music update"
                    ),
                    "link": "https://github.com/spam/proxy/commit/1",
                    "source": "GitHub · spam/proxy",
                    "publish_time": "2026-11-17T07:00:00+00:00",
                    "summary": "批量引流广告",
                    "category": "AI音频开发",
                }
            ],
            fetched_at,
        )
        self.assertEqual(inserted, 0)
        self.assertEqual(get_news_count(), 0)

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

    def test_none_translated_title_is_saved_as_null(self) -> None:
        fetched_at = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
        save_news_items(
            [
                {
                    "title": "AI music news",
                    "title_zh": None,
                    "link": "https://example.com/no-translation",
                    "source": "测试源",
                    "publish_time": "2026-11-17T07:00:00+00:00",
                    "summary": "测试",
                }
            ],
            fetched_at,
        )
        self.assertIsNone(get_all_news()[0]["title_zh"])

    def test_retention_removes_old_and_undated_news(self) -> None:
        now = datetime.now(timezone.utc)
        save_news_items(
            [
                {
                    "title": "2023 年旧报告",
                    "link": "https://example.com/old-report",
                    "source": "测试源",
                    "publish_time": "2023-05-21T10:00:00+00:00",
                    "summary": "音乐技术",
                },
                {
                    "title": "没有时间的内容",
                    "link": "https://example.com/no-date-retention",
                    "source": "测试源",
                    "publish_time": None,
                    "summary": "音乐技术",
                },
                {
                    "title": "最近的音乐技术",
                    "link": "https://example.com/recent-retention",
                    "source": "测试源",
                    "publish_time": now.isoformat(timespec="seconds"),
                    "summary": "音乐技术",
                },
            ],
            now,
        )
        removed = purge_news_outside_retention(60)
        self.assertEqual(removed, 2)
        self.assertEqual(get_news_count(), 1)
        self.assertEqual(get_all_news()[0]["title"], "最近的音乐技术")


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
        now = datetime.now(timezone.utc)
        save_news_items(
            [
                {
                    "title": "AI 吉他音色分析",
                    "link": "https://example.com/guitar-ai",
                    "source": "测试源",
                    "publish_time": now.isoformat(timespec="seconds"),
                    "summary": "机器学习帮助分析吉他音色。",
                }
            ],
            now,
        )

        # 在测试方法内部导入，确保其他测试修改环境变量时不受模块缓存影响。
        from app import app

        response = app.test_client().get("/")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("AI 吉他音色分析", page)
        self.assertIn("测试源", page)
        self.assertIn("总收录", page)
        self.assertIn('id="filter-form"', page)

    def test_index_shows_auto_sync_when_heartbeat_is_fresh(self) -> None:
        set_worker_heartbeat(datetime.now(timezone.utc))
        from app import app

        response = app.test_client().get("/")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("预计下次刷新时间", page)
        self.assertIn("实际刷新时间可能稍晚", page)

    def test_homepage_marks_only_first_twenty_rows_visible(self) -> None:
        now = datetime.now(timezone.utc)
        save_news_items(
            [
                {
                    "title": f"AI 音乐技术资讯 {index}",
                    "link": f"https://example.com/page-{index}",
                    "source": "测试源",
                    "publish_time": (
                        now - timedelta(minutes=index)
                    ).isoformat(timespec="seconds"),
                    "summary": "音乐软件功能更新",
                    "category": "音乐科技",
                }
                for index in range(25)
            ],
            now,
        )
        from app import app

        page = app.test_client().get("/?kind=software").get_data(as_text=True)
        self.assertEqual(page.count('class="feed-row"'), 20)
        self.assertIn("下一页", page)
        self.assertIn("kind=software", page)

    def test_content_kind_filter_only_returns_selected_type(self) -> None:
        now = datetime.now(timezone.utc)
        save_news_items(
            [
                {
                    "title": "新型合成器硬件发布",
                    "link": "https://example.com/hardware-only",
                    "source": "测试源",
                    "publish_time": now.isoformat(timespec="seconds"),
                    "summary": "独立硬件合成器。",
                    "category": "音乐科技",
                },
                {
                    "title": "AI 音乐编曲插件更新",
                    "link": "https://example.com/software-only",
                    "source": "测试源",
                    "publish_time": now.isoformat(timespec="seconds"),
                    "summary": "软件功能更新。",
                    "category": "音乐科技",
                },
            ],
            now,
        )
        from app import app

        client = app.test_client()
        hardware_page = client.get("/?days=3&kind=hardware").get_data(as_text=True)
        software_page = client.get("/?days=3&kind=software").get_data(as_text=True)

        self.assertIn('<select id="content-kind-filter"', hardware_page)
        self.assertIn('value="hardware"', hardware_page)
        self.assertIn("新型合成器硬件发布", hardware_page)
        self.assertNotIn("AI 音乐编曲插件更新", hardware_page)
        self.assertIn("AI 音乐编曲插件更新", software_page)
        self.assertNotIn("新型合成器硬件发布", software_page)

    def test_manual_and_sync_routes_are_removed(self) -> None:
        from app import app

        client = app.test_client()
        self.assertEqual(client.get("/add_manual").status_code, 404)
        self.assertEqual(client.post("/fetch").status_code, 404)


if __name__ == "__main__":
    unittest.main()
