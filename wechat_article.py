"""直接读取已指定的微信公众号文章页面。"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT_SECONDS
from news_filter import is_relevant_news


def _meta_content(soup: BeautifulSoup, *selectors: str) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node is not None:
            value = str(node.get("content", "")).strip()
            if value:
                return html.unescape(value)
    return ""


def _js_string(html_text: str, variable: str) -> str:
    match = re.search(
        rf"{re.escape(variable)}\s*=\s*([\"'])(.*?)\1",
        html_text,
        re.DOTALL,
    )
    if not match:
        return ""
    value = html.unescape(match.group(2))
    return re.sub(r"\s+", " ", value).strip()


def _publish_time(html_text: str, soup: BeautifulSoup) -> str | None:
    for variable in ("ct", "create_time", "publish_time"):
        match = re.search(
            rf"{re.escape(variable)}\s*=\s*[\"']?(\d{{10,13}})",
            html_text,
        )
        if match:
            timestamp = int(match.group(1))
            if timestamp > 10_000_000_000:
                timestamp //= 1000
            return datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            ).isoformat(timespec="seconds")

    published = _meta_content(
        soup,
        'meta[property="article:published_time"]',
        'meta[name="article:published_time"]',
    )
    if published:
        try:
            parsed = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat(
                timespec="seconds"
            )
        except ValueError:
            pass
    return None


def parse_wechat_article(
    html_text: str,
    *,
    link: str,
    source: str,
) -> tuple[list[dict[str, str | None]], int, int]:
    """从微信公众号文章 HTML 提取标题、账号、时间和简介。"""

    soup = BeautifulSoup(html_text, "html.parser")
    title = _meta_content(
        soup,
        'meta[property="og:title"]',
        'meta[name="twitter:title"]',
    )
    if not title:
        title_node = soup.select_one("#activity-name, h1")
        title = (
            " ".join(title_node.get_text(" ", strip=True).split())
            if title_node is not None
            else ""
        )
    if not title:
        title = _js_string(html_text, "msg_title")

    account = _meta_content(
        soup,
        'meta[property="og:article:author"]',
    )
    if not account:
        account_node = soup.select_one("#js_name")
        account = (
            " ".join(account_node.get_text(" ", strip=True).split())
            if account_node is not None
            else ""
        )
    if not account:
        account = _js_string(html_text, "nickname")
    resolved_source = source or (
        f"微信公众号 · {account}" if account else "微信公众号"
    )

    summary = _meta_content(
        soup,
        'meta[property="og:description"]',
        'meta[name="description"]',
    )
    if not summary:
        content_node = soup.select_one("#js_content")
        if content_node is not None:
            summary = " ".join(
                content_node.get_text(" ", strip=True).split()
            )[:500]

    publish_time = _publish_time(html_text, soup)
    if not title or not publish_time:
        raise ValueError("微信公众号文章缺少标题或真实发布时间")
    if not is_relevant_news(title, summary, category="微信公众号"):
        return [], 1, 0
    return (
        [
            {
                "title": title,
                "link": link,
                "source": resolved_source,
                "publish_time": publish_time,
                "summary": summary,
                "category": "微信公众号",
                "dedupe_key": link,
            }
        ],
        1,
        1,
    )


def fetch_wechat_article(
    session: requests.Session,
    url: str,
    *,
    source: str,
) -> tuple[list[dict[str, str | None]], int, int]:
    """请求并解析一个指定的微信公众号文章链接。"""

    response = session.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                "Mobile Safari/537.36 MicroMessenger/8.0"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    if any(
        marker in response.text
        for marker in ("环境异常", "访问过于频繁", "请输入验证码")
    ):
        raise ValueError("微信公众号页面要求验证或限制访问")
    return parse_wechat_article(
        response.text,
        link=url,
        source=source,
    )
