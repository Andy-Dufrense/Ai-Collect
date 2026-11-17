"""
资讯筛选、相关度计算和综合排行。

公开 RSS 和搜狗微信页面通常不提供真实阅读量，因此“热度”使用来源权重、
热词和类别信号做可解释的估算。相关度与时间衰减则是确定性计算，便于测试。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from config import AI_KEYWORDS, MUSIC_KEYWORDS
from news_filter import find_matched_keywords


SOURCE_HEAT = {
    "Music Business Worldwide": 82,
    "MusicTech": 76,
    "MusicRadar": 74,
    "CDM": 72,
    "Synthtopia": 68,
    "Guitar World": 70,
    "TechCrunch": 80,
    "IT之家24小时榜": 68,
    "爱范儿": 66,
}

CATEGORY_HEAT = {
    "音乐科技": 12,
    "微信公众号": 9,
    "搜狗微信": 7,
    "国内科技": 6,
    "国际科技": 8,
    "微信视频号": 8,
    "抖音": 10,
}

HOT_TERMS = (
    "发布",
    "推出",
    "融资",
    "收购",
    "爆火",
    "新品",
    "上线",
    "突破",
    "裁员",
    "诉讼",
    "launch",
    "announce",
    "unveil",
    "funding",
    "acquisition",
    "viral",
    "breakthrough",
    "first",
)


def _parse_utc(value: str | None) -> datetime | None:
    """解析数据库中的 ISO 时间；无时间或格式异常时返回 None。"""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _relevance_score(item: dict[str, Any]) -> int:
    """根据关键词覆盖和标题命中位置计算 0-100 的相关度。"""

    title = str(item.get("title", ""))
    summary = str(item.get("summary", ""))
    combined = f"{title} {summary}"
    ai_matches = find_matched_keywords(combined, AI_KEYWORDS)
    music_matches = find_matched_keywords(combined, MUSIC_KEYWORDS)
    title_ai = find_matched_keywords(title, AI_KEYWORDS)
    title_music = find_matched_keywords(title, MUSIC_KEYWORDS)

    score = 15
    score += min(len(ai_matches), 3) * 10
    score += min(len(music_matches), 3) * 10
    if ai_matches and music_matches:
        # AI + 音乐/乐器交叉命中是本项目的核心目标，给予明显加权。
        score += 25
    score += min(len(title_ai), 2) * 8
    score += min(len(title_music), 2) * 8
    return min(100, score)


def _heat_score(item: dict[str, Any]) -> int:
    """根据来源权重、类别和新闻热词估算热度。"""

    source = str(item.get("source", ""))
    category = str(item.get("category", ""))
    text = f"{item.get('title', '')} {item.get('summary', '')}".casefold()
    score = SOURCE_HEAT.get(source, 55) + CATEGORY_HEAT.get(category, 0)
    score += sum(4 for term in HOT_TERMS if term.casefold() in text)
    return min(100, score)


def _recency_score(item: dict[str, Any], now: datetime) -> int:
    """72 小时内线性衰减，越新分数越高。"""

    publish_time = _parse_utc(item.get("publish_time"))
    if publish_time is None:
        return 0
    age_hours = max(0.0, (now - publish_time).total_seconds() / 3600)
    return max(0, round(100 * (1 - age_hours / 72)))


def filter_and_rank_news(
    items: Iterable[dict[str, Any]],
    *,
    days: int = 3,
    keyword: str = "",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    按时间范围和关键词过滤，再计算综合排行。

    days=0 表示全部时间。关键词使用不区分大小写的包含匹配；
    多个空格分隔的词必须同时出现。
    """

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = (
        current_time.timestamp() - days * 86400 if days > 0 else None
    )
    search_terms = [term.casefold() for term in keyword.split() if term.strip()]
    ranked_items: list[dict[str, Any]] = []

    for original_item in items:
        item = dict(original_item)
        publish_time = _parse_utc(item.get("publish_time"))
        if cutoff is not None:
            if publish_time is None or publish_time.timestamp() < cutoff:
                continue

        searchable = (
            f"{item.get('title', '')} {item.get('summary', '')}".casefold()
        )
        if any(term not in searchable for term in search_terms):
            continue

        relevance = _relevance_score(item)
        heat = _heat_score(item)
        recency = _recency_score(item, current_time)
        item["relevance_score"] = relevance
        item["heat_score"] = heat
        item["recency_score"] = recency
        item["rank_score"] = round(
            relevance * 0.50 + heat * 0.30 + recency * 0.20,
            1,
        )
        ranked_items.append(item)

    ranked_items.sort(
        key=lambda item: (
            item["rank_score"],
            item.get("publish_time") or "",
        ),
        reverse=True,
    )
    for rank, item in enumerate(ranked_items, start=1):
        item["rank"] = rank
    return ranked_items
