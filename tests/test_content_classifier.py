"""硬件/软件资讯分类测试。"""

from __future__ import annotations

import unittest

from content_classifier import classify_content_flags


class ContentClassifierTests(unittest.TestCase):
    def test_hardware_product_is_hardware_only(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "Magerit Laniakea Pro polyphonic Synthesizer",
            "A standalone hardware synthesizer and Eurorack module.",
            category="音乐科技",
            source="Synthanatomy",
        )
        self.assertTrue(is_hardware)
        self.assertFalse(is_software)

    def test_audio_plugin_is_software_only(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "DGR Digital Degrader effect plugin (VST3/AU)",
            "A new audio plugin for DAWs.",
            category="音乐科技",
            source="Rekkerd",
        )
        self.assertFalse(is_hardware)
        self.assertTrue(is_software)

    def test_hardware_with_companion_app_is_both(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "MIDI controller launch adds companion app workflow",
            "A hardware controller and software app update.",
            category="音乐科技",
            source="MusicRadar",
        )
        self.assertTrue(is_hardware)
        self.assertTrue(is_software)

    def test_ai_industry_article_without_product_is_unclassified(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "OpenAI CEO discusses the next stage of AI",
            "Company leadership and industry commentary.",
            category="国际科技",
            source="TechCrunch",
        )
        self.assertFalse(is_hardware)
        self.assertFalse(is_software)

    def test_github_update_is_software(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "GitHub - 新更新：Improve music generation pipeline",
            "最新代码提交。",
            category="AI音频开发",
            source="GitHub · example/music",
        )
        self.assertFalse(is_hardware)
        self.assertTrue(is_software)


if __name__ == "__main__":
    unittest.main()
