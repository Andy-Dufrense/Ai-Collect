"""文本乱码修复的离线测试。"""

from __future__ import annotations

import unittest

from text_utils import repair_mojibake


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


if __name__ == "__main__":
    unittest.main()
