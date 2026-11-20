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
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from config import get_fetch_lock_path
from rss_fetcher import (
    FetchAlreadyRunningError,
    FetchRoute,
    _advance_sogou_batch_cursor,
    _incremental_source_since,
    _direct_source_urls,
    _is_allowed_source_result,
    _next_sogou_query_batch,
    _parse_feed_content,
    _sogou_query_date_bounds,
    _sogou_queries_due,
    fetch_and_save_news,
    fetch_one_source,
)
from database import get_meta_value, set_meta_value


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

STRICT_FOREIGN_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Strict Foreign Feed</title>
    <item>
      <title>Artist interview about a classic album</title>
      <link>https://example.com/culture-story</link>
      <description>A singer discusses the making of a hit song.</description>
      <pubDate>Sun, 16 Nov 2026 07:00:00 GMT</pubDate>
    </item>
    <item>
      <title>New MIDI controller and audio interface released</title>
      <link>https://example.com/studio-hardware</link>
      <description>USB-C music hardware for a home studio.</description>
      <pubDate>Sun, 16 Nov 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
""".encode("utf-8")

MALFORMED_SEARCH_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Malformed Search Feed</title>
    <item>
      <title>AI 音乐软件 &amp; MIDI 工具更新</title>
      <link>https://example.com/search?q=ai&type=2</link>
      <description><![CDATA[AI 编曲工具发布<br>支持 MIDI 和混音功能]]></description>
      <pubDate>Wed, 19 Nov 2026 07:00:00 GMT</pubDate>
    </item>
    <item>
      <title>普通天气新闻</title>
      <link>https://example.com/weather?date=today&city=beijing</link>
      <description>今日天气晴朗&nbsp;适合出行</description>
      <pubDate>Wed, 19 Nov 2026 06:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
""".encode("utf-8")

