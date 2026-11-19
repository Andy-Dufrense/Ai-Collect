"""GitHub Releases 数据适配器。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT_SECONDS
from news_filter import is_relevant_news


GITHUB_API_ROOT = "https://api.github.com/repos"


def _clean_text(value: str) -> str:
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return " ".join(text.split())[:500]


def parse_github_releases(
    payload: list[dict[str, Any]],
    *,
    repository: str,
) -> tuple[list[dict[str, str | None]], int, int]:
    """
    把 GitHub Release JSON 转换为统一新闻结构。

    Release 标题、说明和版本号会一起参与过滤，确保与 AI、音频或音乐开发相关。
    """

    matched: list[dict[str, str | None]] = []
    for release in payload:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        title = _clean_text(
            str(release.get("name") or release.get("tag_name") or repository)
        )
        body = _clean_text(str(release.get("body") or ""))
        link = str(release.get("html_url") or "").strip()
        published_at = str(release.get("published_at") or "").strip()
        if not title or not link or not published_at:
            continue
        if not is_relevant_news(
            title,
            body,
            category="AI音频开发",
            source=f"GitHub · {repository}",
        ):
            continue

        try:
            published = datetime.fromisoformat(
                published_at.replace("Z", "+00:00")
            )
        except ValueError:
            continue
        matched.append(
            {
                "title": f"GitHub - 新更新：{title}（{repository}）",
                "link": link,
                "source": f"GitHub · {repository}",
                "publish_time": published.astimezone(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "summary": f"GitHub 项目 {repository} 发布更新：{body}",
                "category": "AI音频开发",
                "dedupe_key": link,
            }
        )
    return matched, len(payload), len(matched)


def fetch_github_releases(
    session: requests.Session,
    repository: str,
) -> tuple[list[dict[str, str | None]], int, int]:
    """请求一个仓库最近 20 个 Release。"""

    response = session.get(
        f"{GITHUB_API_ROOT}/{repository}/releases",
        params={"per_page": 20},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("GitHub Releases 返回格式异常")
    return parse_github_releases(payload, repository=repository)
