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
) -> dict[str, str | None]:
    return {
        "title": title,
        "summary": summary,
        "publish_time": publish_time,
        "source": source,
        "category": category,
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
