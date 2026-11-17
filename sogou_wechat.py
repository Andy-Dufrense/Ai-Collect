"""
搜狗微信公开搜索结果适配器。

搜狗没有稳定的公开 API，因此本模块只解析正常返回的搜索结果 HTML，
不绕过验证码、登录、反爬挑战或访问限制。请求过密或平台要求验证时，
来源会失败并写入日志，RSS 等其他来源仍然继续工作。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT_SECONDS
from news_filter import is_relevant_news


SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"


def make_sogou_dedupe_key(title: str) -> str:
    """根据规范化标题生成不受搜狗临时 token 影响的稳定去重键。"""

    stable_title = re.sub(r"\s+", "", title).casefold()
    digest = hashlib.sha256(stable_title.encode("utf-8")).hexdigest()
    return f"sogou:{digest}"


def _extract_publish_time(node: object) -> str | None:
    """兼容时间戳脚本、日期文本以及“几小时前”等搜狗展示格式。"""

    node_html = str(node)
    timestamp_match = re.search(
        r"(?:timeConvert|timestamp)[^\d]{0,8}(\d{10,13})",
        node_html,
    )
    if timestamp_match:
        timestamp = int(timestamp_match.group(1))
        if timestamp > 10_000_000_000:
            timestamp //= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(
            timespec="seconds"
        )

    date_match = re.search(
        r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})",
        node_html,
    )
    if date_match:
        year, month, day = map(int, date_match.groups())
        return datetime(year, month, day, tzinfo=timezone.utc).isoformat(
            timespec="seconds"
        )

    now = datetime.now(timezone.utc)
    relative_match = re.search(r"(\d+)\s*(分钟|小时)前", node_html)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        delta_seconds = amount * (60 if unit == "分钟" else 3600)
        return datetime.fromtimestamp(
            now.timestamp() - delta_seconds,
            tz=timezone.utc,
        ).isoformat(timespec="seconds")
    if "昨天" in node_html:
        return datetime.fromtimestamp(
            now.timestamp() - 86400,
            tz=timezone.utc,
        ).isoformat(timespec="seconds")
    if "前天" in node_html:
        return datetime.fromtimestamp(
            now.timestamp() - 2 * 86400,
            tz=timezone.utc,
        ).isoformat(timespec="seconds")
    return None


def build_sogou_url(query: str) -> str:
    """构造普通关键词搜索 URL，不包含登录凭据或规避验证参数。"""

    return (
        f"{SOGOU_SEARCH_URL}?type=2&query={quote_plus(query)}"
        "&ie=utf8&s_from=input"
    )


def parse_sogou_results(
    html: str,
    *,
    page_url: str,
) -> tuple[list[dict[str, str | None]], int, int]:
    """
    从搜狗微信结果页解析文章。

    只收录同时满足 AI 与音乐关键词的标题/简介。链接保留为搜狗文章跳转地址，
    因为它需要搜狗的搜索上下文，直接改写成微信链接通常无法稳定访问。
    """

    soup = BeautifulSoup(html, "html.parser")
    result_nodes = soup.select("ul.news-list li")
    matched_items: list[dict[str, str | None]] = []

    for node in result_nodes:
        title_link = node.select_one("h3 a")
        if title_link is None:
            continue

        title = " ".join(title_link.get_text(" ", strip=True).split())
        relative_link = str(title_link.get("href", "")).strip()
        if not title or not relative_link:
            continue

        summary_node = node.select_one("p.txt-info")
        summary = (
            " ".join(summary_node.get_text(" ", strip=True).split())
            if summary_node is not None
            else ""
        )
        if not is_relevant_news(title, summary):
            continue

        # 没有可靠发布时间的旧结果不进入每日排行。
        publish_time = _extract_publish_time(node)
        if publish_time is None:
            continue

        account_node = node.select_one(".account")
        account = (
            " ".join(account_node.get_text(" ", strip=True).split())
            if account_node is not None
            else "搜狗微信"
        )
        link = urljoin(page_url, relative_link)
        matched_items.append(
            {
                "title": title,
                "link": link,
                "source": account or "搜狗微信",
                "publish_time": publish_time,
                "summary": summary,
                "category": "搜狗微信",
                "dedupe_key": make_sogou_dedupe_key(title),
            }
        )

    return matched_items, len(result_nodes), len(matched_items)


def fetch_sogou_query(
    session: requests.Session,
    query: str,
) -> tuple[list[dict[str, str | None]], int, int]:
    """
    请求并解析一个搜狗微信关键词。

    页面出现“请输入验证码”等限制时直接抛出 ValueError，交由上层记录；
    不尝试识别验证码或伪造登录态。
    """

    url = build_sogou_url(query)
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding

    if (
        "请输入验证码" in response.text
        or "seccodeImage" in response.text
        or "antispider" in response.text
        or "访问过于频繁" in response.text
    ):
        raise ValueError("搜狗要求输入验证码，本类来源本轮跳过")

    parsed_result = parse_sogou_results(response.text, page_url=response.url)
    if parsed_result[1] == 0:
        raise ValueError("搜狗没有返回搜索结果，可能为空结果或页面访问受限")
    return parsed_result
