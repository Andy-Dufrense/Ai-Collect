"""搜狗微信搜索结果解析测试，不访问真实网络。"""

from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from sogou_wechat import (
    _extract_publish_time,
    build_sogou_url,
    parse_sogou_results,
)


SOGOU_HTML = """
<html>
  <body>
    <ul class="news-list">
      <li>
        <div class="txt-box">
          <h3><a href="/link?url=relevant">AI 音乐生成工具发布</a></h3>
          <p class="txt-info">一款面向编曲和音色设计的智能工具。</p>
          <a class="account">音乐科技观察</a>
          <span class="s2"><script>document.write(timeConvert('1763280000'))</script></span>
        </div>
      </li>
      <li>
        <div class="txt-box">
          <h3><a href="/link?url=irrelevant">今日天气与晚餐建议</a></h3>
          <p class="txt-info">周末天气和家常菜介绍。</p>
          <a class="account">科技日报</a>
          <span class="s2"><script>document.write(timeConvert('1763280000'))</script></span>
        </div>
      </li>
    </ul>
  </body>
</html>
"""


class SogouWechatTests(unittest.TestCase):
    def test_query_is_url_encoded(self) -> None:
        url = build_sogou_url("AI音乐")
        self.assertIn("query=AI%E9%9F%B3%E4%B9%90", url)

    def test_custom_date_range_is_included(self) -> None:
        url = build_sogou_url(
            "AI音乐",
            start_date="2026-11-01",
            end_date="2026-11-01",
        )
        self.assertIn("tsn=5", url)
        self.assertIn("ft=2026-11-01", url)
        self.assertIn("et=2026-11-01", url)

    def test_second_page_parameter_is_included(self) -> None:
        url = build_sogou_url("Suno", page=2)
        self.assertIn("page=2", url)

    def test_only_dedicated_time_element_is_used(self) -> None:
        node = BeautifulSoup(
            """
            <li>
              <script>var articleId = "1763000000";</script>
              <span class="s2">2023-08-12</span>
            </li>
            """,
            "html.parser",
        ).li
        self.assertEqual(
            _extract_publish_time(node),
            "2023-08-12T00:00:00+00:00",
        )

    def test_only_relevant_results_are_returned(self) -> None:
        items, total, matched = parse_sogou_results(
            SOGOU_HTML,
            page_url="https://weixin.sogou.com/weixin?type=2&query=test",
        )
        self.assertEqual(total, 2)
        self.assertEqual(matched, 1)
        self.assertEqual(items[0]["title"], "AI 音乐生成工具发布")
        self.assertEqual(items[0]["category"], "搜狗微信")
        self.assertEqual(items[0]["source"], "音乐科技观察")
        self.assertEqual(items[0]["publish_time"], "2025-11-16T08:00:00+00:00")
        self.assertTrue(str(items[0]["dedupe_key"]).startswith("sogou:"))
        self.assertTrue(str(items[0]["link"]).startswith("https://weixin.sogou.com/"))

    def test_query_is_used_when_account_name_is_missing(self) -> None:
        html = SOGOU_HTML.replace(
            '<a class="account">音乐科技观察</a>',
            "",
        )
        items, _total, matched = parse_sogou_results(
            html,
            page_url="https://weixin.sogou.com/weixin?type=2&query=Midifan",
            query="Midifan",
        )
        self.assertEqual(matched, 1)
        self.assertEqual(
            items[0]["source"],
            "搜狗搜索 · Midifan",
        )

    def test_keyword_query_uses_generic_fallback(self) -> None:
        html = SOGOU_HTML.replace(
            '<a class="account">音乐科技观察</a>',
            "",
        )
        items, _total, matched = parse_sogou_results(
            html,
            page_url="https://weixin.sogou.com/weixin?type=2&query=AI编程",
            query="AI编程",
        )
        self.assertEqual(matched, 1)
        self.assertEqual(
            items[0]["source"],
            "搜狗搜索",
        )


if __name__ == "__main__":
    unittest.main()
