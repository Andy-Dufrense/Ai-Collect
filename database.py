"""
SQLite 数据持久化模块。

数据库只负责存储和查询，不依赖 Flask，也不负责联网抓取。
因此 cron 可以直接调用抓取逻辑，而网页应用可以同时读取数据库。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from config import get_database_path


# link 使用 UNIQUE 唯一索引，从数据库层面保证同一篇资讯不会重复入库。
# app_meta 保存“上次抓取时间”等运行信息，不修改需求规定的 news 字段。
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    source TEXT NOT NULL,
    publish_time TEXT,
    summary TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'RSS',
    dedupe_key TEXT,
    title_zh TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_news_link_unique
    ON news(link);

CREATE INDEX IF NOT EXISTS idx_news_publish_time
    ON news(publish_time DESC);

CREATE TABLE IF NOT EXISTS app_meta (
    meta_key TEXT PRIMARY KEY,
    meta_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at TEXT NOT NULL,
    source_count INTEGER NOT NULL,
    successful_sources INTEGER NOT NULL,
    total_entries INTEGER NOT NULL,
    matched_entries INTEGER NOT NULL,
    new_count INTEGER NOT NULL,
    errors_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_fetch_runs_fetched_at
    ON fetch_runs(fetched_at DESC);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """
    创建一个会自动关闭的数据库连接。

    每次操作都使用独立连接，比长期共享一个连接更适合 cron 与 Flask
    同时访问数据库的场景。timeout 可以让短暂写入冲突自动等待。
    """

    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        # WAL 模式可以让网页读取与后台写入更好地并行。
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 15000")
        yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    """创建数据库、表、索引和运行信息表；重复调用不会清空已有数据。"""

    with get_connection() as connection:
        connection.executescript(SCHEMA_SQL)
        # 兼容已经创建过的旧数据库：category 是后加入的字段，需要就地迁移。
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(news)").fetchall()
        }
        if "category" not in columns:
            connection.execute(
                "ALTER TABLE news ADD COLUMN category TEXT NOT NULL DEFAULT 'RSS'"
            )
        if "dedupe_key" not in columns:
            connection.execute("ALTER TABLE news ADD COLUMN dedupe_key TEXT")
        if "title_zh" not in columns:
            connection.execute("ALTER TABLE news ADD COLUMN title_zh TEXT")
        connection.execute(
            "UPDATE news SET dedupe_key = link "
            "WHERE dedupe_key IS NULL OR dedupe_key = ''"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_news_dedupe_unique "
            "ON news(dedupe_key)"
        )
        connection.commit()


def _normalize_utc_datetime(value: datetime) -> datetime:
    """把 datetime 转成带 UTC 时区的值，统一数据库中的时间格式。"""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def save_news_items(
    items: Iterable[Mapping[str, Any]],
    fetched_at: datetime,
) -> int:
    """
    批量保存资讯，并返回本次真正新增的条数。

    使用 INSERT OR IGNORE 依赖 link 唯一索引去重：数据库已有相同链接时，
    这条数据会被安静跳过，不会覆盖已有标题或简介，也不会产生重复卡片。
    """

    fetched_at_utc = _normalize_utc_datetime(fetched_at)
    inserted_count = 0

    with get_connection() as connection:
        for item in items:
            title = str(item.get("title", "")).strip()
            link = str(item.get("link", "")).strip()
            source = str(item.get("source", "")).strip()
            summary = str(item.get("summary", "")).strip()
            raw_publish_time = item.get("publish_time")
            publish_time = (
                str(raw_publish_time).strip()
                if raw_publish_time is not None
                else None
            )
            if not publish_time or publish_time.casefold() == "none":
                publish_time = None
            category = str(item.get("category", "")).strip() or "RSS"
            dedupe_key = str(item.get("dedupe_key", "")).strip() or link
            raw_title_zh = item.get("title_zh")
            title_zh = (
                str(raw_title_zh).strip() if raw_title_zh is not None else None
            )
            if not title_zh or title_zh.casefold() == "none":
                title_zh = None

            # 标题、链接和来源是有效资讯的最低要求，缺失时直接跳过。
            if not title or not link or not source:
                continue

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO news
                    (
                        title,
                        link,
                        source,
                        publish_time,
                        summary,
                        category,
                        dedupe_key,
                        title_zh
                    )
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    link,
                    source,
                    publish_time,
                    summary,
                    category,
                    dedupe_key,
                    title_zh,
                ),
            )
            inserted_count += cursor.rowcount
            if cursor.rowcount == 0:
                # 搜狗跳转链接的 token 会变化，但 dedupe_key 保持稳定。
                # 更新为最新链接，保证旧文章不会因为链接变化重复入库。
                connection.execute(
                    """
                    UPDATE news
                    SET title = ?,
                        link = ?,
                        source = ?,
                        publish_time = COALESCE(?, publish_time),
                        summary = ?,
                        category = ?,
                        title_zh = COALESCE(?, title_zh)
                    WHERE dedupe_key = ?
                    """,
                    (
                        title,
                        link,
                        source,
                        publish_time,
                        summary,
                        category,
                        title_zh,
                        dedupe_key,
                    ),
                )

        # 即使本轮没有新资讯，也记录抓取时间，页面可以显示任务确实运行过。
        connection.execute(
            """
            INSERT INTO app_meta (meta_key, meta_value)
            VALUES ('last_fetch_at', ?)
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
            """,
            (fetched_at_utc.isoformat(timespec="seconds"),),
        )
        connection.commit()

    return inserted_count


def get_all_news() -> list[dict[str, Any]]:
    """
    按发布时间倒序返回全部资讯。

    publish_time 保存为 UTC ISO 8601 字符串，因此可以直接按字符串排序。
    没有发布时间的资讯排在最后，避免未知时间干扰最新内容。
    """

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                title,
                link,
                source,
                publish_time,
                summary,
                category,
                dedupe_key,
                title_zh
            FROM news
            ORDER BY
                CASE WHEN publish_time IS NULL OR publish_time = '' THEN 1 ELSE 0 END,
                publish_time DESC,
                id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_news_count() -> int:
    """返回当前数据库收录的资讯总数。"""

    with get_connection() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM news").fetchone()
    return int(row["total"]) if row else 0


def get_last_fetch_time() -> str | None:
    """读取上一次抓取任务的完成时间；从未抓取时返回 None。"""

    with get_connection() as connection:
        row = connection.execute(
            "SELECT meta_value FROM app_meta WHERE meta_key = 'last_fetch_at'"
        ).fetchone()
    return str(row["meta_value"]) if row else None


def record_fetch_run(
    *,
    fetched_at: datetime,
    source_count: int,
    successful_sources: int,
    total_entries: int,
    matched_entries: int,
    new_count: int,
    errors: Iterable[str],
) -> None:
    """
    保存一条抓取运行记录。

    news 表只保存最终资讯，而 fetch_runs 表保存每次任务是否成功、
    抓到了多少内容以及出错来源。两部分职责分开，统计信息不会污染新闻数据。
    """

    fetched_at_utc = _normalize_utc_datetime(fetched_at)
    errors_json = json.dumps(list(errors), ensure_ascii=False)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO fetch_runs (
                fetched_at,
                source_count,
                successful_sources,
                total_entries,
                matched_entries,
                new_count,
                errors_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fetched_at_utc.isoformat(timespec="seconds"),
                source_count,
                successful_sources,
                total_entries,
                matched_entries,
                new_count,
                errors_json,
            ),
        )
        connection.commit()


def get_latest_fetch_run() -> dict[str, Any] | None:
    """
    返回最近一次抓取任务的状态。

    错误详情会转换成 Python 列表，供命令行排障使用；网页只展示失败数量，
    避免将代理、内部地址等异常文本直接暴露在浏览器中。
    """

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                fetched_at,
                source_count,
                successful_sources,
                total_entries,
                matched_entries,
                new_count,
                errors_json
            FROM fetch_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if not row:
        return None

    result = dict(row)
    try:
        result["errors"] = json.loads(result.pop("errors_json"))
    except (json.JSONDecodeError, TypeError):
        result["errors"] = []
    result["failed_sources"] = (
        int(result["source_count"]) - int(result["successful_sources"])
    )
    return result


def set_worker_heartbeat(heartbeat_at: datetime) -> None:
    """
    更新后台抓取进程的心跳时间。

    工作进程启动和每轮抓取结束后都会调用此函数。网页通过心跳是否足够新
    来判断自动同步是否真正在线，而不是只根据 PID 文件猜测。
    """

    heartbeat_utc = _normalize_utc_datetime(heartbeat_at)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO app_meta (meta_key, meta_value)
            VALUES ('worker_heartbeat_at', ?)
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
            """,
            (heartbeat_utc.isoformat(timespec="seconds"),),
        )
        connection.commit()


