"""直接站点文章列表解析测试，不访问真实网络。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from direct_site import (
    extract_article_publish_time,
    extract_article_title,
    fetch_direct_site,
)


HOME_HTML = """
<html><body>
  <nav><a href="/about">关于我们</a></nav>
  <div class="news-list">
    <div>
      <a href="/archives/2026/new-synth.html" title="2026 新款合成器正式发布 这是摘要 16 小时前">
        2026 新款合成器正式发布 这是一段不应进入标题的摘要 16 小时前
      </a>
    </div>
  </div>
</body></html>
"""

ARTICLE_HTML = """
<html><head>
  <meta property="article:published_time" content="2026-11-19T08:00:00+08:00">
  <title>2026 新款合成器正式发布 - Midifan</title>
</head><body><h1>2026 新款合成器正式发布</h1></body></html>
"""

PAGE_TWO_HTML = """
<html><body>
  <div><a href="/archives/2026/midi-controller.html">新款 MIDI 控制器发布</a>
  <span>2026-11-18</span></div>
</body></html>
"""


class DirectSiteTests(unittest.TestCase):
    def test_article_metadata_date_is_extracted(self) -> None:
        html = """
        <html><head>
          <meta property="article:published_time" content="2026-11-19T08:30:00+08:00">
        </head></html>
        """
        self.assertEqual(
            extract_article_publish_time(html),
            "2026-11-19T00:30:00+00:00",
        )
        self.assertEqual(
            extract_article_title(ARTICLE_HTML, "Midifan"),
            "2026 新款合成器正式发布",
        )

    def test_homepage_title_link_and_date_are_parsed(self) -> None:
        class Response:
            def __init__(self, text: str, url: str) -> None:
                self.text = text
                self.url = url
                self.encoding = "utf-8"
                self.apparent_encoding = "utf-8"

            def raise_for_status(self) -> None:
                return None

        class Session:
            def get(self, url: str, **_kwargs: object) -> Response:
                if url.endswith("new-synth.html"):
                    return Response(ARTICLE_HTML, url)
                return Response(HOME_HTML, url)

        items, total, matched = fetch_direct_site(
            Session(),
            "Midifan",
            "https://www.midifan.com/",
        )
        self.assertEqual(total, 1)
        self.assertEqual(matched, 1)
        self.assertEqual(items[0]["source"], "Midifan")
        self.assertEqual(items[0]["title"], "2026 新款合成器正式发布")
        self.assertEqual(
            items[0]["link"],
            "https://www.midifan.com/archives/2026/new-synth.html",
        )
        self.assertEqual(
            items[0]["publish_time"],
            "2026-11-19T00:00:00+00:00",
        )

    def test_next_page_is_followed(self) -> None:
        class Response:
            def __init__(self, text: str, url: str) -> None:
                self.text = text
                self.url = url
                self.encoding = "utf-8"
                self.apparent_encoding = "utf-8"

            def raise_for_status(self) -> None:
                return None

        class Session:
            def get(self, url: str, **_kwargs: object) -> Response:
                if "page=2" in url:
                    return Response(PAGE_TWO_HTML, url)
                if url.endswith("new-synth.html"):
                    return Response(ARTICLE_HTML, url)
                return Response(
                    HOME_HTML.replace(
                        "</body>",
                        '<a href="?page=2" rel="next">下一页</a></body>',
                    ),
                    url,
                )

        items, total, matched = fetch_direct_site(
            Session(),
            "Midifan",
            "https://www.midifan.com/",
            max_pages=2,
            max_articles=10,
        )
        self.assertEqual(total, 2)
        self.assertEqual(matched, 2)
        self.assertEqual(
            {item["link"] for item in items},
            {
                "https://www.midifan.com/archives/2026/new-synth.html",
                "https://www.midifan.com/archives/2026/midi-controller.html",
            },
        )

    def test_browser_rendering_is_used_when_static_html_is_empty(self) -> None:
        class Response:
            def __init__(self, text: str, url: str) -> None:
                self.text = text
                self.url = url
                self.encoding = "utf-8"
                self.apparent_encoding = "utf-8"

            def raise_for_status(self) -> None:
                return None

        class Session:
            def get(self, url: str, **_kwargs: object) -> Response:
                return Response("<html><div id='app'></div></html>", url)

        rendered_home = HOME_HTML.replace(
            "</a>\n    </div>",
            "</a><span>2026-11-19</span>\n    </div>",
        )
        with patch(
            "direct_site._render_with_chromium",
            return_value=rendered_home,
        ):
            items, total, matched = fetch_direct_site(
                Session(),
                "叉烧网",
                "https://www.exound.com/",
                browser_fallback=True,
            )
        self.assertEqual(total, 1)
        self.assertEqual(matched, 1)
        self.assertEqual(items[0]["source"], "叉烧网")

    def test_browser_rendering_is_used_when_request_is_forbidden(self) -> None:
        class Session:
            def get(self, _url: str, **_kwargs: object) -> object:
                raise RuntimeError("403 Forbidden")

        rendered_home = HOME_HTML.replace(
            "</a>\n    </div>",
            "</a><span>2026-11-19</span>\n    </div>",
        )
        with patch(
            "direct_site._render_with_chromium",
            return_value=rendered_home,
        ):
            items, total, matched = fetch_direct_site(
                Session(),
                "Soomal",
                "http://www.soomal.com/",
                browser_fallback=True,
            )
        self.assertEqual(total, 1)
        self.assertEqual(matched, 1)
        self.assertEqual(items[0]["source"], "Soomal")

    def test_incremental_crawl_stops_after_reaching_previous_success_time(
        self,
    ) -> None:
        older_page = """
        <html><body><div>
          <a href="/archives/2026/older.html">旧款合成器历史发布</a>
          <span>2026-11-17</span>
        </div></body></html>
        """
        first_page = """
        <html><body><div>
          <a href="/archives/2026/new.html">新款音源插件正式发布</a>
          <span>2026-11-19</span>
        </div><div>
          <a href="/archives/2026/older.html">旧款合成器历史发布</a>
          <span>2026-11-17</span>
        </div><a href="?page=2" rel="next">下一页</a></body></html>
        """
        requested_urls: list[str] = []

        class Response:
            def __init__(self, text: str, url: str) -> None:
                self.text = text
                self.url = url
                self.encoding = "utf-8"
                self.apparent_encoding = "utf-8"

            def raise_for_status(self) -> None:
                return None

        class Session:
            def get(self, url: str, **_kwargs: object) -> Response:
                requested_urls.append(url)
                if "page=2" in url:
                    return Response(older_page, url)
                return Response(first_page, url)

        items, total, matched = fetch_direct_site(
            Session(),
            "Midifan",
            "https://www.midifan.com/",
            max_pages=8,
            max_articles=200,
            since="2026-11-18T00:00:00+00:00",
        )
        self.assertEqual(total, 2)
        self.assertEqual(matched, 2)
        self.assertFalse(any("page=2" in url for url in requested_urls))


if __name__ == "__main__":
    unittest.main()