BAIDU_SEARCH_HTML = """<!doctype html>
<html><body>
  <ul class="news-list">
    <li class="result">
      <h3><a href="/link?url=ai-music-1">AI 音乐编曲软件新增 MIDI 混音功能</a></h3>
      <span>2026-11-19 14:20</span>
      <p>该工具支持 AI 编曲和音频编辑。</p>
    </li>
    <li class="result">
      <h3><a href="/link?url=weather-1">今天北京天气晴朗</a></h3>
      <span>2026-11-19 13:00</span>
      <p>普通天气新闻。</p>
    </li>
  </ul>
</body></html>
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
    def test_fetch_stops_starting_sources_after_global_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "fetch-budget.db"
            event_session = ClosingSession()
            fetch_mock = Mock()
            with (
                patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}),
                patch(
                    "rss_fetcher.RSS_SOURCES",
                    (
                        {
                            "source": "测试源",
                            "url": "https://example.com/feed",
                        },
                    ),
                ),
                patch("rss_fetcher.GITHUB_RELEASE_REPOSITORIES", ()),
                patch("rss_fetcher.GITHUB_DISCOVERY_ENABLED", False),
                patch("rss_fetcher.WATCHED_ARTICLE_URLS", ()),
                patch("rss_fetcher.SOGOU_WECHAT_QUERIES", ()),
                patch("rss_fetcher.FETCH_TIME_BUDGET_SECONDS", 0),
                patch(
                    "rss_fetcher._discover_fetch_routes",
                    return_value=[FetchRoute("测试通道", event_session)],
                ),
                patch(
                    "rss_fetcher.fetch_one_source",
                    fetch_mock,
                ),
            ):
                result = fetch_and_save_news()

        fetch_mock.assert_not_called()
        self.assertEqual(result.source_count, 0)
        self.assertTrue(
            any("抓取总时间达到" in error for error in result.errors)
        )

    def test_sogou_signature_change_resets_batch_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sogou-signature.db"
            with (
                patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}),
                patch(
                    "rss_fetcher.SOGOU_WECHAT_QUERIES",
                    ("Midifan", "叉烧网"),
                ),
            ):
                from database import initialize_database

                initialize_database()
                set_meta_value("sogou_query_signature", "old-query")
                set_meta_value("sogou_batch_cursor", "31")
                self.assertTrue(
                    _sogou_queries_due(datetime.now(timezone.utc))
                )
                self.assertEqual(get_meta_value("sogou_batch_cursor"), "0")

    def test_sogou_queries_rotate_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sogou-batches.db"
            with (
                patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}),
                patch(
                    "rss_fetcher.SOGOU_WECHAT_QUERIES",
                    ("a", "b", "c", "d", "e"),
                ),
                patch(
                    "rss_fetcher.SOGOU_MAX_QUERIES_PER_RUN",
                    2,
                ),
            ):
                from database import initialize_database

                initialize_database()
                self.assertEqual(_next_sogou_query_batch(), ("a", "b"))
                _advance_sogou_batch_cursor(0, 2)
                self.assertEqual(_next_sogou_query_batch(), ("c", "d"))
                _advance_sogou_batch_cursor(2, 2)
                self.assertEqual(_next_sogou_query_batch(), ("e", "a"))

    def test_sogou_cursor_keeps_unprocessed_queries_after_partial_batch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "sogou-partial.db"
            with (
                patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}),
                patch(
                    "rss_fetcher.SOGOU_WECHAT_QUERIES",
                    ("a", "b", "c", "d", "e"),
                ),
                patch(
                    "rss_fetcher.SOGOU_MAX_QUERIES_PER_RUN",
                    2,
                ),
            ):
                from database import initialize_database

                initialize_database()
                batch = _next_sogou_query_batch()
                self.assertEqual(batch, ("a", "b"))
                # 如果只完成了第一个词，下一次不能跳到 c。
                _advance_sogou_batch_cursor(0, 1)
                self.assertEqual(_next_sogou_query_batch(), ("b", "c"))

    def test_sogou_queries_use_retention_date_window(self) -> None:
        now = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)
        with patch("rss_fetcher.NEWS_RETENTION_DAYS", 60):
            start_date, end_date = _sogou_query_date_bounds(
                "Midifan",
                now,
            )
            self.assertEqual(start_date, "2026-09-21")
            self.assertEqual(end_date, "2026-11-19")
            self.assertEqual(
                _sogou_query_date_bounds("AI音乐", now),
                ("2026-09-21", "2026-11-19"),
            )

    def test_direct_source_uses_last_successful_fetch_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "source-since.db"
            with patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}):
                from database import initialize_database

                initialize_database()
                set_meta_value(
                    "source_last_success::Midifan",
                    "2026-11-20T00:00:00+00:00",
                )
                self.assertEqual(
                    _incremental_source_since(
                        "Midifan",
                        datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc),
                    ),
                    "2026-11-19T00:00:00+00:00",
                )

    def test_direct_source_url_fallbacks_are_deduplicated(self) -> None:
        self.assertEqual(
            _direct_source_urls(
                {
                    "url": "https://example.com/",
                    "fallback_urls": (
                        "https://example.net/, https://example.com/"
                    ),
                }
            ),
            ("https://example.com/", "https://example.net/"),
        )

    def test_named_site_search_only_accepts_official_domains(self) -> None:
        self.assertTrue(
            _is_allowed_source_result(
                "百度新闻：Soomal",
                "https://www.soomal.com/doc/10100000001.htm",
            )
        )
        self.assertFalse(
            _is_allowed_source_result(
                "百度新闻：Soomal",
                "https://baijiahao.baidu.com/s?id=123",
            )
        )
        self.assertTrue(
            _is_allowed_source_result(
                "百度新闻：音频应用",
                "http://www.audiobar.net/thread-1-1-1.html",
            )
        )

    def test_baidu_security_page_is_reported_explicitly(self) -> None:
        entries, error = _parse_feed_content(
            "<html><title>百度安全验证</title><body></body></html>".encode(),
            source="百度新闻：合成器",
        )
        self.assertEqual(entries, [])
        self.assertEqual(error, "百度安全验证")

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

    def test_foreign_source_passes_source_into_strict_filter(self) -> None:
        """RSS 适配器必须把来源名称传给过滤器，严格规则才会生效。"""

        items, total, matched = fetch_one_source(
            FakeSession(STRICT_FOREIGN_RSS),
            "MusicRadar",
            "https://example.com/feed.xml",
            "音乐科技",
        )

        self.assertEqual(total, 2)
        self.assertEqual(matched, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["title"],
            "New MIDI controller and audio interface released",
        )

    def test_malformed_search_rss_is_recovered(self) -> None:
        """百度搜索 RSS 的裸 & 和 HTML 标签不应导致整份结果被丢弃。"""

        items, total, matched = fetch_one_source(
            FakeSession(MALFORMED_SEARCH_RSS),
            "百度新闻：AI音乐软件",
            "https://example.com/malformed.xml",
            "国内科技",
        )

        self.assertEqual(total, 2)
        self.assertEqual(matched, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["link"],
            "https://example.com/search?q=ai&type=2",
        )
        self.assertIn("AI 编曲工具发布", items[0]["summary"])

    def test_baidu_html_search_results_are_recovered(self) -> None:
        """百度 RSS 失效但返回搜索网页时，仍应提取标题、链接和真实日期。"""

        items, total, matched = fetch_one_source(
            FakeSession(BAIDU_SEARCH_HTML),
            "百度新闻：AI音乐软件",
            "https://news.baidu.com/ns?word=AI音乐",
            "国内科技",
        )

        self.assertEqual(total, 2)
        self.assertEqual(matched, 1)
        self.assertEqual(len(items), 1)
        self.assertIn("AI 音乐编曲软件", items[0]["title"])
        self.assertTrue(items[0]["dedupe_key"].startswith("baidu:"))
        self.assertEqual(
            items[0]["publish_time"],
            "2026-11-19T06:20:00+00:00",
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
                *,
                source_focus: str = "",
            ):
                del source_focus
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
                **_kwargs: object,
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
