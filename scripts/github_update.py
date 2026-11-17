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
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database import (
    get_all_news,
    get_latest_fetch_run,
    initialize_database,
    save_news_items,
)
from ranking import filter_and_rank_news
from rss_fetcher import fetch_and_save_news


PROJECT_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = PROJECT_DIR / "public"
DATA_FILE = PUBLIC_DIR / "data" / "news.json"


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
) -> dict[str, Any]:
    """
    导出静态页面所需数据。

    GitHub Pages 不执行 Python，因此所有抓取结果都保存为 JSON，浏览器端
    再根据天数、关键词和发布时间进行筛选与排名。
    """

    output_file.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ranked_items = filter_and_rank_news(get_all_news(), days=0, now=now)
    latest_run = get_latest_fetch_run()
    payload: dict[str, Any] = {
        "generated_at": now.isoformat(timespec="seconds"),
        "total": len(ranked_items),
        "last_run": latest_run,
        "items": ranked_items,
    }
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Pages 只发布 public 目录，因此把现有样式复制过去。
    if copy_style:
        style_source = PROJECT_DIR / "static" / "style.css"
        style_target = PUBLIC_DIR / "style.css"
        style_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(style_source, style_target)
    return payload


def main() -> int:
    """执行 GitHub Actions 的完整更新流程。"""

    restored = import_existing_news()
    print(f"恢复已有资讯：{restored} 条新写入（其余已存在）")

    result = fetch_and_save_news()
    print(
        "本轮抓取："
        f"成功源 {result.successful_sources}/{result.source_count}，"
        f"命中 {result.matched_entries} 条，新增 {result.new_count} 条"
    )

    payload = export_static_site()
    print(f"静态数据已导出：{payload['total']} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
