"""
RSS 解析流程的离线测试。

测试通过一个模拟的 HTTP 响应提供固定 RSS XML，不会访问网络。
这样可以稳定验证：RSS 条目能被解析、HTML 简介会被清理、过滤条件会生效，
以及无效 RSS 会产生明确错误。
"""

from __future__ import annotations

import fcntl
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from config import get_fetch_lock_path
from rss_fetcher import (
    FetchAlreadyRunningError,
    fetch_and_save_news,
    fetch_one_source,
)


TEST_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>AI 编曲工具正式发布</title>
      <link>https://example.com/relevant</link>
      <description><![CDATA[<p>这是一款面向<strong>音乐</strong>创作的工具。</p>]]></description>
      <pubDate>Sun, 16 Nov 2026 07:00:00 GMT</pubDate>
    </item>
    <item>
      <title>普通行业新闻</title>
      <link>https://example.com/irrelevant</link>
      <description>这是一条与本周消费市场有关的普通新闻。</description>
    </item>
    <item>
      <title>今日天气与晚餐建议</title>
      <link>https://example.com/lifestyle</link>
      <description>本次介绍周末天气和家常菜。</description>
    </item>
  </channel>
</rss>
""".encode("utf-8")


class FakeResponse:
    """模拟 requests.Response 中最少的必要接口。"""

    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    """模拟 requests.Session，并记录网络下载之后无需真实联网。"""

    def __init__(self, content: bytes) -> None:
        self.content = content

    def get(self, url: str, timeout: float) -> FakeResponse:
        del url, timeout
        return FakeResponse(self.content)


class ClosingSession:
    """只模拟抓取结束后的 close 行为。"""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class RssFetcherTests(unittest.TestCase):
    def test_relevant_item_is_parsed_and_cleaned(self) -> None:
        items, total, matched = fetch_one_source(
            FakeSession(TEST_RSS),
            "测试源",
            "https://example.com/feed.xml",
        )

        self.assertEqual(total, 3)
        self.assertEqual(matched, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "AI 编曲工具正式发布")
        self.assertEqual(items[0]["summary"], "这是一款面向 音乐 创作的工具。")
        self.assertEqual(items[0]["publish_time"], "2026-11-16T07:00:00+00:00")

    def test_empty_feed_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            fetch_one_source(
                FakeSession(b"<html>not an rss feed</html>"),
                "错误源",
                "https://example.com/broken",
            )

    def test_second_fetch_is_rejected_while_lock_is_held(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "lock-test.db"
            with patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}):
                lock_path = get_fetch_lock_path()
                with lock_path.open("a+", encoding="utf-8") as lock_file:
                    fcntl.flock(
                        lock_file.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                    with self.assertRaises(FetchAlreadyRunningError):
                        fetch_and_save_news()

    def test_proxy_error_falls_back_to_direct_connection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "fallback-test.db"
            sessions: list[ClosingSession] = []
            call_count = 0

            def fake_build_session(
                use_environment_proxy: bool = True,
            ) -> ClosingSession:
                del use_environment_proxy
                session = ClosingSession()
                sessions.append(session)
                return session

            def fake_fetch(
                _session: object,
                _source: str,
                _url: str,
                _category: str = "RSS",
            ):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise requests.exceptions.ProxyError("代理未启动")
                return (
                    [
                        {
                            "title": "AI 音乐新闻",
                            "link": "https://example.com/fallback",
                            "source": "测试源",
                            "publish_time": None,
                            "summary": "直连成功",
                        }
                    ],
                    1,
                    1,
                )

            with (
                patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}),
                patch(
                    "rss_fetcher.RSS_SOURCES",
                    ({"source": "测试源", "url": "https://example.com/feed"},),
                ),
                patch("rss_fetcher.SOGOU_WECHAT_QUERIES", ()),
                patch("rss_fetcher.GITHUB_RELEASE_REPOSITORIES", ()),
                patch("rss_fetcher.GITHUB_DISCOVERY_ENABLED", False),
                patch("rss_fetcher.WATCHED_ARTICLE_URLS", ()),
                patch(
                    "rss_fetcher._build_http_session",
                    side_effect=fake_build_session,
                ),
                patch(
                    "rss_fetcher.fetch_one_source",
                    side_effect=fake_fetch,
                ),
            ):
                result = fetch_and_save_news()

            self.assertEqual(result.successful_sources, 1)
            self.assertEqual(result.errors, [])
            self.assertEqual(call_count, 2)
            self.assertEqual(len(sessions), 2)
            self.assertTrue(all(session.closed for session in sessions))

    def test_empty_sogou_query_does_not_stop_later_queries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sogou-continue.db"
            queries: list[str] = []

            def fake_sogou(
                _session: object,
                query: str,
            ):
                queries.append(query)
                if query == "没有结果的词":
                    raise ValueError("搜狗没有返回搜索结果")
                return (
                    [
                        {
                            "title": "AI 编曲软件更新",
                            "link": "https://example.com/sogou",
                            "source": "测试公众号",
                            "publish_time": "2026-11-19T01:00:00+00:00",
                            "summary": "音乐制作功能更新",
                            "category": "搜狗微信",
                            "dedupe_key": "sogou:test",
                        }
                    ],
                    1,
                    1,
                )

            with (
                patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}),
                patch("rss_fetcher.RSS_SOURCES", ()),
                patch("rss_fetcher.GITHUB_RELEASE_REPOSITORIES", ()),
                patch("rss_fetcher.GITHUB_DISCOVERY_ENABLED", False),
                patch("rss_fetcher.WATCHED_ARTICLE_URLS", ()),
                patch(
                    "rss_fetcher.SOGOU_WECHAT_QUERIES",
                    ("没有结果的词", "AI编曲"),
                ),
                patch("rss_fetcher._sogou_queries_due", return_value=True),
                patch(
                    "rss_fetcher._build_http_session",
                    return_value=ClosingSession(),
                ),
                patch(
                    "rss_fetcher.fetch_sogou_query",
                    side_effect=fake_sogou,
                ),
            ):
                result = fetch_and_save_news()

            self.assertEqual(queries, ["没有结果的词", "AI编曲"])
            self.assertEqual(result.successful_sources, 1)
            self.assertEqual(result.source_count, 2)


if __name__ == "__main__":
    unittest.main()
