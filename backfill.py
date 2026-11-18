"""
基于真实 date_gmt 的音乐科技历史归档回填。

当前使用实测可访问的 Synthtopia 和 MusicTech WordPress REST API。只保存
接口明确返回的发布时间，缺失时间的数据不会进入历史排行。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from bs4 import BeautifulSoup

from config import DISPLAY_TIME_ZONE, ON_DEMAND_DATE_BACKFILL_SECONDS
from database import (
    get_all_news,
    get_meta_value,
    initialize_database,
    purge_news_outside_retention,
    save_news_items,
    set_meta_value,
)
from news_filter import is_relevant_news
from translation import translate_items


LOGGER = logging.getLogger(__name__)

ARCHIVE_SOURCES = (
    {
        "source": "Synthtopia",
        "api": "https://www.synthtopia.com/wp-json/wp/v2/posts",
        "category": "音乐科技",
    },
    {
        "source": "MusicTech",
        "api": "https://musictech.com/wp-json/wp/v2/posts",
        "category": "音乐科技",
    },
    {
        "source": "Synthanatomy",
        "api": "https://www.synthanatomy.com/wp-json/wp/v2/posts",
        "category": "音乐科技",
    },
    {
        "source": "Rekkerd",
        "api": "https://rekkerd.org/wp-json/wp/v2/posts",
        "category": "音乐科技",
    },
    {
        "source": "Music Business Worldwide",
        "api": "https://www.musicbusinessworldwide.com/wp-json/wp/v2/posts",
        "category": "音乐科技",
    },
    {
        "source": "爱范儿",
        "api": "https://www.ifanr.com/wp-json/wp/v2/posts",
        "category": "国内科技",
    },
    {
        "source": "TechCrunch",
        "api": "https://techcrunch.com/wp-json/wp/v2/posts",
        "category": "国际科技",
    },
)


@dataclass
class DateBackfillResult:
    target_date: str
    matched_entries: int
    new_count: int
    skipped: bool = False


def _display_today() -> date:
    try:
        zone = ZoneInfo(DISPLAY_TIME_ZONE)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Asia/Shanghai")
    return datetime.now(timezone.utc).astimezone(zone).date()


def _clean_html(value: str) -> str:
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return " ".join(text.split())


def _convert_article(
    row: dict[str, Any],
    *,
    source: str,
    category: str,
) -> dict[str, str | None] | None:
    """转换一篇归档文章，严格使用 date_gmt，不伪造发布时间。"""

    date_gmt = str(row.get("date_gmt") or "").strip()
    if not date_gmt:
        return None
    try:
        published = datetime.fromisoformat(date_gmt.replace("Z", "+00:00"))
    except ValueError:
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)

    title = _clean_html(str((row.get("title") or {}).get("rendered", "")))
    summary = _clean_html(str((row.get("excerpt") or {}).get("rendered", "")))
    link = str(row.get("link") or "").strip()
    if (
        not title
        or not link
        or not is_relevant_news(title, summary, category=category)
    ):
        return None
    return {
        "title": title,
        "link": link,
        "source": source,
        "publish_time": published.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "summary": summary,
        "category": category,
        "dedupe_key": link,
    }


def _fetch_archive_range(
    start_date: date,
    end_date: date,
) -> list[dict[str, str | None]]:
    """分页抓取日期范围内的历史文章。"""

    items: list[dict[str, str | None]] = []
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "AI-Music-Collector/1.0"})
    try:
        for source in ARCHIVE_SOURCES:
            page = 1
            while page <= 10:
                try:
                    response = session.get(
                        source["api"],
                        params={
                            "after": f"{start_date.isoformat()}T00:00:00",
                            "before": f"{end_date.isoformat()}T23:59:59",
                            "per_page": 100,
                            "page": page,
                            "orderby": "date",
                            "order": "asc",
                            "_fields": "date_gmt,link,title,excerpt",
                        },
                        timeout=(5, 25),
                    )
                    response.raise_for_status()
                    rows = response.json()
                except (requests.RequestException, ValueError) as exc:
                    LOGGER.warning(
                        "%s 历史归档抓取失败：%s",
                        source["source"],
                        exc,
                    )
                    break
                if not isinstance(rows, list) or not rows:
                    break
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    item = _convert_article(
                        row,
                        source=source["source"],
                        category=source["category"],
                    )
                    if item is not None:
                        items.append(item)
                if len(rows) < 100:
                    break
                page += 1
    finally:
        session.close()
    return items


def _save_items(
    items: list[dict[str, str | None]],
    fetched_at: datetime,
) -> int:
    new_count = save_news_items(items, fetched_at)
    if items:
        stored_items = get_all_news()
        translated_count = translate_items(
            stored_items,
            existing_items=stored_items,
        )
        if translated_count:
            save_news_items(stored_items, fetched_at)
    purge_news_outside_retention()
    return new_count


def backfill_date(
    target_date: str,
    *,
    force: bool = False,
) -> DateBackfillResult:
    """补抓一个具体日期，并限制同一日期的重复尝试频率。"""

    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        return DateBackfillResult(target_date, 0, 0, skipped=True)

    initialize_database()
    now = datetime.now(timezone.utc)
    meta_key = f"date_backfill_attempt:{target_date}"
    last_attempt = get_meta_value(meta_key)
    if not force and last_attempt:
        try:
            previous = datetime.fromisoformat(last_attempt)
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
            if (
                now - previous
            ).total_seconds() < ON_DEMAND_DATE_BACKFILL_SECONDS:
                return DateBackfillResult(target_date, 0, 0, skipped=True)
        except ValueError:
            pass
    set_meta_value(meta_key, now.isoformat(timespec="seconds"))

    items = _fetch_archive_range(target, target)
    return DateBackfillResult(
        target_date=target_date,
        matched_entries=len(items),
        new_count=_save_items(items, now),
    )


def backfill_history(days: int = 60) -> int:
    """回填最近 N 天的可用历史归档。"""

    initialize_database()
    end_date = _display_today()
    start_date = end_date - timedelta(days=max(1, days) - 1)
    LOGGER.info(
        "开始历史回填：%s 至 %s",
        start_date.isoformat(),
        end_date.isoformat(),
    )
    items = _fetch_archive_range(start_date, end_date)
    now = datetime.now(timezone.utc)
    new_count = _save_items(items, now)
    set_meta_value(
        "history_backfill_last_range",
        f"{start_date.isoformat()}..{end_date.isoformat()}",
    )
    LOGGER.info(
        "历史归档命中 %d 条，新增 %d 条",
        len(items),
        new_count,
    )
    return new_count
