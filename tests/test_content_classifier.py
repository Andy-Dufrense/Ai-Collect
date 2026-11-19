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

    def test_hardware_dsp_and_hard_synth_are_hardware(self) -> None:
        for title in (
            "Tantrum Audio NEXUS compact hardware DSP processor",
            "The LARYNX is a new hard synth from AnalogFX",
            "Synthesizers.com introduces a new modular system",
            "英伟达发布 AI 服务器、GPU 与推理加速卡",
            "国产智能终端搭载新一代 NPU 芯片",
        ):
            with self.subTest(title=title):
                is_hardware, is_software = classify_content_flags(
                    title,
                    "",
                    category="音乐科技",
                    source="MusicTech",
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

    def test_software_synthesizer_is_not_misclassified_as_hardware(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "Rave Generation releases OMEGA-50 software synthesizer (VST3/AU)",
            "A virtual instrument plugin.",
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

    def test_ai_music_video_is_software(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "SUNO 发布 AI MV：音乐视频重磅上线",
            "通过提示词生成完整音乐视频。",
            category="搜狗微信",
            source="搜狗微信",
        )
        self.assertFalse(is_hardware)
        self.assertTrue(is_software)

    def test_business_opinion_and_roundup_are_not_hardware(self) -> None:
        for title in (
            "小米雷军：AI+ 手机与机器人有很大想象空间",
            "英伟达安抚机器人生态伙伴，投资不会急刹车",
            "极客早知道：家用机器人或将迎来技术突破",
        ):
            with self.subTest(title=title):
                is_hardware, _is_software = classify_content_flags(
                    title,
                    "文章主体是人物观点和行业汇总。",
                    category="国内科技",
                    source="IT之家24小时榜",
                )
                self.assertFalse(is_hardware)


if __name__ == "__main__":
    unittest.main()
