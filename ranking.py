"""
资讯筛选、相关度计算和综合排行。

公开 RSS 和搜狗微信页面通常不提供真实阅读量，因此“热度”使用来源权重、
热词和类别信号做可解释的估算。相关度与时间衰减则是确定性计算，便于测试。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import (
    AI_HARDWARE_KEYWORDS,
    AI_KEYWORDS,
    DISPLAY_TIME_ZONE,
    MUSIC_HARDWARE_KEYWORDS,
    MUSIC_KEYWORDS,
    TECH_KEYWORDS,
)
from news_filter import find_matched_keywords


SOURCE_HEAT = {
    "Music Business Worldwide": 82,
    "MusicTech": 76,
    "MusicRadar": 74,
    "CDM": 72,
    "Synthtopia": 68,
    "Synthanatomy": 69,
    "Rekkerd": 67,
    "Attack Magazine": 70,
    "Matrixsynth": 66,
    "Guitar World": 70,
    "TechCrunch": 80,
    "IT之家24小时榜": 68,
    "36氪": 68,
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

PAGE_SIZE = 20
MAX_ITEMS_PER_SOURCE_PER_PAGE = 6


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
    title_zh = str(item.get("title_zh", ""))
    summary = str(item.get("summary", ""))
    combined = f"{title} {title_zh} {summary}"
    ai_matches = find_matched_keywords(combined, AI_KEYWORDS)
    music_matches = find_matched_keywords(combined, MUSIC_KEYWORDS)
    tech_matches = find_matched_keywords(combined, TECH_KEYWORDS)
    ai_hardware_matches = find_matched_keywords(
        combined,
        AI_HARDWARE_KEYWORDS,
    )
    music_hardware_matches = find_matched_keywords(
        combined,
        MUSIC_HARDWARE_KEYWORDS,
    )
    title_ai = find_matched_keywords(f"{title} {title_zh}", AI_KEYWORDS)
    title_music = find_matched_keywords(f"{title} {title_zh}", MUSIC_KEYWORDS)
    title_tech = find_matched_keywords(f"{title} {title_zh}", TECH_KEYWORDS)
    title_ai_hardware = find_matched_keywords(
        f"{title} {title_zh}",
        AI_HARDWARE_KEYWORDS,
    )
    title_music_hardware = find_matched_keywords(
        f"{title} {title_zh}",
        MUSIC_HARDWARE_KEYWORDS,
    )

    score = 15
    score += min(len(ai_matches), 3) * 10
    score += min(len(music_matches), 3) * 10
    score += min(len(tech_matches), 2) * 6
    score += min(len(ai_hardware_matches), 2) * 9
    score += min(len(music_hardware_matches), 2) * 9
    if ai_matches and music_matches:
        # AI + 音乐/乐器交叉命中是本项目的核心目标，给予明显加权。
        score += 25
    if (ai_hardware_matches or music_hardware_matches) and (
        ai_matches or music_matches
    ):
        # 硬件是当前项目的扩展方向，AI/音乐硬件获得额外排序权重。
        score += 15
    score += min(len(title_ai), 2) * 8
    score += min(len(title_music), 2) * 8
    score += min(len(title_tech), 2) * 5
    score += min(len(title_ai_hardware), 2) * 6
    score += min(len(title_music_hardware), 2) * 6
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


def _search_term_matches(searchable: str, term: str) -> bool:
    """
    判断一个搜索词是否命中。

    中文按包含匹配；英文按“词语开头”匹配，既能让 Git 命中 GitHub，
    又不会让 Git 错误命中 digital 中间的 git。含有分号的多个词仍由
    调用方拆分，不含分号时整个输入作为一个短语。
    """

    normalized = term.casefold().strip()
    if not normalized:
        return True
    if re.search(r"[\u3400-\u9fff]", normalized):
        return normalized in searchable

    # 英文短语允许词与词之间出现一个或多个空白，但第一个词必须从
    # 单词边界开始，避免把 digital 中间的 git 当成独立关键词。
    words = [re.escape(word) for word in normalized.split()]
    phrase_pattern = r"\s+".join(words)
    pattern = rf"(?<![a-z0-9]){phrase_pattern}"
    return re.search(pattern, searchable) is not None


def _source_group(item: dict[str, Any]) -> str:
    """把同一批 GitHub 仓库归为一个来源组，便于控制首页来源比例。"""

    source = str(item.get("source", "")).strip()
    category = str(item.get("category", "")).strip()
    if category == "搜狗微信":
        return "搜狗微信"
    if source.casefold().startswith("github"):
        return "GitHub"
    return source or "未知来源"


def balance_source_diversity(
    items: list[dict[str, Any]],
    *,
    page_size: int = PAGE_SIZE,
    max_per_source: int = MAX_ITEMS_PER_SOURCE_PER_PAGE,
) -> list[dict[str, Any]]:
    """
    为每一页设置同来源数量上限，避免一个来源占满整页。

    输入已经按发布时间排序；每页仍保持时间倒序，但会选择不同来源填充，
    被推迟的条目进入后续页面。
    """

    remaining = list(items)
    balanced: list[dict[str, Any]] = []
    while remaining:
        selected: list[dict[str, Any]] = []
        deferred: list[dict[str, Any]] = []
        consumed = 0
        counts: dict[str, int] = {}

        for index, item in enumerate(remaining):
            if len(selected) >= page_size:
                consumed = index
                break
            group = _source_group(item)
            if counts.get(group, 0) < max_per_source:
                selected.append(item)
                counts[group] = counts.get(group, 0) + 1
            else:
                deferred.append(item)
        else:
            consumed = len(remaining)

        fill_count = min(page_size - len(selected), len(deferred))
        selected.extend(deferred[:fill_count])
        balanced.extend(selected)
        remaining = deferred[fill_count:] + remaining[consumed:]

    return balanced


def filter_and_rank_news(
    items: Iterable[dict[str, Any]],
    *,
    days: int = 3,
    keyword: str = "",
    specific_date: str = "",
    content_kind: str = "all",
    sort_by: str = "time",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    按时间范围和关键词过滤，再计算综合排行。

    specific_date 为 YYYY-MM-DD 时只筛选本地时区的那一天，并忽略 days。
    content_kind 可选 all、hardware、software；软硬结合资讯会同时出现在
    后两个筛选中。
    sort_by 可选 time、heat、relevance；默认按发布时间倒序。
    days=0 表示全部时间。关键词使用不区分大小写的包含匹配；
    多个空格分隔的词必须同时出现。
    """

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    selected_kind = content_kind.strip().casefold()
    if selected_kind not in {"all", "hardware", "software"}:
        selected_kind = "all"
    selected_sort = sort_by.strip().casefold()
    if selected_sort not in {"time", "heat", "relevance"}:
        selected_sort = "time"
    # 分号是唯一的多词分隔符；没有分号时整个输入只作为一个搜索词。
    search_terms = [
        term.strip().casefold()
        for term in re.split(r"[;；]", keyword)
        if term.strip()
    ]
    ranked_items: list[dict[str, Any]] = []
    target_date: date | None = None
    if specific_date:
        try:
            target_date = date.fromisoformat(specific_date)
        except ValueError:
            target_date = None
    try:
        display_time_zone = ZoneInfo(DISPLAY_TIME_ZONE)
    except ZoneInfoNotFoundError:
        display_time_zone = ZoneInfo("Asia/Shanghai")
    current_local_date = current_time.astimezone(display_time_zone).date()
    range_start_date = (
        current_local_date - timedelta(days=days - 1)
        if days > 0
        else None
    )

    for original_item in items:
        item = dict(original_item)
        publish_time = _parse_utc(item.get("publish_time"))
        if target_date is not None:
            if (
                publish_time is None
                or publish_time.astimezone(display_time_zone).date()
                != target_date
            ):
                continue
        elif range_start_date is not None:
            if publish_time is None:
                continue
            publish_date = publish_time.astimezone(display_time_zone).date()
            if not (range_start_date <= publish_date <= current_local_date):
                continue

        searchable = (
            f"{item.get('title', '')} {item.get('title_zh', '')} "
            f"{item.get('summary', '')} {item.get('source', '')}".casefold()
        )
        if (
            selected_kind == "hardware"
            and not bool(item.get("is_hardware"))
        ):
            continue
        if (
            selected_kind == "software"
            and not bool(item.get("is_software"))
        ):
            continue
        if search_terms and not any(
            _search_term_matches(searchable, term)
            for term in search_terms
        ):
            continue

        relevance = _relevance_score(item)
        heat = _heat_score(item)
        recency = _recency_score(item, current_time)
        item["relevance_score"] = relevance
        item["heat_score"] = heat
        item["recency_score"] = recency
        item["is_ai_music_cross"] = bool(
            find_matched_keywords(searchable, AI_KEYWORDS)
            and find_matched_keywords(searchable, MUSIC_KEYWORDS)
        )
        item["rank_score"] = round(
            relevance * 0.50 + heat * 0.30 + recency * 0.20,
            1,
        )
        ranked_items.append(item)

    if selected_sort == "heat":
        ranked_items.sort(
            key=lambda item: (
                item["heat_score"],
                item.get("publish_time") or "",
                item["rank_score"],
            ),
            reverse=True,
        )
    elif selected_sort == "relevance":
        ranked_items.sort(
            key=lambda item: (
                item["is_ai_music_cross"],
                item["relevance_score"],
                item.get("publish_time") or "",
                item["rank_score"],
            ),
            reverse=True,
        )
    else:
        ranked_items.sort(
            key=lambda item: (
                item.get("publish_time") or "",
                item["rank_score"],
            ),
            reverse=True,
        )
    ranked_items = balance_source_diversity(ranked_items)
    for rank, item in enumerate(ranked_items, start=1):
        item["rank"] = rank
    return ranked_items
