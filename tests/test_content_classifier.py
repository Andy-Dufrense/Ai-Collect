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

    def test_physical_type_in_summary_recovers_review_articles(self) -> None:
        """产品名标题没有硬件实体词时，简介中的明确设备类型仍可分类。"""

        for title, summary in (
            (
                "Shure MV7i review",
                "A broadcast microphone with a built-in audio interface.",
            ),
            (
                "Auriteq Flow review",
                "A compact and configurable DAW controller.",
            ),
            (
                "Yamaha expands its keyboard lineup",
                "The new CK76 stage keyboard is now available.",
            ),
        ):
            with self.subTest(title=title):
                is_hardware, _is_software = classify_content_flags(
                    title,
                    summary,
                    category="音乐科技",
                    source="MusicRadar",
                )
                self.assertTrue(is_hardware)

    def test_summary_hardware_compatibility_does_not_override_plugin(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "OMEGA-50 software synthesizer (VST3/AU)",
            "Works with any audio interface and DAW controller.",
            category="音乐科技",
            source="Rekkerd",
        )
        self.assertFalse(is_hardware)
        self.assertTrue(is_software)

    def test_instrument_release_is_hardware_but_artist_story_is_not(self) -> None:
        for title, summary in (
            (
                "Gibson launches the new Les Paul Standard guitar",
                "A new electric guitar for studio and stage players.",
            ),
            (
                "Yamaha releases a new digital piano",
                "The piano includes a graded hammer-action keyboard.",
            ),
            (
                "Elixir announces new acoustic guitar strings",
                "A coated guitar string set for acoustic instruments.",
            ),
        ):
            with self.subTest(title=title):
                is_hardware, _is_software = classify_content_flags(
                    title,
                    summary,
                    category="音乐科技",
                    source="Guitar World",
                )
                self.assertTrue(is_hardware)

        is_hardware, _is_software = classify_content_flags(
            "Why this guitarist still loves a vintage guitar",
            "An artist interview about his favourite instrument.",
            category="音乐科技",
            source="Guitar World",
        )
        self.assertFalse(is_hardware)

    def test_software_guitar_instrument_is_not_hardware(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "New acoustic guitar virtual instrument plugin released",
            "A VST3 guitar sample library for DAWs.",
            category="音乐科技",
            source="Rekkerd",
        )
        self.assertFalse(is_hardware)
        self.assertTrue(is_software)

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

    def test_plugins_and_mobile_or_web_tools_are_software(self) -> None:
        for title, summary in (
            (
                "4 new Sinevibes oscillator plugins for Korg NTS-1 mkII",
                "VST3 and AU plugins.",
            ),
            (
                "Photophore 2 returns to iOS",
                "A software synthesizer app.",
            ),
            (
                "SynthMaker modular synthesis environment for your browser",
                "Runs in Safari and Chrome.",
            ),
            (
                "MIDI velocity Transformer for piano transcription",
                "A machine-learning research model.",
            ),
        ):
            with self.subTest(title=title):
                category = (
                    "AI音频研究"
                    if "Transformer" in title
                    else "音乐科技"
                )
                is_hardware, is_software = classify_content_flags(
                    title,
                    summary,
                    category=category,
                    source="Synthanatomy",
                )
                self.assertFalse(is_hardware)
                self.assertTrue(is_software)

    def test_summary_plugin_signal_overrides_ambiguous_synth_title(self) -> None:
        for title, summary in (
            (
                "Imaginando FRMS 2 synthesizer gets a wavetable upgrade",
                "A major upgrade to its granular FM synthesizer plugin.",
            ),
            (
                "BackLab Audio updates Filament synth to v1.1",
                "Available for Windows and macOS as VST3 and AU.",
            ),
            (
                "Decent Sampler makes instrument building easier",
                "The popular free sampler plugin adds a preset editor.",
            ),
            (
                "Vitaleon brings Vital synth to Akai MPC",
                "A fork of the free wavetable synthesizer.",
            ),
        ):
            with self.subTest(title=title):
                is_hardware, is_software = classify_content_flags(
                    title,
                    summary,
                    category="音乐科技",
                    source="Synthanatomy",
                )
                self.assertFalse(is_hardware)
                self.assertTrue(is_software)

    def test_hardware_inspired_software_update_is_not_hardware(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "discoDSP updates OB-Xd with hardware-inspired features",
            "A major software update.",
            category="音乐科技",
            source="Synthtopia",
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

    def test_source_focus_helps_hardware_query_without_keyword(self) -> None:
        """精准硬件搜索词可补足标题中缺失的“硬件/设备”实体词。"""

        is_hardware, is_software = classify_content_flags(
            "Nova 智能吉他在中国发布",
            "面向吉他学习者的新一代产品。",
            category="国内科技",
            source="百度新闻：智能吉他",
            focus="hardware",
        )
        self.assertTrue(is_hardware)
        self.assertFalse(is_software)

    def test_source_focus_does_not_override_explicit_software(self) -> None:
        is_hardware, is_software = classify_content_flags(
            "Nova 吉他音源插件更新",
            "适用于 DAW 的 VST3 插件。",
            category="国内科技",
            source="百度新闻：智能吉他",
            focus="hardware",
        )
        self.assertFalse(is_hardware)
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
            "机器人公司创始人访谈：具身智能如何落地",
            "CoRL 2026 演讲实录：机器人需要什么 AI",
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
