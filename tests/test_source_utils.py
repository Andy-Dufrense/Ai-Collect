"""来源展示名称测试。"""

from __future__ import annotations

import unittest

from source_utils import display_source_name, is_safe_http_url


class SourceUtilsTests(unittest.TestCase):
    def test_generic_sogou_names_are_hidden(self) -> None:
        self.assertEqual(display_source_name("搜狗搜索"), "微信文章")
        self.assertEqual(
            display_source_name("搜狗搜索 · AI编程"),
            "微信文章",
        )
        self.assertEqual(display_source_name("搜狗微信"), "微信文章")
        self.assertEqual(
            display_source_name("百度新闻：Soomal"),
            "Soomal",
        )
        self.assertEqual(
            display_source_name("百度新闻：音频应用"),
            "音频应用",
        )

    def test_real_source_names_are_preserved(self) -> None:
        for name in ("Midifan", "叉烧网", "我爱音频网", "MusicTech"):
            self.assertEqual(display_source_name(name), name)

    def test_only_http_article_links_are_safe(self) -> None:
        self.assertTrue(is_safe_http_url("https://example.com/news"))
        self.assertTrue(is_safe_http_url("http://example.com/news"))
        self.assertFalse(is_safe_http_url("javascript:alert(1)"))
        self.assertFalse(is_safe_http_url("data:text/html,hello"))
        self.assertFalse(is_safe_http_url("file:///tmp/news.html"))
        self.assertFalse(is_safe_http_url("https://example.com/a b"))


if __name__ == "__main__":
    unittest.main()
