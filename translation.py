"""
英文资讯标题自动翻译。

GitHub Pages 是静态站点，因此翻译在 GitHub Actions 生成 JSON 时完成。
使用 MyMemory 免费接口，并通过已有 title_zh 做持久化缓存，避免重复请求。
"""

from __future__ import annotations

import html
import logging
import os
import re
import time
from collections.abc import Iterable, Mapping
from typing import Any

import requests


MYMEMORY_URL = "https://api.mymemory.translated.net/get"
GOOGLE_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
TRANSLATION_ENABLED = os.getenv("TRANSLATION_ENABLED", "1").casefold() not in {
    "0",
    "false",
    "no",
    "off",
}
MAX_TRANSLATIONS_PER_RUN = 300
LOGGER = logging.getLogger(__name__)


def _translation_time_budget() -> float:
    """读取单轮翻译时间预算；异常配置回退到 10 分钟。"""

    raw_value = os.getenv("TRANSLATION_TIME_BUDGET_SECONDS", "").strip()
    if not raw_value:
        return 600.0
    try:
        value = float(raw_value)
    except ValueError:
        return 600.0
    return max(30.0, value)


TRANSLATION_TIME_BUDGET_SECONDS = _translation_time_budget()
GITHUB_TITLE_PREFIXES = (
    "GitHub · AI+音乐新项目：",
    "GitHub · AI+音乐新功能：",
    "GitHub · AI+音乐新发布：",
    # 兼容旧数据库中尚未清理的历史标题。
    "GitHub - 新发布：",
    "GitHub - 新更新：",
)


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
        translated = _translate_with_mymemory(http, text)
        if translated:
            return translated
        return _translate_with_google(http, text)
    finally:
        if owns_session:
            http.close()


def _translate_with_mymemory(
    session: requests.Session,
    text: str,
) -> str | None:
    """使用 MyMemory 免费翻译接口。"""

    try:
        response = session.get(
            MYMEMORY_URL,
            params={"q": text, "langpair": "en|zh-CN"},
            headers={"User-Agent": "AI-Music-Collector/1.0"},
            timeout=(4.0, 10.0),
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


def _translate_with_google(
    session: requests.Session,
    text: str,
) -> str | None:
    """
    MyMemory 限流时使用 Google 公共翻译网页接口作为备用。

    这里只调用无需账号的普通翻译端点，不涉及登录或绕过验证。
    """

    try:
        response = session.get(
            GOOGLE_TRANSLATE_URL,
            params={
                "client": "gtx",
                "sl": "en",
                "tl": "zh-CN",
                "dt": "t",
                "q": text,
            },
            headers={"User-Agent": "AI-Music-Collector/1.0"},
            timeout=(4.0, 12.0),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            return None
        segments = payload[0]
        if not isinstance(segments, list):
            return None
        translated = "".join(
            str(segment[0])
            for segment in segments
            if isinstance(segment, list) and segment
        ).strip()
        translated = html.unescape(translated)
        if not translated or translated.casefold() == text.casefold():
            return None
        return translated
    except (requests.RequestException, ValueError, TypeError):
        return None


def is_translatable_title(text: str) -> bool:
    """避免把纯数字、链接或极短英文产品缩写送去翻译。"""

    return is_probably_english(text) and len(text) <= 400


def is_title_displayable(item: Mapping[str, Any]) -> bool:
    """中文标题或翻译成功的英文标题才允许展示。"""

    title = str(item.get("title", "")).strip()
    title_zh = str(item.get("title_zh") or "").strip()
    if not is_probably_english(title):
        return True
    return bool(title_zh and title_zh.casefold() != "none")


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
    max_translations: int = MAX_TRANSLATIONS_PER_RUN,
    time_budget_seconds: float | None = None,
) -> int:
    """
    为英文标题增加 title_zh 字段，返回本轮新翻译数量。
    """

    should_translate = TRANSLATION_ENABLED if enabled is None else enabled
    if not should_translate:
        return 0

    cache = load_translation_cache(existing_items)
    translated_count = 0
    attempted_count = 0
    budget = (
        TRANSLATION_TIME_BUDGET_SECONDS
        if time_budget_seconds is None
        else max(0.0, time_budget_seconds)
    )
    deadline = time.monotonic() + budget
    budget_reported = False
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
            if translated_count >= max(0, max_translations):
                break
            if time.monotonic() >= deadline:
                if not budget_reported:
                    LOGGER.warning(
                        "翻译达到 %.0f 秒时间预算，剩余标题留待下一轮处理",
                        budget,
                    )
                    budget_reported = True
                break

            # GitHub 标题带有中文分类前缀，不能把整个标题直接送翻译。
            # 只翻译冒号后的英文简介，并保留固定的“GitHub - 新发布/新更新”
            # 前缀，方便用户始终用 Git/GitHub 搜索到这些内容。
            github_prefix = ""
            github_payload = title
            for prefix in GITHUB_TITLE_PREFIXES:
                if title.startswith(prefix):
                    github_prefix = prefix
                    github_payload = title[len(prefix):].strip()
                    break
            if github_prefix:
                attempted_count += 1
                translated = translate_title(
                    github_payload,
                    session=session,
                )
                if translated:
                    item["title_zh"] = github_prefix + translated
                    cache[key] = item["title_zh"]
                    translated_count += 1
                    time.sleep(0.15)
                    if translated_count == 1 or translated_count % 10 == 0:
                        LOGGER.info("英文标题翻译进度：%d 条", translated_count)
                continue

            if not is_probably_english(title):
                continue

            attempted_count += 1
            translated = translate_title(title, session=session)
            if translated:
                item["title_zh"] = translated
                cache[key] = translated
                translated_count += 1
                time.sleep(0.15)
                if translated_count == 1 or translated_count % 10 == 0:
                    LOGGER.info("英文标题翻译进度：%d 条", translated_count)
    if attempted_count and translated_count == 0:
        LOGGER.warning(
            "尝试翻译 %d 条，但所有翻译接口均未返回可用结果",
            attempted_count,
        )
    return translated_count
