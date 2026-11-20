"""
GitHub Actions 数据更新入口。

流程：
1. 读取上次提交到仓库的 public/data/news.json，恢复静态站点已有资讯；
2. 执行一次完整抓取并写入临时 SQLite；
3. 导出新的 JSON 和样式到 public/；
4. Actions 提交 JSON 并部署 GitHub Pages。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Actions 直接执行“python scripts/github_update.py”时，sys.path[0] 是 scripts/。
# 把项目根目录加入搜索路径，才能导入 database.py、ranking.py 等根目录模块。
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from database import (
    get_all_news,
    get_latest_fetch_run,
    initialize_database,
    save_news_items,
)
from backfill import backfill_history
from ranking import filter_and_rank_news
from rss_fetcher import fetch_and_save_news
from source_utils import display_source_name, is_safe_http_url
from translation import translate_items


PUBLIC_DIR = PROJECT_DIR / "public"
DATA_FILE = PUBLIC_DIR / "data" / "news.json"
LOGGER = logging.getLogger(__name__)
MIN_EXPORTED_ITEM_RATIO = 0.70


class ExportValidationError(RuntimeError):
    """导出的静态数据不满足最低安全条件。"""


def _env_flag(name: str) -> bool:
    """读取 GitHub Actions 中的布尔开关。"""

    return os.getenv(name, "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _emit_warning(message: str) -> None:
    """同时写入普通日志和 GitHub Actions 注解。"""

    LOGGER.warning(message)
    if os.getenv("GITHUB_ACTIONS", "").casefold() == "true":
        safe_message = message.replace("%", "%25").replace("\n", "%0A")
        print(f"::warning title=抓取阶段失败::{safe_message}")


def validate_static_payload(
    payload: dict[str, Any],
    *,
    previous_total: int = 0,
) -> None:
    """在覆盖旧网页数据前验证结构、链接和数量骤降。"""

    items = payload.get("items")
    if not isinstance(items, list):
        raise ExportValidationError("导出数据缺少 items 数组")
    total = payload.get("total")
    if not isinstance(total, int) or total != len(items):
        raise ExportValidationError(
            f"导出数量不一致：total={total!r}, items={len(items)}"
        )
    try:
        generated_at = datetime.fromisoformat(
            str(payload.get("generated_at") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ExportValidationError("generated_at 不是合法时间") from exc
    if generated_at.tzinfo is None:
        raise ExportValidationError("generated_at 缺少时区")

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ExportValidationError(f"第 {index + 1} 条资讯不是对象")
        for field_name in ("title", "link", "source"):
            if not str(item.get(field_name) or "").strip():
                raise ExportValidationError(
                    f"第 {index + 1} 条资讯缺少 {field_name}"
                )
        if not is_safe_http_url(str(item.get("link") or "")):
            raise ExportValidationError(
                f"第 {index + 1} 条资讯链接协议不安全"
            )
        publish_time = str(item.get("publish_time") or "").strip()
        if publish_time:
            try:
                datetime.fromisoformat(
                    publish_time.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ExportValidationError(
                    f"第 {index + 1} 条资讯发布时间无效"
                ) from exc

    if total == 0 and not _env_flag("ALLOW_EMPTY_EXPORT"):
        raise ExportValidationError(
            "拒绝导出 0 条资讯；如确需清空请设置 ALLOW_EMPTY_EXPORT=1"
        )
    if (
        previous_total >= 20
        and total < int(previous_total * MIN_EXPORTED_ITEM_RATIO)
        and not _env_flag("ALLOW_LARGE_DATA_DROP")
    ):
        raise ExportValidationError(
            f"资讯数量从 {previous_total} 条骤降到 {total} 条，"
            "已停止覆盖旧数据；如确认无误请设置 "
            "ALLOW_LARGE_DATA_DROP=1"
        )


def _atomic_write_text(path: Path, content: str) -> None:
    """在目标目录写临时文件并原子替换，避免留下半个 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
        ) as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def import_existing_news(path: Path = DATA_FILE) -> int:
    """把上次 GitHub Pages 数据恢复到本次 Actions 的 SQLite。"""

    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return 0
    if not isinstance(items, list):
        return 0

    initialize_database()
    return save_news_items(items, datetime.now(timezone.utc))


def export_static_site(
    output_file: Path = DATA_FILE,
    *,
    copy_style: bool = True,
    translate_titles: bool = True,
) -> dict[str, Any]:
    """
    导出静态页面所需数据。

    GitHub Pages 不执行 Python，因此所有抓取结果都保存为 JSON，浏览器端
    再根据天数、关键词和发布时间进行筛选与排名。
    """

    output_file.parent.mkdir(parents=True, exist_ok=True)
    existing_items: list[dict[str, Any]] = []
    if output_file.exists():
        try:
            existing_payload = json.loads(
                output_file.read_text(encoding="utf-8")
            )
            if isinstance(existing_payload.get("items"), list):
                existing_items = existing_payload["items"]
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            LOGGER.warning("无法读取上一版 news.json：%s", exc)

    now = datetime.now(timezone.utc)
    ranked_items = filter_and_rank_news(get_all_news(), days=0, now=now)
    try:
        translated_count = translate_items(
            ranked_items,
            existing_items=existing_items,
            enabled=translate_titles,
        )
    except Exception as exc:
        translated_count = 0
        _emit_warning(f"标题翻译失败，保留现有中文标题继续导出：{exc}")
    for item in ranked_items:
        item["display_source"] = display_source_name(
            str(item.get("source", ""))
        )
    latest_run = get_latest_fetch_run()
    payload: dict[str, Any] = {
        "generated_at": now.isoformat(timespec="seconds"),
        "total": len(ranked_items),
        "translated_count": translated_count,
        "last_run": latest_run,
        "items": ranked_items,
    }
    validate_static_payload(
        payload,
        previous_total=len(existing_items),
    )
    serialized_payload = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
    _atomic_write_text(output_file, serialized_payload)

    # Pages 只发布 public 目录，因此把现有样式复制过去。
    if copy_style:
        style_source = PROJECT_DIR / "static" / "style.css"
        style_target = PUBLIC_DIR / "style.css"
        style_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(style_source, style_target)
    return payload


def main() -> int:
    """执行 GitHub Actions 的完整更新流程。"""

    try:
        restored = import_existing_news()
        print(f"恢复已有资讯：{restored} 条新写入（其余已存在）")
    except Exception as exc:
        restored = 0
        _emit_warning(f"恢复上一版资讯失败，将继续尝试抓取：{exc}")

    raw_backfill_days = os.getenv("BACKFILL_DAYS", "0").strip()
    try:
        backfill_days = max(0, int(raw_backfill_days))
    except ValueError:
        backfill_days = 0
    if backfill_days:
        try:
            backfilled = backfill_history(backfill_days)
            print(
                f"已完成最近 {backfill_days} 天历史回填："
                f"新增 {backfilled} 条"
            )
        except Exception as exc:
            _emit_warning(f"历史回填失败，继续执行实时抓取：{exc}")

    try:
        result = fetch_and_save_news()
        print(
            "本轮抓取："
            f"成功源 {result.successful_sources}/{result.source_count}，"
            f"命中 {result.matched_entries} 条，新增 {result.new_count} 条"
        )
    except Exception as exc:
        _emit_warning(f"实时抓取失败，将导出已恢复的旧数据：{exc}")

    payload = export_static_site()
    print(f"静态数据已导出：{payload['total']} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
