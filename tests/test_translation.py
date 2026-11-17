"""自动翻译逻辑测试，不访问真实翻译接口。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from translation import is_probably_english, translate_items, translate_title


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


if __name__ == "__main__":
    unittest.main()
