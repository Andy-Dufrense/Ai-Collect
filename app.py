"""
Flask 网页展示入口。

网页只负责展示数据库内容，以及提供一个手动抓取按钮。
真正的每日抓取仍由 fetch_news.py + cron 完成，所以后台任务卡住或失败时，
网页仍可以正常打开并展示已有资讯。
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, Response, redirect, render_template, request, url_for

from config import (
    ADMIN_TOKEN,
    AUTO_FETCH_INTERVAL_SECONDS,
    DISPLAY_TIME_ZONE,
    FLASK_HOST,
    FLASK_PORT,
)
from database import (
    get_all_news,
    get_latest_fetch_run,
    get_last_fetch_time,
    get_news_count,
    get_worker_heartbeat,
    initialize_database,
    save_news_items,
)
from ranking import filter_and_rank_news
from rss_fetcher import FetchAlreadyRunningError, fetch_and_save_news


# 统一日志格式，启动脚本会把标准输出和错误写入 data/flask.log。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)

app = Flask(__name__)


@app.before_request
def protect_admin_routes():
    """
    公网部署时保护会写数据的路由。

    ADMIN_TOKEN 未配置时保持本机使用便利；配置后，浏览器会弹出 Basic Auth
    登录框。读取首页、搜索和筛选仍然公开。
    """

    if not ADMIN_TOKEN:
        return None
    if request.path not in {"/add_manual", "/fetch"}:
        return None

    auth = request.authorization
    if (
        auth is None
        or auth.username != "admin"
        or not secrets.compare_digest(auth.password or "", ADMIN_TOKEN)
    ):
        return Response(
            "需要管理员凭据",
            401,
            {"WWW-Authenticate": 'Basic realm="AI Music Admin"'},
        )
    return None


def _query_int(name: str, default: int = 0) -> int:
    """
    安全读取 URL 中的整数参数。

    正常抓取结果都由程序生成，但用户仍可能手动修改地址栏。这里遇到
    非数字内容时回退到默认值，避免首页因为一个错误查询参数而返回 500。
    """

    raw_value = request.args.get(name, "")
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _is_auto_sync_online(heartbeat_value: str | None) -> bool:
    """
    根据后台心跳判断自动同步是否在线。

    抓取间隔较长时，心跳会长时间保持不变，因此允许它存活两个轮询周期
    再加 60 秒。这样正常等待期间不会误报离线，进程异常退出后也会及时提示。
    """

    if not heartbeat_value:
        return False

    try:
        heartbeat = datetime.fromisoformat(heartbeat_value)
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        maximum_age = timedelta(
            seconds=max(90.0, AUTO_FETCH_INTERVAL_SECONDS * 2 + 60)
        )
        return datetime.now(timezone.utc) - heartbeat <= maximum_age
    except (TypeError, ValueError):
        return False


def _redact_error_text(message: str) -> str:
    """
    隐藏错误文本中代理 URL 可能包含的账号密码。

    网络异常详情对本地排障很有帮助，但网页展示前仍应避免泄露凭据。
    """

    return re.sub(r"(https?://)[^/@\s]+@", r"\1***@", message)


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
    latest_fetch_run = get_latest_fetch_run()
    keyword = request.args.get("q", "").strip()[:100]
    raw_days = request.args.get("days", "3")
    allowed_days = {0, 1, 3, 7, 14, 30}
    try:
        selected_days = int(raw_days)
    except ValueError:
        selected_days = 3
    if selected_days not in allowed_days:
        selected_days = 3
    ranked_news = filter_and_rank_news(
        all_news_items,
        days=selected_days,
        keyword=keyword,
    )

    # 手动抓取完成后，fetch 路由会通过 URL 参数带回简短统计信息。
    fetch_status = request.args.get("status", "")
    message = ""
    message_class = "notice"
    if fetch_status == "success":
        matched = _query_int("matched")
        new_count = _query_int("new")
        success_sources = _query_int("success")
        failed_sources = _query_int("failed")
        message = (
            f"抓取完成：命中 {matched} 条，新增 {new_count} 条；"
            f"成功源 {success_sources} 个，失败源 {failed_sources} 个。"
        )
        if failed_sources > 0:
            message_class = "notice warning"
    elif fetch_status == "error":
        message = "抓取任务发生异常，请查看 data/flask.log 获取详细原因。"
        message_class = "notice error"
    elif fetch_status == "busy":
        message = "后台正在执行抓取，请稍后刷新页面；已有数据不会受影响。"
        message_class = "notice warning"

    return render_template(
        "index.html",
        news_items=ranked_news,
        result_count=len(ranked_news),
        total_count=get_news_count(),
        keyword=keyword,
        selected_days=selected_days,
        last_fetch_at=get_last_fetch_time(),
        last_fetch_run=latest_fetch_run,
        fetch_error_messages=[
            _redact_error_text(str(error))
            for error in (latest_fetch_run or {}).get("errors", [])
        ],
        auto_sync_online=_is_auto_sync_online(get_worker_heartbeat()),
        auto_interval_minutes=max(
            1,
            round(AUTO_FETCH_INTERVAL_SECONDS / 60),
        ),
        message=message,
        message_class=message_class,
    )


@app.post("/fetch")
def fetch_now():
    """
    手动抓取路由。

    使用 POST 而不是普通链接，防止浏览器预加载或爬虫误触抓取。
    完整堆栈只记录在服务器日志中；网页只显示经过脱敏的摘要错误。
    """

    try:
        result = fetch_and_save_news()
    except FetchAlreadyRunningError:
        return redirect(url_for("index", status="busy"))
    except Exception:
        LOGGER.exception("手动抓取任务失败")
        return redirect(url_for("index", status="error"))

    return redirect(
        url_for(
            "index",
            status="success",
            matched=result.matched_entries,
            new=result.new_count,
            success=result.successful_sources,
            failed=result.failed_sources,
        )
    )


@app.route("/add_manual", methods=["GET", "POST"])
def add_manual():
    """
    手动收录公众号、视频号、抖音或其他资讯。

    手动来源不抓取第三方页面，只保存用户提供的标题、链接和简介，
    因此不会绕过任何平台登录或访问限制。
    """

    allowed_categories = {"微信公众号", "微信视频号", "抖音", "其他"}
    message = ""
    message_class = "notice"

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        link = request.form.get("link", "").strip()
        source = request.form.get("source", "").strip() or "手动录入"
        summary = request.form.get("summary", "").strip()
        category = request.form.get("category", "其他").strip()
        if category not in allowed_categories:
            category = "其他"

        parsed_link = urlparse(link)
        if not title:
            message = "标题不能为空。"
            message_class = "notice error"
        elif parsed_link.scheme not in {"http", "https"} or not parsed_link.netloc:
            message = "链接必须是完整的 http:// 或 https:// 地址。"
            message_class = "notice error"
        else:
            inserted_count = save_news_items(
                [
                    {
                        "title": title,
                        "link": link,
                        "source": source,
                        "publish_time": datetime.now(timezone.utc).isoformat(
                            timespec="seconds"
                        ),
                        "summary": summary,
                        "category": category,
                    }
                ],
                datetime.now(timezone.utc),
            )
            return redirect(
                url_for(
                    "add_manual",
                    status="saved" if inserted_count else "duplicate",
                )
            )

    success_status = request.args.get("status", "")
    if success_status == "saved":
        message = "资讯已保存，可以返回首页查看。"
    elif success_status == "duplicate":
        message = "这个链接已经收录，无需重复添加。"
        message_class = "notice warning"

    return render_template(
        "manual.html",
        message=message,
        message_class=message_class,
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
