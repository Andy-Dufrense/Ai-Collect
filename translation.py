"""
英文资讯标题自动翻译。

GitHub Pages 是静态站点，因此翻译在 GitHub Actions 生成 JSON 时完成。
使用 MyMemory 免费接口，并通过已有 title_zh 做持久化缓存，避免重复请求。
"""

from __future__ import annotations

import html
import os
import re
import time
from collections.abc import Iterable, Mapping
from typing import Any

import requests


MYMEMORY_URL = "https://api.mymemory.translated.net/get"
TRANSLATION_ENABLED = os.getenv("TRANSLATION_ENABLED", "1").casefold() not in {
    "0",
    "false",
    "no",
    "off",
}
MAX_TRANSLATIONS_PER_RUN = 60


def is_probably_english(text: str) -> bool:
    """只翻译以英文为主、且中文很少的标题。"""

    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return latin_count >= 10 and cjk_count < 2


def translate_title(
    text: str,
    *,
    session: requests.Session | None = None,
) -> str | None:
    """
    把一个英文标题翻译成简体中文。

    网络失败、接口限流或返回异常时返回 None，由调用方保留英文原文。
    """

    if not is_translatable_title(text):
        return None

    owns_session = session is None
    http = session or requests.Session()
    http.trust_env = False
    try:
        response = http.get(
            MYMEMORY_URL,
            params={"q": text, "langpair": "en|zh-CN"},
            headers={"User-Agent": "AI-Music-Collector/1.0"},
            timeout=(4.0, 12.0),
        )
        response.raise_for_status()
        payload = response.json()
        translated = str(
            payload.get("responseData", {}).get("translatedText", "")
        ).strip()
        translated = html.unescape(translated)
        if (
            not translated
            or "MYMEMORY WARNING" in translated.upper()
            or translated.casefold() == text.casefold()
        ):
            return None
        return translated
    except (requests.RequestException, ValueError, TypeError):
        return None
    finally:
        if owns_session:
            http.close()


def is_translatable_title(text: str) -> bool:
    """避免把纯数字、链接或极短英文产品缩写送去翻译。"""

    return is_probably_english(text) and len(text) <= 400


def load_translation_cache(
    existing_items: Iterable[Mapping[str, Any]],
) -> dict[str, str]:
    """用稳定去重键缓存已有中文标题。"""

    cache: dict[str, str] = {}
    for item in existing_items:
        key = str(item.get("dedupe_key") or item.get("link") or "")
        translated = str(item.get("title_zh") or "").strip()
        if key and translated and translated.casefold() != "none":
            cache[key] = translated
    return cache


def translate_items(
    items: list[dict[str, Any]],
    *,
    existing_items: Iterable[Mapping[str, Any]] = (),
    enabled: bool | None = None,
) -> int:
    """
    为英文标题增加 title_zh 字段，返回本轮新翻译数量。
    """

    should_translate = TRANSLATION_ENABLED if enabled is None else enabled
    if not should_translate:
        return 0

    cache = load_translation_cache(existing_items)
    translated_count = 0
    with requests.Session() as session:
        session.trust_env = False
        for item in items:
            title = str(item.get("title", "")).strip()
            key = str(item.get("dedupe_key") or item.get("link") or "")
            if str(item.get("title_zh") or "").strip().casefold() == "none":
                item["title_zh"] = ""
            if not title or not key:
                continue
            if key in cache:
                item["title_zh"] = cache[key]
                continue
            if translated_count >= MAX_TRANSLATIONS_PER_RUN:
                break
            if not is_probably_english(title):
                continue

            translated = translate_title(title, session=session)
            if translated:
                item["title_zh"] = translated
                cache[key] = translated
                translated_count += 1
                time.sleep(0.15)
    return translated_count
