"""
“AI + 音乐”资讯过滤器。

系统接受 AI、音乐或乐器任一领域的内容；同时命中多个领域时，由排名模块
提高相关度。英文关键词按完整单词匹配，避免把 “daily” 中的 “ai” 误判成
人工智能资讯；中文关键词直接进行包含匹配。所有比较均忽略大小写。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from config import AI_KEYWORDS, MUSIC_KEYWORDS


def _normalize_text(value: str) -> str:
    """统一大小写并压缩多余空白，减少无意义的匹配差异。"""

    return re.sub(r"\s+", " ", value.casefold()).strip()


def _contains_keyword(text: str, keyword: str) -> bool:
    """
    判断文本是否包含指定关键词。

    对纯英文/数字关键词使用边界检查。例如：
    - “AI 音乐”和“AI音乐”会匹配 ai；
    - “daily news”不会因为里面恰好有 ai 两个字母而误匹配。
    中文关键词没有空格边界，因此直接使用普通子串匹配。
    """

    normalized_keyword = keyword.casefold()
    if re.fullmatch(r"[a-z0-9]+", normalized_keyword):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return normalized_keyword in text


def find_matched_keywords(
    text: str,
    keywords: Iterable[str],
) -> tuple[str, ...]:
    """返回文本实际命中的关键词，便于调试过滤结果。"""

    normalized_text = _normalize_text(text)
    return tuple(
        keyword
        for keyword in keywords
        if _contains_keyword(normalized_text, keyword)
    )


def is_relevant_news(
    *text_parts: str,
) -> bool:
    """
    判断一条资讯是否属于 AI、音乐或乐器相关领域。

    传入的多个文本片段（通常是标题和简介）会先合并再判断。
    标题命中了 AI、简介命中了音乐，同样算同时满足条件。
    两类关键词采用并集，只要命中 AI 或音乐/乐器之一即可收录；
    同时命中两类的文章会在 ranking.py 中获得更高的相关度加权。
    """

    combined_text = _normalize_text(" ".join(part for part in text_parts if part))
    has_ai_keyword = bool(find_matched_keywords(combined_text, AI_KEYWORDS))
    has_music_keyword = bool(find_matched_keywords(combined_text, MUSIC_KEYWORDS))
    return has_ai_keyword or has_music_keyword