def get_worker_heartbeat() -> str | None:
    """返回后台工作进程最近一次心跳时间。"""

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT meta_value
            FROM app_meta
            WHERE meta_key = 'worker_heartbeat_at'
            """
        ).fetchone()
    return str(row["meta_value"]) if row else None


def clear_worker_heartbeat() -> None:
    """工作进程正常退出时清理心跳，网页会立即显示自动同步离线。"""

    with get_connection() as connection:
        connection.execute(
            "DELETE FROM app_meta WHERE meta_key = 'worker_heartbeat_at'"
        )
        connection.commit()


def get_meta_value(key: str) -> str | None:
    """读取 app_meta 中的通用运行状态。"""

    with get_connection() as connection:
        row = connection.execute(
            "SELECT meta_value FROM app_meta WHERE meta_key = ?",
            (key,),
        ).fetchone()
    return str(row["meta_value"]) if row else None


def set_meta_value(key: str, value: str) -> None:
    """写入 app_meta 中的通用运行状态。"""

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO app_meta (meta_key, meta_value)
            VALUES (?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
            """,
            (key, value),
        )
        connection.commit()


def clear_meta_value(key: str) -> None:
    """删除一条运行状态，例如工作进程退出时清除下次刷新时间。"""

    with get_connection() as connection:
        connection.execute("DELETE FROM app_meta WHERE meta_key = ?", (key,))
        connection.commit()
