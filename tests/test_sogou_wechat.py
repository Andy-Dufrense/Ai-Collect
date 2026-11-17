"""搜狗微信搜索结果解析测试，不访问真实网络。"""

from __future__ import annotations

import unittest

from sogou_wechat import build_sogou_url, parse_sogou_results


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


if __name__ == "__main__":
    unittest.main()
