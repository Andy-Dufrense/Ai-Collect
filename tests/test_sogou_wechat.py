"""搜狗微信搜索结果解析测试，不访问真实网络。"""

from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from sogou_wechat import (
    _extract_publish_time,
    _resolve_sogou_article_link,
    build_stable_sogou_fallback_link,
    build_sogou_url,
    canonicalize_wechat_article_link,
    fetch_sogou_query,
    is_temporary_article_link,
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

    def test_preset_time_range_is_included(self) -> None:
        url = build_sogou_url("Midifan", time_range="3")
        self.assertIn("tsn=3", url)
        self.assertNotIn("ft=", url)

    def test_second_page_parameter_is_included(self) -> None:
        url = build_sogou_url("Suno", page=2)
        self.assertIn("page=2", url)

    def test_temporary_links_are_normalized_to_stable_links(self) -> None:
        signed_link = (
            "https://mp.weixin.qq.com/s?__biz=abc&mid=123&idx=1&sn=def"
            "&src=11&timestamp=1795130000&signature=temporary"
        )
        self.assertTrue(is_temporary_article_link(signed_link))
        self.assertEqual(
            canonicalize_wechat_article_link(signed_link),
            "https://mp.weixin.qq.com/s?__biz=abc&mid=123&idx=1&sn=def",
        )
        fallback = build_stable_sogou_fallback_link("酷狗音乐新功能上线")
        self.assertIn("query=%E9%85%B7%E7%8B%97", fallback)
        self.assertNotIn("/link?url=", fallback)

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
            "Midifan",
        )
        self.assertEqual(items[0]["category"], "音乐科技")

    def test_explicit_site_keeps_daw_update_without_ai_in_title(self) -> None:
        html = """
        <html><body><ul class="news-list"><li>
          <h3><a href="/link?url=daw">Steinberg updates Cubase with new chord tools</a></h3>
          <p class="txt-info">A DAW workflow and software update for producers.</p>
          <a class="account">Midifan</a>
          <span class="s2"><script>document.write(timeConvert('1763280000'))</script></span>
        </li></ul></body></html>
        """
        items, total, matched = parse_sogou_results(
            html,
            page_url="https://weixin.sogou.com/weixin?type=2&query=Midifan",
            query="Midifan",
        )
        self.assertEqual(total, 1)
        self.assertEqual(matched, 1)
        self.assertEqual(items[0]["source"], "Midifan")
        self.assertEqual(items[0]["category"], "音乐科技")

    def test_explicit_site_fetch_success_path_is_usable(self) -> None:
        """完整站点查询路径不能只在解析函数测试中通过。"""

        html = """
        <html><body><ul class="news-list"><li>
          <h3><a href="https://mp.weixin.qq.com/s?__biz=midifan&amp;mid=123&amp;idx=1&amp;sn=abc">Steinberg updates Cubase with new chord tools</a></h3>
          <p class="txt-info">A DAW workflow and software update for producers.</p>
          <a class="account">Midifan</a>
          <span class="s2"><script>document.write(timeConvert('1763280000'))</script></span>
        </li></ul></body></html>
        """

        class FakeResponse:
            def __init__(self, text: str, url: str) -> None:
                self.text = text
                self.url = url
                self.status_code = 200
                self.history = []
                self.encoding = "utf-8"
                self.apparent_encoding = "utf-8"

            def raise_for_status(self) -> None:
                return None

        class FakeSession:
            def __init__(self) -> None:
                self.headers: dict[str, str] = {}

            def get(self, url: str, **_kwargs: object) -> FakeResponse:
                if url == "https://weixin.sogou.com/":
                    return FakeResponse("<html></html>", url)
                return FakeResponse(html, url)

        items, total, matched = fetch_sogou_query(
            FakeSession(),  # type: ignore[arg-type]
            "Midifan 2026",
            source_query="Midifan",
            pages=1,
        )
        self.assertEqual(total, 1)
        self.assertEqual(matched, 1)
        self.assertEqual(items[0]["source"], "Midifan")
        self.assertEqual(items[0]["category"], "音乐科技")
        self.assertEqual(
            items[0]["link"],
            "https://mp.weixin.qq.com/s?__biz=midifan&mid=123&idx=1&sn=abc",
        )

    def test_explicit_site_drops_results_older_than_requested_window(
        self,
    ) -> None:
        html = """
        <html><body><ul class="news-list"><li>
          <h3><a href="https://mp.weixin.qq.com/s?__biz=old">Steinberg updates Cubase with new chord tools</a></h3>
          <p class="txt-info">A DAW workflow and software update for producers.</p>
          <a class="account">Midifan</a>
          <span class="s2"><script>document.write(timeConvert('1577836800'))</script></span>
        </li></ul></body></html>
        """

        class FakeResponse:
            url = "https://weixin.sogou.com/weixin?type=2&query=Midifan"
            text = html
            status_code = 200
            history: list[object] = []
            encoding = "utf-8"
            apparent_encoding = "utf-8"

            def raise_for_status(self) -> None:
                return None

        class FakeSession:
            headers: dict[str, str] = {}

            def get(self, _url: str, **_kwargs: object) -> FakeResponse:
                return FakeResponse()

        items, total, matched = fetch_sogou_query(
            FakeSession(),  # type: ignore[arg-type]
            "Midifan",
            minimum_publish_date="2026-09-21",
            pages=1,
        )
        self.assertEqual(total, 1)
        self.assertEqual(matched, 0)
        self.assertEqual(items, [])

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

    def test_sogou_redirect_script_can_be_resolved(self) -> None:
        class RedirectResponse:
            url = "https://weixin.sogou.com/link?url=test"
            text = (
                "<script>var url='';"
                "url += 'https://mp.weixin.qq.com/s?__biz=abc\\x26id=1';"
                "</script>"
            )

        class RedirectSession:
            def get(self, _link: str, **_kwargs: object) -> RedirectResponse:
                return RedirectResponse()

        self.assertEqual(
            _resolve_sogou_article_link(
                RedirectSession(),  # type: ignore[arg-type]
                "https://weixin.sogou.com/link?url=test",
            ),
            "https://mp.weixin.qq.com/s?__biz=abc&id=1",
        )


if __name__ == "__main__":
    unittest.main()
