"""
Flask 网页展示入口。

网页只负责读取和展示数据库内容，不提供手动抓取或手动录入入口。
后台任务卡住或失败时，网页仍可以正常打开并展示已有资讯。
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, render_template, request, url_for

from config import (
    DISPLAY_TIME_ZONE,
    FLASK_HOST,
    FLASK_PORT,
)
from backfill import backfill_date
from database import (
    get_all_news,
    get_last_fetch_time,
    get_news_count,
    initialize_database,
)
from ranking import filter_and_rank_news
from source_utils import display_source_name
from scheduler_utils import next_estimated_refresh
from translation import is_title_displayable


# 统一日志格式，启动脚本会把标准输出和错误写入 data/flask.log。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)

app = Flask(__name__)
PAGE_SIZE = 20


def _github_actions_auto_sync_configured() -> bool:
    """
    判断 GitHub Actions 自动同步是否已经配置。

    本地后台 worker 已按需求停用，不能再用本地心跳判断自动同步状态。
    当前唯一自动抓取入口是仓库中的 GitHub Actions 工作流。
    """

    workflow_path = (
        Path(__file__).resolve().parent
        / ".github"
        / "workflows"
        / "update-pages.yml"
    )
    return workflow_path.is_file()


def _display_time_zone() -> ZoneInfo:
    """读取展示时区；系统缺少时区数据时回退到中国标准时间。"""

    try:
        return ZoneInfo(DISPLAY_TIME_ZONE)
    except ZoneInfoNotFoundError:
        LOGGER.warning("找不到时区 %s，改用 Asia/Shanghai", DISPLAY_TIME_ZONE)
        return ZoneInfo("Asia/Shanghai")


@app.template_filter("local_time")
def format_local_time(value: str | None) -> str:
    """
    将数据库里的 UTC ISO 时间转换为浏览器用户熟悉的本地时间文本。

    Jinja 模板通过 {{ value | local_time }} 调用这个过滤器。
    如果旧数据或异常数据不是合法时间，则原样显示，页面不会因此报错。
    """

    if not value:
        return "时间未知"

    try:
        parsed_time = datetime.fromisoformat(value)
        # 兼容没有时区的历史数据，将其按 UTC 理解。
        if parsed_time.tzinfo is None:
            parsed_time = parsed_time.replace(tzinfo=timezone.utc)
        local_time = parsed_time.astimezone(_display_time_zone())
        return local_time.strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return value


@app.get("/")
def index():
    """
    首页路由。

    每次访问都从 SQLite 读取最新数据，因此 cron 在后台新增资讯后，
    用户刷新浏览器就能看到，无需重启 Flask。
    """

    initialize_database()
    all_news_items = get_all_news()
    keyword = request.args.get("q", "").strip()[:100]
    raw_days = request.args.get("days", "3")
    allowed_days = {1, 3, 7, 14, 30, 60}
    try:
        selected_days = int(raw_days)
    except ValueError:
        selected_days = 3
    if selected_days not in allowed_days:
        selected_days = 3
    selected_date = request.args.get("date", "").strip()
    if selected_date:
        try:
            date.fromisoformat(selected_date)
        except ValueError:
            selected_date = ""
    content_kind = request.args.get("kind", "all").strip().casefold()
    if content_kind not in {"all", "hardware", "software"}:
        content_kind = "all"
    sort_by = request.args.get("sort", "time").strip().casefold()
    if sort_by not in {"time", "heat", "relevance"}:
        sort_by = "time"
    ranked_news = filter_and_rank_news(
        all_news_items,
        days=selected_days,
        keyword=keyword,
        specific_date=selected_date,
        content_kind=content_kind,
        sort_by=sort_by,
    )
    # 指定日期没有数据时，按该日期的真实范围补抓一次。
    if selected_date and not ranked_news:
        backfill_date(selected_date)
        all_news_items = get_all_news()
        ranked_news = filter_and_rank_news(
            all_news_items,
            days=selected_days,
            keyword=keyword,
            specific_date=selected_date,
            content_kind=content_kind,
            sort_by=sort_by,
        )
    # 英文文章必须完成标题翻译后才展示，翻译失败时保留在数据库中等待重试。
    ranked_news = [item for item in ranked_news if is_title_displayable(item)]
    for item in ranked_news:
        item["display_source"] = display_source_name(
            str(item.get("source", ""))
        )
    # 隐藏未翻译英文后必须重新编号。否则原始第 1 条被隐藏时，页面会从
    # 2 开始，后续也可能出现 2、4、6 这类不连续序号。
    for rank, item in enumerate(ranked_news, start=1):
        item["rank"] = rank
    total_results = len(ranked_news)
    total_pages = max(1, (total_results + PAGE_SIZE - 1) // PAGE_SIZE)
    try:
        current_page = int(request.args.get("page", "1"))
    except ValueError:
        current_page = 1
    current_page = min(max(1, current_page), total_pages)
    page_start = (current_page - 1) * PAGE_SIZE
    paged_news = ranked_news[page_start:page_start + PAGE_SIZE]
    first_page_number = max(1, current_page - 2)
    last_page_number = min(total_pages, current_page + 2)

    return render_template(
        "index.html",
        news_items=paged_news,
        result_count=total_results,
        current_page=current_page,
        total_pages=total_pages,
        page_numbers=range(first_page_number, last_page_number + 1),
        total_count=get_news_count(),
        keyword=keyword,
        selected_days=selected_days,
        selected_date=selected_date,
        content_kind=content_kind,
        sort_by=sort_by,
        last_fetch_at=get_last_fetch_time(),
        auto_sync_online=_github_actions_auto_sync_configured(),
        # 页面始终按固定日程实时计算，不信任重启前可能残留的旧 meta 值。
        next_auto_fetch_at=next_estimated_refresh().isoformat(
            timespec="seconds"
        ),
    )


@app.get("/health")
def health():
    """供本地排障或以后接入监控系统使用的轻量健康检查。"""

    return {"status": "ok", "database": str(get_news_count()) + " articles"}


if __name__ == "__main__":
    # Flask 自带开发服务器足够支持个人本机的每日情报页面。
    # 默认关闭 debug，避免在生产式常驻运行时泄露调试器和自动重载进程。
    initialize_database()
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
        use_reloader=False,
    )
