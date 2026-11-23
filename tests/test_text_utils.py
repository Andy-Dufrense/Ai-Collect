"""文本乱码修复的离线测试。"""

from __future__ import annotations

import unittest

from text_utils import (
    charset_from_content_type,
    decode_html_content,
    is_likely_mojibake,
    repair_mojibake,
)


class TextUtilsTests(unittest.TestCase):
    def test_macroman_chinese_mojibake_is_repaired(self) -> None:
        broken = (
            "‰∏ÄÈ¶ñÊ≠å‰∏ÄÈîÆÂèòÂ§ßÁâáÔºÅËãèËØ∫ AI MV "
            "ÂäüËÉΩÈáçÁ£Ö‰∏äÁ∫ø,‰∏ÄÁßí‰ΩéËá≥3ÂàÜÈí±!"
        )
        repaired = repair_mojibake(broken)

        self.assertEqual(
            repaired,
            "一首歌一键变大片！苏诺 AI MV 功能重磅上线,一秒低至3分钱!",
        )

    def test_normal_chinese_and_accented_names_are_not_changed(self) -> None:
        for value in (
            "一首歌一键变大片！苏诺 AI MV 功能重磅上线",
            "Våld Labs TRESSE synthesizer",
            "Loops de la Crème releases Kontakt instrument",
        ):
            with self.subTest(value=value):
                self.assertEqual(repair_mojibake(value), value)

    def test_gbk_html_is_not_decoded_as_windows_1251(self) -> None:
        html = (
            '<html><head><meta charset="gbk"></head>'
            "<body>新闻 发布 智能乐器 监听音箱</body></html>"
        ).encode("gb18030")

        decoded = decode_html_content(
            html,
            declared_encoding="windows-1251",
        )

        self.assertIn("新闻", decoded)
        self.assertIn("智能乐器", decoded)
        self.assertNotIn("РВОЕ", decoded)
        self.assertEqual(
            charset_from_content_type(
                'text/html; charset="GBK"'
            ),
            "GBK",
        )

    def test_gbk_without_meta_prefers_gb18030_before_wrong_header(self) -> None:
        content = "发布免费音频工作站".encode("gb18030")
        decoded = decode_html_content(
            content,
            declared_encoding="windows-1251",
        )
        self.assertEqual(decoded, "发布免费音频工作站")

    def test_cp1251_style_mojibake_fragments_are_repaired(self) -> None:
        broken = (
            "[РВОЕ] Korg ЕФащФтФЃФтКЯГЩЦїЙЬМў"
        )
        repaired = repair_mojibake(broken)
        self.assertIn("[新闻]", repaired)
        self.assertIn("的虚拟模拟合成器固件", repaired)
        self.assertTrue(is_likely_mojibake(broken))
        self.assertFalse(is_likely_mojibake(repaired))


if __name__ == "__main__":
    unittest.main()
