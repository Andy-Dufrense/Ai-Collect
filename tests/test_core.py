"""
核心逻辑自动化测试。

这些测试不会访问网络，因此即使 RSSHub 临时不可用也能稳定运行。
主要验证关键词双重过滤、忽略大小写、英文词边界、数据库去重和页面渲染。
"""

from __future__ import annotations

import os
import re
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
from news_filter import is_promotional_title, is_relevant_news
from config import RSS_SOURCES, SOGOU_WECHAT_QUERIES


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
        self.assertFalse(
            is_relevant_news(
                "OpenAI CEO 谈 AI 行业下一阶段",
                "公司人物与商业动态",
                category="国内科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "马斯克预测 AI 将在数年内超越人类",
                "纯人物观点",
                category="国内科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "AI 网络安全风险持续上升",
                "纯行业评论",
                category="国际科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "权志龙公司推出 AI 机器人女团并举办演唱会",
                "娱乐活动",
                category="国内科技",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "芯片公司 CEO 宣布裁员",
                "管理层和裁员计划",
                category="国际科技",
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
        for title in (
            "音频插件限时降价 50%",
            "Black Friday plugin deals",
            "Studio software subscriptions now available",
            "Guitar Center exclusives for Christmas shopping season",
        ):
            with self.subTest(title=title):
                self.assertTrue(is_promotional_title(title))
                self.assertFalse(
                    is_relevant_news(title, category="音乐科技")
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

    def test_foreign_music_media_rejects_artist_and_album_stories(self) -> None:
        """国外音乐媒体的艺人故事不能仅因 guitar/music 泛词进入资讯库。"""

        rejected_cases = (
            (
                "MusicRadar",
                (
                    "Levi Seacer Jr on giving one of Prince's funkiest hits "
                    "its X-rated chorus"
                ),
                "The story behind a classic song and its one-take guitar solo.",
            ),
            (
                "Guitar World",
                "Robert Pattinson once played guitar on a Death Grips track",
                "A celebrity interview about music and guitar collecting.",
            ),
            (
                "Music Business Worldwide",
                (
                    "Universal Music Canada strikes a label distribution "
                    "partnership with First Class Music Group"
                ),
                "The two companies will jointly sign and develop artists.",
            ),
            (
                "Synthtopia",
                (
                    "New Album Features Classics Played On A Famous "
                    "Analog Synthesizer"
                ),
                "An album story about a classic synthesizer collection.",
            ),
        )
        for source, title, summary in rejected_cases:
            with self.subTest(source=source, title=title):
                self.assertFalse(
                    is_relevant_news(
                        title,
                        summary,
                        category="音乐科技",
                        source=source,
                    )
                )

    def test_foreign_music_media_keeps_products_software_and_tutorials(
        self,
    ) -> None:
        """严格规则仍应保留插件、合成器、MIDI、音频接口和制作教程。"""

        accepted_cases = (
            (
                "Rekkerd",
                "HoRNet Plugins releases RhyGenerator MK2 MIDI sequencer",
                "A new Euclidean MIDI sequencer plugin for music producers.",
            ),
            (
                "Synthtopia",
                "Magerit Introduces Laniakea Pro Eight-Voice Synthesizer",
                "A new hardware synthesizer for Eurorack and standalone use.",
            ),
            (
                "Music Business Worldwide",
                "Suno launches Bridge, an app that drops AI stems into Ableton",
                "AI audio stems now sync into production projects.",
            ),
            (
                "Attack Magazine",
                "How To Deconstruct Any Beat In Ableton Live",
                "A production tutorial using Ableton Live.",
            ),
            (
                "MusicRadar",
                "Audient launches next-generation audio interfaces with onboard DSP",
                "New studio recording hardware with monitor correction.",
            ),
        )
        for source, title, summary in accepted_cases:
            with self.subTest(source=source, title=title):
                self.assertTrue(
                    is_relevant_news(
                        title,
                        summary,
                        category="音乐科技",
                        source=source,
                    )
                )

    def test_foreign_general_tech_requires_ai_music_or_development_value(
        self,
    ) -> None:
        """TechCrunch 只保留 AI 音乐、AI 硬件或真实 AI 开发资讯。"""

        self.assertTrue(
            is_relevant_news(
                "New open-source AI model generates audio stems",
                "Developers can run the audio generation model locally.",
                category="国际科技",
                source="TechCrunch",
            )
        )
        self.assertTrue(
            is_relevant_news(
                "Snapchat lets developers build AR lenses with AI assistants",
                "The new SDK exposes AI development tools.",
                category="国际科技",
                source="TechCrunch",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "Satya Nadella predicts AI agents will reshuffle the web",
                "An executive shares an industry prediction.",
                category="国际科技",
                source="TechCrunch",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "US tightens AI chip export controls",
                "New regulation restricts access to AI compute.",
                category="国际科技",
                source="TechCrunch",
            )
        )
        self.assertFalse(
            is_relevant_news(
                "Apple launches a new AI app to study health",
                "A consumer app for health research.",
                category="国际科技",
                source="TechCrunch",
            )
        )

    def test_strict_foreign_rule_does_not_change_other_sources(self) -> None:
        """国内来源或未登记来源继续使用原有较宽规则。"""

        self.assertTrue(
            is_relevant_news(
                "钢琴基础知识与和弦练习",
                "面向初学者的音乐学习文章。",
                category="音乐科技",
                source="国内音乐媒体",
            )
        )

    def test_music_only_and_ai_development_are_kept(self) -> None:
        self.assertFalse(
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

    def test_sogou_rejects_generic_ai_and_event_posts(self) -> None:
        for title, summary in (
            ("AI", "只有两个字母的泛内容"),
            ("AI 效果如何?", "泛泛讨论"),
            ("人工智能训练师报名入口开启", "证书培训广告"),
            ("顶尖音乐生全国音乐节招募", "活动通知"),
            ("钢琴家的一生", "人物故事"),
            ("一文看懂 AI 全产业链图谱", "行业综述"),
            ("人工智能标准研讨会即将举行", "活动通知"),
            ("温控仪 AI 算法介绍", "与音乐无关的工业产品"),
            ("AIGC 应用工程师报考流程", "考试报名广告"),
        ):
            with self.subTest(title=title):
                self.assertFalse(
                    is_relevant_news(
                        title,
                        summary,
                        category="搜狗微信",
                    )
                )

        self.assertTrue(
            is_relevant_news(
                "Suno 发布 AI MV 音乐视频功能",
                "用 AI 生成口型同步的音乐视频。",
                category="搜狗微信",
            )
        )
        self.assertTrue(
            is_relevant_news(
                "新款 MIDI 控制器与配套编曲软件更新",
                "面向音乐制作人的硬件和软件功能。",
                category="搜狗微信",
            )
        )
        self.assertTrue(
            is_relevant_news(
                "AI 编程工具新增音频插件开发接口",
                "面向音乐软件开发者。",
                category="搜狗微信",
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

    def test_suno_ai_music_video_is_supported(self) -> None:
        self.assertTrue(
            is_relevant_news(
                "SUNO 发布 AI MV 重磅上线",
                "用户可以生成完整的音乐视频。",
                category="搜狗微信",
            )
        )
        priced_feature_title = "SUNO AI MV 一秒只需3毛钱"
        self.assertFalse(is_promotional_title(priced_feature_title))
        self.assertTrue(
            is_relevant_news(
                priced_feature_title,
                "AI 音乐视频功能上线及使用成本说明。",
                category="搜狗微信",
            )
        )

    def test_sogou_queries_use_broad_discovery_terms(self) -> None:
        for keyword in (
            "AI",
            "人工智能",
            "AI音乐",
            "音乐",
            "吉他",
            "乐器",
            "音频",
            "编曲",
            "MIDI",
            "混音",
            "母带",
            "DAW",
            "音源",
        ):
            self.assertIn(keyword, SOGOU_WECHAT_QUERIES)
        self.assertNotIn("SUNO AI MV", SOGOU_WECHAT_QUERIES)
        self.assertNotIn("MIDI控制器", SOGOU_WECHAT_QUERIES)

    def test_hardware_specific_sources_are_configured(self) -> None:
        names = {source["source"] for source in RSS_SOURCES}
        for name in (
            "Matrixsynth",
            "Sound On Sound",
            "AudioTechnology",
            "Mixdown Magazine",
            "百度新闻：智能乐器",
            "百度新闻：音频硬件",
            "百度新闻：AI硬件",
            "百度新闻：MIDI控制器",
        ):
            self.assertIn(name, names)

    def test_software_specific_sources_are_configured(self) -> None:
        names = {source["source"] for source in RSS_SOURCES}
        for name in (
            "百度新闻：AI音乐软件",
            "百度新闻：音乐制作软件",
            "百度新闻：AI编曲",
            "百度新闻：混音软件",
            "百度新闻：DAW音乐制作",
            "百度新闻：音乐生成工具",
            "百度新闻：MIDI编曲",
            "百度新闻：音频插件",
        ):
            self.assertIn(name, names)


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

        piracy_count = save_news_items(
            [
                {
                    "title": "GitHub - 新发布：How to get Fl studio Producer 2026",
                    "link": "https://github.com/spam/flstudio",
                    "source": "GitHub 项目发现",
                    "publish_time": fetched_at.isoformat(timespec="seconds"),
                    "summary": "FL Studio producer download",
                    "category": "AI音频开发",
                }
            ],
            fetched_at,
        )
        self.assertEqual(piracy_count, 0)

    def test_promotional_item_is_rejected_before_database_insert(self) -> None:
        fetched_at = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)
        inserted = save_news_items(
            [
                {
                    "title": "AI 音乐插件黑五限时 5 折",
                    "link": "https://example.com/promotion",
                    "source": "测试源",
                    "publish_time": "2026-11-19T07:00:00+00:00",
                    "summary": "优惠活动",
                    "category": "音乐科技",
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

    def test_obviously_future_publish_time_is_rejected(self) -> None:
        now = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)
        inserted = save_news_items(
            [
                {
                    "title": "伪造未来的 GitHub MIDI 提交",
                    "link": "https://example.com/future-commit",
                    "source": "GitHub · spam/future",
                    "publish_time": "2071-10-10T19:46:01+00:00",
                    "summary": "fake future commit",
                    "category": "AI音频开发",
                }
            ],
            now,
        )
        self.assertEqual(inserted, 0)
        self.assertEqual(get_news_count(), 0)

    def test_initialization_purges_existing_out_of_scope_news(self) -> None:
        now = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)
        save_news_items(
            [
                {
                    "title": "AI",
                    "link": "https://example.com/generic-ai",
                    "source": "搜狗微信",
                    "publish_time": now.isoformat(timespec="seconds"),
                    "summary": "没有质量边界的泛内容",
                    "category": "搜狗微信",
                },
                {
                    "title": "AI 人物发表行业观点",
                    "link": "https://example.com/generic-ai-opinion",
                    "source": "国内科技",
                    "publish_time": now.isoformat(timespec="seconds"),
                    "summary": "只有观点，没有产品或技术信息",
                    "category": "国内科技",
                },
            ],
            now,
        )
        self.assertEqual(get_news_count(), 2)
        initialize_database()
        self.assertEqual(get_news_count(), 0)

    def test_initialization_purges_foreign_culture_stories(self) -> None:
        """升级后首次初始化应清理旧库中不符合严格国外规则的艺人内容。"""

        now = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)
        save_news_items(
            [
                {
                    "title": (
                        "Artist interview about the making of a hit album"
                    ),
                    "link": "https://example.com/foreign-culture",
                    "source": "MusicRadar",
                    "publish_time": now.isoformat(timespec="seconds"),
                    "summary": "A singer discusses a classic song.",
                    "category": "音乐科技",
                },
                {
                    "title": "New MIDI controller and audio interface released",
                    "link": "https://example.com/foreign-hardware",
                    "source": "MusicRadar",
                    "publish_time": now.isoformat(timespec="seconds"),
                    "summary": "USB-C music hardware for studio recording.",
                    "category": "音乐科技",
                },
            ],
            now,
        )
        self.assertEqual(get_news_count(), 2)

        initialize_database()

        remaining = get_all_news()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(
            remaining[0]["title"],
            "New MIDI controller and audio interface released",
        )

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
        self.assertIn("实际刷新时间存在偏差", page)

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

    def test_rank_numbers_are_continuous_after_hidden_translation(self) -> None:
        now = datetime.now(timezone.utc)
        save_news_items(
            [
                {
                    "title": "New AI music plugin released",
                    "link": "https://example.com/untranslated",
                    "source": "测试源",
                    "publish_time": now.isoformat(timespec="seconds"),
                    "summary": "Music software update",
                    "category": "音乐科技",
                    "title_zh": None,
                },
                {
                    "title": "AI 音乐中文资讯一",
                    "link": "https://example.com/chinese-one",
                    "source": "测试源",
                    "publish_time": (
                        now - timedelta(minutes=1)
                    ).isoformat(timespec="seconds"),
                    "summary": "音乐软件更新",
                    "category": "音乐科技",
                },
                {
                    "title": "AI 音乐中文资讯二",
                    "link": "https://example.com/chinese-two",
                    "source": "测试源",
                    "publish_time": (
                        now - timedelta(minutes=2)
                    ).isoformat(timespec="seconds"),
                    "summary": "音乐软件更新",
                    "category": "音乐科技",
                },
            ],
            now,
        )
        from app import app

        page = app.test_client().get("/").get_data(as_text=True)
        ranks = re.findall(
            r'class="rank-number[^"]*">\s*(\d+)\s*<',
            page,
        )
        self.assertEqual(ranks[:2], ["1", "2"])
        self.assertNotIn("New AI music plugin released", page)

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
        self.assertIn('id="sort-filter"', hardware_page)
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
