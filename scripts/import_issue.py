"""
把通过审核的 GitHub Issue 手动资讯导入静态数据。

Issue Form 生成 Markdown 标题，例如 “### 标题”。该脚本只在仓库维护者
添加 approved-news 标签后运行，避免公开 Issue 被任意写入。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from database import save_news_items
from ranking import filter_and_rank_news


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_DIR / "public" / "data" / "news.json"


def parse_issue_body(body: str) -> dict[str, str]:
    """解析 GitHub Issue Forms 的“### 字段”格式。"""

    sections: dict[str, str] = {}
    current_key = ""
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if line.startswith("### "):
            current_key = line[4:].strip()
            sections[current_key] = ""
        elif current_key:
            sections[current_key] += line + "\n"
    return {key: value.strip() for key, value in sections.items()}


def main() -> int:
    """读取审核 Issue 并把内容合并到 news.json。"""

    body = os.getenv("ISSUE_BODY", "")
    fields = parse_issue_body(body)
    title = fields.get("标题", "").strip()
    link = fields.get("原文链接", "").strip()
    source = fields.get("账号或来源", "").strip() or "GitHub 手动提交"
    category = fields.get("平台分类", "其他").strip() or "其他"
    summary = fields.get("简介", "").strip()

    parsed_link = urlparse(link)
    if (
        not title
        or parsed_link.scheme not in {"http", "https"}
        or not parsed_link.netloc
    ):
        print("Issue 内容缺少有效标题或链接")
        return 1

    now = datetime.now(timezone.utc)
    save_news_items(
        [
            {
                "title": title,
                "link": link,
                "source": source,
                "publish_time": now.isoformat(timespec="seconds"),
                "summary": summary,
                "category": category,
                "dedupe_key": link,
            }
        ],
        now,
    )

    if DATA_FILE.exists():
        try:
            payload: dict[str, Any] = json.loads(
                DATA_FILE.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            payload = {"items": []}
    else:
        payload = {"items": []}

    items = payload.setdefault("items", [])
    if isinstance(items, list) and not any(
        item.get("link") == link for item in items if isinstance(item, dict)
    ):
        manual_item = {
            "title": title,
            "link": link,
            "source": source,
            "publish_time": now.isoformat(timespec="seconds"),
            "summary": summary,
            "category": category,
            "dedupe_key": link,
        }
        scored_item = filter_and_rank_news(
            [manual_item],
            days=0,
            now=now,
        )[0]
        items.insert(0, scored_item)
        payload["total"] = len(items)
        payload["generated_at"] = now.isoformat(timespec="seconds")
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(f"已处理手动资讯：{title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
