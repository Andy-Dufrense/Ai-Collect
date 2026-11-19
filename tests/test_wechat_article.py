"""指定微信公众号文章解析测试。"""

from __future__ import annotations

import unittest

from wechat_article import parse_wechat_article


ARTICLE_HTML = """
<html>
  <head>
    <meta property="og:title" content="SUNO 发布 AI MV 重磅上线">
    <meta property="og:description" content="用 AI 生成完整音乐视频。">
  </head>
  <body>
    <a id="js_name">Suno 官方公众号</a>
    <script>var ct = "1763500000";</script>
    <div id="js_content">文章正文内容</div>
  </body>
</html>
"""


class WechatArticleTests(unittest.TestCase):
    def test_relevant_article_is_parsed(self) -> None:
        items, total, matched = parse_wechat_article(
            ARTICLE_HTML,
            link="https://mp.weixin.qq.com/s/example",
            source="微信公众号 · SUNO",
        )
        self.assertEqual(total, 1)
        self.assertEqual(matched, 1)
        self.assertEqual(items[0]["title"], "SUNO 发布 AI MV 重磅上线")
        self.assertEqual(items[0]["category"], "微信公众号")
        self.assertEqual(
            items[0]["publish_time"],
            "2025-11-18T21:06:40+00:00",
        )


if __name__ == "__main__":
    unittest.main()
