"""自动翻译逻辑测试，不访问真实翻译接口。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from translation import (
    is_probably_english,
    is_title_displayable,
    translate_items,
    translate_title,
)


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "responseData": {
                "translatedText": "AI 吉他工具正式发布",
            }
        }


class FakeSession:
    def get(self, *_args, **_kwargs) -> FakeResponse:
        return FakeResponse()


class TranslationTests(unittest.TestCase):
    def test_english_title_is_detected(self) -> None:
        self.assertTrue(is_probably_english("New AI guitar tool released"))
        self.assertFalse(is_probably_english("AI 吉他工具正式发布"))

    def test_title_translation(self) -> None:
        translated = translate_title(
            "New AI guitar tool released",
            session=FakeSession(),  # type: ignore[arg-type]
        )
        self.assertEqual(translated, "AI 吉他工具正式发布")

    def test_translation_cache_avoids_repeated_request(self) -> None:
        items = [
            {
                "title": "New AI guitar tool released",
                "link": "https://example.com/tool",
                "dedupe_key": "tool",
            }
        ]
        existing = [
            {
                "link": "https://example.com/tool",
                "dedupe_key": "tool",
                "title_zh": "缓存的中文标题",
            }
        ]
        with patch("translation.translate_title") as translate_mock:
            translated_count = translate_items(
                items,
                existing_items=existing,
            )
        self.assertEqual(translated_count, 0)
        self.assertEqual(items[0]["title_zh"], "缓存的中文标题")
        translate_mock.assert_not_called()

    def test_untranslated_english_title_is_hidden(self) -> None:
        self.assertFalse(
            is_title_displayable(
                {"title": "New AI music plugin released"}
            )
        )
        self.assertTrue(
            is_title_displayable(
                {
                    "title": "New AI music plugin released",
                    "title_zh": "全新 AI 音乐插件发布",
                }
            )
        )
        self.assertTrue(is_title_displayable({"title": "AI 音乐工具更新"}))

    def test_github_title_translates_only_payload_and_keeps_prefix(self) -> None:
        items = [
            {
                "title": "GitHub - 新发布：New AI guitar tool released",
                "link": "https://github.com/example/tool",
                "dedupe_key": "github-tool",
            }
        ]
        with patch(
            "translation.translate_title",
            return_value="AI 吉他工具正式发布",
        ) as translate_mock:
            translated_count = translate_items(
                items,
                existing_items=[],
            )
        self.assertEqual(translated_count, 1)
        self.assertEqual(
            items[0]["title_zh"],
            "GitHub - 新发布：AI 吉他工具正式发布",
        )
        translate_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
