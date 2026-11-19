"""筛选和排行榜计算测试。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ranking import filter_and_rank_news


def make_item(
    title: str,
    *,
    publish_time: str | None,
    summary: str = "",
    source: str = "MusicTech",
    category: str = "音乐科技",
    is_hardware: bool = False,
    is_software: bool = False,
) -> dict[str, str | None]:
    return {
        "title": title,
        "summary": summary,
        "publish_time": publish_time,
        "source": source,
        "category": category,
        "is_hardware": is_hardware,
        "is_software": is_software,
        "link": f"https://example.com/{abs(hash(title))}",
    }


class RankingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)

    def test_default_three_day_window_excludes_old_and_unknown(self) -> None:
        items = [
            make_item(
                "AI 音乐制作工具发布",
                publish_time="2026-11-17T08:00:00+00:00",
            ),
            make_item(
                "旧 AI 吉他资讯",
                publish_time="2026-11-01T08:00:00+00:00",
            ),
            make_item("AI 乐理资讯", publish_time=None),
        ]
        ranked = filter_and_rank_news(items, days=3, now=self.now)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["title"], "AI 音乐制作工具发布")
        self.assertGreater(ranked[0]["rank_score"], 0)

    def test_all_time_can_include_unknown_publish_time(self) -> None:
        items = [make_item("AI 乐理资讯", publish_time=None)]
        ranked = filter_and_rank_news(items, days=0, now=self.now)
        self.assertEqual(len(ranked), 1)

    def test_keyword_search_matches_title_or_summary(self) -> None:
        items = [
            make_item(
                "AI 音乐工具发布",
                publish_time="2026-11-17T08:00:00+00:00",
                summary="支持钢琴和吉他编曲",
            ),
            make_item(
                "AI 歌曲生成器",
                publish_time="2026-11-17T07:00:00+00:00",
            ),
        ]
        ranked = filter_and_rank_news(
            items,
            days=3,
            keyword="钢琴",
            now=self.now,
        )
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["title"], "AI 音乐工具发布")

    def test_semicolon_separates_terms_but_space_does_not(self) -> None:
        items = [
            make_item(
                "MIDI 吉他编曲工具",
                publish_time="2026-11-17T08:00:00+00:00",
            ),
            make_item(
                "M I D 三个字母与普通音乐",
                publish_time="2026-11-17T07:30:00+00:00",
            ),
        ]
        midi_only = filter_and_rank_news(
            items,
            days=3,
            keyword="MIDI",
            now=self.now,
        )
        self.assertEqual(
            [item["title"] for item in midi_only],
            ["MIDI 吉他编曲工具"],
        )

        multi_terms = filter_and_rank_news(
            items,
            days=3,
            keyword="MIDI；吉他",
            now=self.now,
        )
        self.assertEqual(
            [item["title"] for item in multi_terms],
            ["MIDI 吉他编曲工具"],
        )

        spaced_phrase = filter_and_rank_news(
            items,
            days=3,
            keyword="MIDI 吉他",
            now=self.now,
        )
        self.assertEqual(len(spaced_phrase), 1)

    def test_latin_search_term_matches_word_start_not_middle(self) -> None:
        items = [
            make_item(
                "GitHub - 新发布：AI music toolkit",
                publish_time="2026-11-17T08:00:00+00:00",
            ),
            make_item(
                "Digital reverb plugin update",
                publish_time="2026-11-17T07:00:00+00:00",
                summary="A digital audio effect",
            ),
        ]
        ranked = filter_and_rank_news(
            items,
            days=3,
            keyword="Git",
            now=self.now,
        )
        self.assertEqual(
            [item["title"] for item in ranked],
            ["GitHub - 新发布：AI music toolkit"],
        )

    def test_specific_date_overrides_relative_time_range(self) -> None:
        items = [
            make_item(
                "当天 AI 音乐资讯",
                publish_time="2026-11-15T08:00:00+00:00",
            ),
            make_item(
                "今天 AI 吉他资讯",
                publish_time="2026-11-17T08:00:00+00:00",
            ),
        ]
        ranked = filter_and_rank_news(
            items,
            days=3,
            specific_date="2026-11-15",
            now=self.now,
        )
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["title"], "当天 AI 音乐资讯")

    def test_three_days_means_three_calendar_days(self) -> None:
        local_now = datetime(2026, 11, 18, 2, 0, tzinfo=timezone.utc)
        items = [
            make_item(
                "16 日零点后资讯",
                publish_time="2026-11-15T16:01:00+00:00",
            ),
            make_item(
                "15 日深夜资讯",
                publish_time="2026-11-15T15:59:00+00:00",
            ),
        ]
        ranked = filter_and_rank_news(items, days=3, now=local_now)
        self.assertEqual(
            [item["title"] for item in ranked],
            ["16 日零点后资讯"],
        )

    def test_newer_relevant_item_usually_ranks_first(self) -> None:
        items = [
            make_item(
                "AI 钢琴与乐理工具",
                publish_time="2026-11-17T09:00:00+00:00",
                summary="AI 音乐制作、钢琴和乐理功能正式发布",
            ),
            make_item(
                "AI 音乐简讯",
                publish_time="2026-11-14T12:00:00+00:00",
            ),
        ]
        ranked = filter_and_rank_news(items, days=3, now=self.now)
        self.assertEqual(ranked[0]["title"], "AI 钢琴与乐理工具")
        self.assertTrue(all(item["rank"] > 0 for item in ranked))

    def test_music_hardware_gets_relevance_boost(self) -> None:
        from ranking import _relevance_score

        hardware = {
            "title": "智能乐器硬件与 MIDI 控制器发布",
            "summary": "面向电子乐器开发者的音频接口",
        }
        generic_music = {
            "title": "音乐学习方法更新",
            "summary": "面向普通音乐爱好者",
        }
        self.assertGreater(
            _relevance_score(hardware),
            _relevance_score(generic_music),
        )

    def test_content_kind_filter_supports_hybrid_items(self) -> None:
        items = [
            make_item(
                "硬件合成器发布",
                publish_time="2026-11-17T09:00:00+00:00",
                is_hardware=True,
            ),
            make_item(
                "AI 编曲插件发布",
                publish_time="2026-11-17T08:00:00+00:00",
                is_software=True,
            ),
            make_item(
                "MIDI 控制器与配套软件更新",
                publish_time="2026-11-17T07:00:00+00:00",
                is_hardware=True,
                is_software=True,
            ),
        ]
        hardware = filter_and_rank_news(
            items,
            days=3,
            content_kind="hardware",
            now=self.now,
        )
        software = filter_and_rank_news(
            items,
            days=3,
            content_kind="software",
            now=self.now,
        )
        self.assertEqual(
            {item["title"] for item in hardware},
            {"硬件合成器发布", "MIDI 控制器与配套软件更新"},
        )
        self.assertEqual(
            {item["title"] for item in software},
            {"AI 编曲插件发布", "MIDI 控制器与配套软件更新"},
        )

    def test_one_source_cannot_fill_an_entire_page(self) -> None:
        sogou_items = [
            make_item(
                f"搜狗微信资讯 {index}",
                publish_time=(
                    f"2026-11-17T{9 - index // 60:02d}:"
                    f"{59 - index % 60:02d}:00+00:00"
                ),
                source="搜狗微信",
                category="搜狗微信",
            )
            for index in range(25)
        ]
        other_items = [
            make_item(
                f"其他来源资讯 {index}",
                publish_time=f"2026-11-17T08:{20 - index:02d}:00+00:00",
                source=f"其他来源 {index}",
            )
            for index in range(20)
        ]
        ranked = filter_and_rank_news(
            sogou_items + other_items,
            days=3,
            now=self.now,
        )
        first_page = ranked[:20]
        self.assertLessEqual(
            sum(item["source"] == "搜狗微信" for item in first_page),
            6,
        )
        self.assertGreater(len({item["source"] for item in first_page}), 6)

    def test_heat_and_relevance_sort_modes(self) -> None:
        items = [
            make_item(
                "AI 芯片销量创新高",
                publish_time="2026-11-17T09:30:00+00:00",
                source="MusicTech",
            ),
            make_item(
                "AI 吉他编曲与混音工具发布",
                publish_time="2026-11-17T08:00:00+00:00",
                summary="人工智能音乐制作和乐器工作流",
                source="未知来源",
            ),
        ]
        by_heat = filter_and_rank_news(
            items,
            days=3,
            sort_by="heat",
            now=self.now,
        )
        self.assertEqual(by_heat[0]["title"], "AI 芯片销量创新高")

        by_relevance = filter_and_rank_news(
            items,
            days=3,
            sort_by="relevance",
            now=self.now,
        )
        self.assertEqual(
            by_relevance[0]["title"],
            "AI 吉他编曲与混音工具发布",
        )

    def test_publication_time_is_primary_sort_key(self) -> None:
        items = [
            make_item(
                "AI 音乐软件 插件 合成器 混音 母带",
                publish_time="2026-11-16T08:00:00+00:00",
                summary="AI 音乐制作 插件 功能 工作流",
            ),
            make_item(
                "最新 AI 简讯",
                publish_time="2026-11-17T09:00:00+00:00",
            ),
        ]
        ranked = filter_and_rank_news(items, days=3, now=self.now)
        self.assertEqual(ranked[0]["title"], "最新 AI 简讯")


if __name__ == "__main__":
    unittest.main()
