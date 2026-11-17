"""探测可用于 60 天历史回填的公开数据接口。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "data" / "backfill_probes"

SOURCES = {
    "gdelt_ai_music": (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        "?query=%22AI%20music%22"
        "&mode=artlist&maxrecords=100&format=json&sort=datedesc"
        "&startdatetime=20260919000000&enddatetime=20261117235959"
    ),
    "gdelt_ai_guitar": (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        "?query=%22AI%20guitar%22"
        "&mode=artlist&maxrecords=100&format=json&sort=datedesc"
        "&startdatetime=20260919000000&enddatetime=20261117235959"
    ),
    "google_news_ai_music": (
        "https://news.google.com/rss/search"
        "?q=%22AI%20music%22%20when%3A60d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    ),
    "bing_news_ai_music": (
        "https://www.bing.com/news/search?q=%22AI%20music%22&format=rss"
    ),
    "bing_web_ai_music": (
        "https://www.bing.com/search?q=%22AI%20music%22&format=rss"
    ),
    "cdm_wordpress": (
        "https://cdm.link/wp-json/wp/v2/posts"
        "?after=2026-09-19T00:00:00&per_page=100"
        "&_fields=date,link,title,excerpt"
    ),
    "synthtopia_wordpress": (
        "https://www.synthtopia.com/wp-json/wp/v2/posts"
        "?after=2026-09-19T00:00:00&per_page=100"
        "&_fields=date,link,title,excerpt"
    ),
    "musictech_wordpress": (
        "https://musictech.com/wp-json/wp/v2/posts"
        "?after=2026-09-19T00:00:00&per_page=100"
        "&_fields=date,link,title,excerpt"
    ),
}


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
            )
        }
    )
    summary: dict[str, dict[str, object]] = {}
    for name, url in SOURCES.items():
        try:
            response = session.get(url, timeout=(5, 20))
            body = response.content
            (OUTPUT_DIR / f"{name}.txt").write_bytes(body)
            content_type = response.headers.get("Content-Type", "")
            summary[name] = {
                "status": response.status_code,
                "content_type": content_type,
                "bytes": len(body),
                "preview": body[:300].decode("utf-8", errors="replace"),
            }
        except requests.RequestException as exc:
            summary[name] = {"error": str(exc)}
        print(name, summary[name])

    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
