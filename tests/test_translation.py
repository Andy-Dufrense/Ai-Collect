"""自动翻译逻辑测试，不访问真实翻译接口。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

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


class FakeGoogleResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> list:
        return [[["备用接口中文标题", "fallback title", None, None]]]


class FallbackSession:
    def get(self, url: str, **_kwargs):
        if "mymemory" in url:
            raise requests.ConnectionError("quota exceeded")
        return FakeGoogleResponse()


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

    def test_google_fallback_is_used_when_mymemory_fails(self) -> None:
        translated = translate_title(
            "Fallback title for translation",
            session=FallbackSession(),  # type: ignore[arg-type]
        )
        self.assertEqual(translated, "备用接口中文标题")

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

    def test_translation_stops_at_time_budget(self) -> None:
        items = [
            {
                "title": "New AI guitar tool released",
                "link": "https://example.com/tool",
                "dedupe_key": "tool-budget",
            }
        ]
        with patch("translation.translate_title") as translate_mock:
            translated_count = translate_items(
                items,
                existing_items=[],
                time_budget_seconds=0,
            )

        self.assertEqual(translated_count, 0)
        translate_mock.assert_not_called()

    def test_github_title_translates_only_payload_and_keeps_prefix(self) -> None:
        items = [
            {
                "title": "GitHub · AI+音乐新项目：New AI guitar tool released",
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
            "GitHub · AI+音乐新项目：AI 吉他工具正式发布",
        )
        translate_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
