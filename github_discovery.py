"""发现 GitHub 上新的 AI 音乐项目和 commits。"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from config import (
    GITHUB_COMMIT_LOOKBACK_DAYS,
    GITHUB_REPOSITORY_LOOKBACK_DAYS,
    REQUEST_TIMEOUT_SECONDS,
)
from news_filter import (
    is_github_spam_text,
    is_relevant_news,
)


GITHUB_SEARCH_URL = "https://api.github.com/search"
LOGGER = logging.getLogger(__name__)

# 每类查询都聚焦 AI 音乐开发，查询之间去重。使用多条较窄查询比一条
# 过宽查询更容易命中真正的项目，也能减少无关的“科技”仓库。
REPOSITORY_QUERIES = (
    '"ai music" in:name,description,readme',
    '"music generation" in:name,description,readme',
    '"music production" in:name,description,readme',
    "midi in:name,description,readme",
    "topic:ai-music",
)
COMMIT_QUERIES = (
    '"ai music"',
    '"music generation"',
    '"audio generation"',
    "midi",
    "mixing",
)

# 这些 commit 只维护工程杂项，不反映产品能力或 AI 音频实现变化。
# 即使它们来自 AI 音乐仓库，也没有必要占用资讯列表。
LOW_VALUE_COMMIT_PATTERN = re.compile(
    r"(?:"
    r"^(?:docs?|readme|typo|format|lint|style)(?:\s|:)|"
    r"^update\s+(?:docs?|documentation|readme|dependencies|deps)\b|"
    r"^bump\s+(?:version|dependencies|deps)\b|"
    r"^merge\s+(?:branch|pull request)\b|"
    r"^(?:chore|ci)(?:\([^)]*\))?:"
    r")",
    re.IGNORECASE,
)


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _clean_commit_message(message: str) -> str:
    """只保留 commit 信息第一行，避免多段说明撑满网页列表。"""

    first_line = message.splitlines()[0].strip() if message else ""
    return re.sub(r"\s+", " ", first_line)[:240]


def _is_low_value_commit(message: str) -> bool:
    """跳过 README、依赖升级、格式化和流水线维护等低信息量 commit。"""

    return LOW_VALUE_COMMIT_PATTERN.search(message.strip()) is not None


def _repository_from_commit_url(link: str) -> str:
    """从 commit 网页地址中提取 owner/repository，兼容不同的 API 响应。"""

    match = re.match(r"https?://github\.com/([^/]+/[^/]+)/commit/", link)
    return match.group(1) if match else "GitHub 项目"


def parse_repository_search(
    payload: dict[str, Any],
) -> tuple[list[dict[str, str | None]], int, int]:
    """解析 GitHub 仓库搜索结果。"""

    matched: list[dict[str, str | None]] = []
    items = payload.get("items", [])
    if not isinstance(items, list):
        items = []
    for repository in items:
        if not isinstance(repository, dict):
            continue
        full_name = str(repository.get("full_name") or "").strip()
        description = str(repository.get("description") or "").strip()
        link = str(repository.get("html_url") or "").strip()
        created_at = str(repository.get("created_at") or "").strip()
        if not full_name or not link or not created_at:
            continue
        topics = " ".join(
            str(topic) for topic in repository.get("topics", [])
            if isinstance(topic, str)
        )
        if not is_relevant_news(
            full_name,
            f"{description} {topics}",
        ):
            continue
        try:
            published = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        stars = int(repository.get("stargazers_count") or 0)
        language = str(repository.get("language") or "未标注")
        matched.append(
            {
                # 统一使用“GitHub - 新发布：简介”格式。标题前缀让用户
                # 可以直接搜索 GitHub/Git，翻译模块会单独翻译冒号后的简介。
                "title": (
                    f"GitHub - 新发布：{description or full_name}"
                    f"（{full_name}）"
                )[:400],
                "link": link,
                "source": "GitHub 项目发现",
                "publish_time": published.astimezone(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "summary": (
                    f"GitHub 项目简介：{description or '暂无项目说明'}；"
                    f"主要语言：{language}；Stars：{stars}；"
                    f"主题词：{topics or '未标注'}"
                ),
                "category": "AI音频开发",
                "dedupe_key": link,
            }
        )
    return matched, len(items), len(matched)


def parse_commit_search(
    payload: dict[str, Any],
) -> tuple[list[dict[str, str | None]], int, int]:
    """解析 GitHub commit 搜索结果。"""

    matched: list[dict[str, str | None]] = []
    items = payload.get("items", [])
    if not isinstance(items, list):
        items = []
    for commit_item in items:
        if not isinstance(commit_item, dict):
            continue
        commit = commit_item.get("commit") or {}
        message = _clean_commit_message(str(commit.get("message") or ""))
        link = str(commit_item.get("html_url") or "").strip()
        repository = commit_item.get("repository") or {}
        repository_name = str(
            repository.get("full_name") or _repository_from_commit_url(link)
        )
        commit_date = (
            (commit.get("committer") or {}).get("date")
            or (commit.get("author") or {}).get("date")
            or ""
        )
        commit_date = str(commit_date).strip()
        if (
            not message
            or not link
            or not commit_date
            or _is_low_value_commit(message)
            or is_github_spam_text(f"{message} {repository_name}")
        ):
            continue
        # 与所有其他来源共用同一组 DISCOVERY_KEYWORDS：
        # AI、音乐、乐器、音频、MIDI、混音等任一方向均可被发现。
        if not is_relevant_news(message, repository_name):
            continue
        try:
            published = datetime.fromisoformat(
                commit_date.replace("Z", "+00:00")
            )
        except ValueError:
            continue
        matched.append(
            {
                "title": (
                    f"GitHub - 新更新：{message}（{repository_name}）"
                ),
                "link": link,
                "source": f"GitHub · {repository_name}",
                "publish_time": published.astimezone(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "summary": (
                    f"GitHub 项目 {repository_name} 的最新代码提交：{message}；"
                    "点击标题可查看代码变更和提交说明。"
                ),
                "category": "AI音频开发",
                "dedupe_key": link,
            }
        )
    return matched, len(items), len(matched)


def fetch_new_repositories(
    session: requests.Session,
    *,
    now: datetime | None = None,
) -> tuple[list[dict[str, str | None]], int, int]:
    """搜索近期新建的 AI 音乐相关项目。"""

    current = now or datetime.now(timezone.utc)
    since = (
        current - timedelta(days=GITHUB_REPOSITORY_LOOKBACK_DAYS)
    ).date().isoformat()
    all_items: list[dict[str, str | None]] = []
    total_entries = 0
    query_errors: list[str] = []
    successful_queries = 0
    for query in REPOSITORY_QUERIES:
        try:
            response = session.get(
                f"{GITHUB_SEARCH_URL}/repositories",
                headers=_headers(),
                params={
                    "q": f"{query} created:>={since}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 30,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items, source_total, _source_matched = parse_repository_search(
                response.json()
            )
        except (requests.RequestException, ValueError, TypeError) as exc:
            message = f"仓库查询 {query} 失败：{exc}"
            query_errors.append(message)
            LOGGER.warning(message)
            continue
        successful_queries += 1
        all_items.extend(items)
        total_entries += source_total

    if successful_queries == 0 and query_errors:
        raise ValueError("；".join(query_errors))

    unique_items = {
        str(item.get("dedupe_key") or item.get("link")): item
        for item in all_items
    }
    result_items = list(unique_items.values())
    return result_items, total_entries, len(result_items)


def fetch_new_music_commits(
    session: requests.Session,
    *,
    now: datetime | None = None,
) -> tuple[list[dict[str, str | None]], int, int]:
    """搜索近期与音乐生成、音频生成相关的 commits。"""

    current = now or datetime.now(timezone.utc)
    since = (
        current - timedelta(days=GITHUB_COMMIT_LOOKBACK_DAYS)
    ).date().isoformat()
    all_items: list[dict[str, str | None]] = []
    total_entries = 0
    query_errors: list[str] = []
    successful_queries = 0
    for query in COMMIT_QUERIES:
        try:
            response = session.get(
                f"{GITHUB_SEARCH_URL}/commits",
                headers=_headers(),
                params={
                    "q": f"{query} committer-date:>={since}",
                    "sort": "committer-date",
                    "order": "desc",
                    "per_page": 30,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items, source_total, _source_matched = parse_commit_search(
                response.json()
            )
        except (requests.RequestException, ValueError, TypeError) as exc:
            message = f"commit 查询 {query} 失败：{exc}"
            query_errors.append(message)
            LOGGER.warning(message)
            continue
        successful_queries += 1
        all_items.extend(items)
        total_entries += source_total

    if successful_queries == 0 and query_errors:
        raise ValueError("；".join(query_errors))

    unique_items = {
        str(item.get("dedupe_key") or item.get("link")): item
        for item in all_items
    }
    result_items = list(unique_items.values())
    return result_items, total_entries, len(result_items)


def fetch_github_discovery(
    session: requests.Session,
    *,
    now: datetime | None = None,
) -> tuple[list[dict[str, str | None]], int, int]:
    """
    组合项目发现和 commit 搜索。

    任一搜索失败时保留另一部分结果，不因为单个 GitHub 查询失败丢弃全部内容。
    """

    all_items: list[dict[str, str | None]] = []
    total_entries = 0
    errors: list[str] = []
    for fetch_function in (fetch_new_repositories, fetch_new_music_commits):
        try:
            items, total, _matched = fetch_function(session, now=now)
        except (requests.RequestException, ValueError, TypeError) as exc:
            message = str(exc)
            errors.append(message)
            LOGGER.warning("GitHub 自动发现的一部分查询失败：%s", message)
            continue
        all_items.extend(items)
        total_entries += total
    if errors and not all_items:
        raise ValueError("；".join(errors))

    # 同一项目可能同时出现在仓库和 commit 搜索结果中。
    unique_items = {
        str(item.get("dedupe_key") or item.get("link")): item
        for item in all_items
    }
    result_items = list(unique_items.values())
    return result_items, total_entries, len(result_items)
