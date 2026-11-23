"""文本乱码修复的离线测试。"""

from __future__ import annotations

import unittest

from text_utils import (
    charset_from_content_type,
    decode_html_content,
    is_likely_mojibake,
    recover_title_from_summary,
    repair_mojibake,
    strip_title_category_prefix,
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

    def test_real_organ_site_multi_codepage_titles_are_repaired(self) -> None:
        cases = {
            (
                "[ аТЮХ ] j0kerpack ЭЦГі InfeKt-FM1ЃКЗТ Access Virus "
                "ЕФащФтФЃФтКЯГЩЦїЙЬМў"
            ): (
                "[ 新闻 ] j0kerpack 推出 InfeKt-FM1：仿 Access Virus "
                "的虚拟模拟合成器固件"
            ),
            (
                "[РВОЕ] Korg НЖіц phase8 companion ұајӯЖч"
                "УлТфЙ«№ЬАнУҰУГ"
            ): (
                "[新闻] Korg 推出 phase8 companion "
                "编辑器与音色管理应用"
            ),
            (
                "[–¬őŇ] IK Multimedia ∑Ę≤ľ iLoud Micro Monitor 2 "
                "ľŗŐż“ŰŌš"
            ): (
                "[新闻] IK Multimedia 发布 iLoud Micro Monitor 2 "
                "监听音箱"
            ),
            (
                "[–¬őŇ] Nektar ∑Ę≤ľ Impact GX49 Mk3 ”Ž "
                "GX61 Mk3 ľŁŇŐ"
            ): (
                "[新闻] Nektar 发布 Impact GX49 Mk3 与 "
                "GX61 Mk3 键盘"
            ),
        }
        for broken, expected in cases.items():
            with self.subTest(broken=broken):
                self.assertEqual(repair_mojibake(broken), expected)

    def test_short_category_prefix_is_removed_from_title(self) -> None:
        for title, expected in (
            ("[新闻] Korg 发布新合成器", "Korg 发布新合成器"),
            ("[ 资讯 ] 智能乐器新品", "智能乐器新品"),
            ("[视频] 合成器使用教程", "合成器使用教程"),
            ("【2026年11月】Korg 发布新固件", "【2026年11月】Korg 发布新固件"),
        ):
            with self.subTest(title=title):
                self.assertEqual(
                    strip_title_category_prefix(title),
                    expected,
                )

    def test_organ_title_can_be_recovered_from_correct_summary(self) -> None:
        title = "[ ���� ] IK Multimedia ���� iLoud Micro Monitor 2 ��������"
        summary = (
            "IK Multimedia 发布 iLoud Micro Monitor 2 监听音箱 "
            "4 天前 发布 IK Multimedia 的超紧凑型监听音箱..."
        )

        self.assertEqual(
            recover_title_from_summary(
                "中国电子琴信息网",
                title,
                summary,
            ),
            "IK Multimedia 发布 iLoud Micro Monitor 2 监听音箱",
        )


if __name__ == "__main__":
    unittest.main()
