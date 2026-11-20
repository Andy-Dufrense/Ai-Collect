"""
单独诊断三个不可用来源近三天的文章。

只处理小旭音乐、Soomal、音频应用，使用与正式抓取相同的直接站点解析、
入口备用和 Chromium 回退，但强制执行近三天时间窗。有效内容会入库；
该诊断不会推进来源的增量成功时间。
"""

from __future__ import annotations

import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config import DIRECT_SITE_SOURCES, DISPLAY_TIME_ZONE, RSS_SOURCES
from database import initialize_database, save_news_items
from direct_site import fetch_direct_site
from rss_fetcher import (
    _direct_source_urls,
    _discover_fetch_routes,
    fetch_one_source,
)


TARGET_SOURCES = {"小旭音乐", "Soomal", "音频应用"}


def three_day_cutoff(now: datetime | None = None) -> datetime:
    """按北京时间的三个日历日计算抓取起点。"""

    current = now or datetime.now(timezone.utc)
    try:
        display_zone = ZoneInfo(DISPLAY_TIME_ZONE)
    except ZoneInfoNotFoundError:
        display_zone = ZoneInfo("Asia/Shanghai")
    today = current.astimezone(display_zone).date()
    start_date = today - timedelta(days=2)
    return datetime.combine(
        start_date,
        time.min,
        tzinfo=display_zone,
    ).astimezone(timezone.utc)


def main() -> int:
    initialize_database()
    fetched_at = datetime.now(timezone.utc)
    since = three_day_cutoff(fetched_at).isoformat(timespec="seconds")
    routes = _discover_fetch_routes()
    all_items: list[dict[str, str | None]] = []

    try:
        for source_config in DIRECT_SITE_SOURCES:
            source_name = source_config["source"]
            if source_name not in TARGET_SOURCES:
                continue
            print(f"\n=== {source_name} · 近三天 · since={since} ===")
            source_items: list[dict[str, str | None]] = []
            errors: list[str] = []
            for route in routes:
                for direct_url in _direct_source_urls(source_config):
                    try:
                        items, total, matched = fetch_direct_site(
                            route.session,
                            source_name,
                            direct_url,
                            source_config.get("category", "音乐科技"),
                            max_pages=8,
                            max_articles=200,
                            browser_fallback=True,
                            since=since,
                        )
                    except Exception as exc:
                        errors.append(
                            f"{route.label} · {direct_url}: {exc}"
                        )
                        continue
                    print(
                        f"{route.label} · {direct_url}: "
                        f"候选 {total}，近三天有效 {matched}"
                    )
                    source_items.extend(items)
                    break
                if source_items:
                    break

            unique_source_items = {
                str(item.get("link")): item
                for item in source_items
            }
            resolved_items = list(unique_source_items.values())
            if not resolved_items:
                search_source_name = f"百度新闻：{source_name}"
                search_config = next(
                    (
                        config
                        for config in RSS_SOURCES
                        if config.get("source") == search_source_name
                    ),
                    None,
                )
                if search_config:
                    for route in routes:
                        try:
                            (
                                search_items,
                                search_total,
                                search_matched,
                            ) = fetch_one_source(
                                route.session,
                                search_source_name,
                                search_config["url"],
                                search_config.get("category", "音乐科技"),
                            )
                        except Exception as exc:
                            errors.append(
                                f"{route.label} · {search_source_name}: {exc}"
                            )
                            continue
                        print(
                            f"{route.label} · {search_source_name}: "
                            f"搜索结果 {search_total}，有效 {search_matched}"
                        )
                        resolved_items.extend(
                            item
                            for item in search_items
                            if str(item.get("publish_time") or "") >= since
                        )
                        break
            if resolved_items:
                for item in resolved_items:
                    print(
                        f"- {item.get('publish_time')} | "
                        f"{item.get('title')} | {item.get('link')}"
                    )
            else:
                print("近三天有效文章：0")
                for error in errors:
                    print(f"- 失败：{error}")
            all_items.extend(resolved_items)
    finally:
        for route in routes:
            route.session.close()

    added = save_news_items(all_items, fetched_at)
    print(f"\n诊断结果：近三天有效 {len(all_items)} 条，新入库 {added} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
