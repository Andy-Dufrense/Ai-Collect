"""
搜狗微信公开搜索结果适配器。

搜狗没有稳定的公开 API，因此本模块只解析正常返回的搜索结果 HTML，
不绕过验证码、登录、反爬挑战或访问限制。请求过密或平台要求验证时，
来源会失败并写入日志，RSS 等其他来源仍然继续工作。
"""

from __future__ import annotations

import hashlib
import html
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from config import (
    DATA_DIR,
    REQUEST_TIMEOUT_SECONDS,
    SOGOU_EXPLICIT_SITES,
    SOGOU_PAGE_DELAY_SECONDS,
    SOGOU_PAGES_PER_QUERY,
)
from news_filter import is_relevant_news


SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"
SOGOU_DEBUG_PATH = DATA_DIR / "sogou_debug.html"


def make_sogou_dedupe_key(title: str) -> str:
    """根据规范化标题生成不受搜狗临时 token 影响的稳定去重键。"""

    stable_title = re.sub(r"\s+", "", title).casefold()
    digest = hashlib.sha256(stable_title.encode("utf-8")).hexdigest()
    return f"sogou:{digest}"


def canonicalize_wechat_article_link(link: str) -> str | None:
    """把带临期签名的微信链接转换为永久文章参数。"""

    parsed = urlsplit(link)
    if parsed.hostname != "mp.weixin.qq.com":
        return None
    query = parse_qs(parsed.query)
    required_keys = ("__biz", "mid", "idx", "sn")
    if not all(query.get(key) for key in required_keys):
        return None
    permanent_query = urlencode(
        [(key, query[key][0]) for key in required_keys],
        safe="*",
    )
    return f"https://mp.weixin.qq.com/s?{permanent_query}"


def build_stable_sogou_fallback_link(
    title: str,
    anchor: str = "",
) -> str:
    """用完整标题生成不会携带临时 token 的重新定位链接。"""

    digest = hashlib.sha256(title.encode("utf-8")).hexdigest()[:12]
    fragment = anchor.strip() or f"news-{digest}"
    return (
        "https://weixin.sogou.com/weixin?type=2&query="
        f"{quote_plus(title)}#{fragment}"
    )


def is_temporary_article_link(link: str) -> bool:
    """判断链接是否依赖搜狗 token 或微信短期分享签名。"""

    parsed = urlsplit(link)
    if parsed.hostname == "weixin.sogou.com" and parsed.path == "/link":
        return True
    if parsed.hostname == "mp.weixin.qq.com":
        query = parse_qs(parsed.query)
        if query.get("timestamp") or query.get("signature"):
            return True
    return False


def _extract_publish_time(node: object) -> str | None:
    """
    只从搜狗结果的 .s2 时间元素提取发布时间。

    不从整个结果节点搜索数字，避免把图片 ID、文章 ID 等误当成时间戳。
    """

    time_node = getattr(node, "select_one", lambda _selector: None)(".s2")
    if time_node is None:
        return None
    node_html = str(time_node)
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


def build_sogou_url(
    query: str,
    *,
    start_date: str = "",
    end_date: str = "",
    time_range: str = "",
    page: int = 1,
) -> str:
    """构造普通关键词搜索 URL，不包含登录凭据或规避验证参数。"""

    url = (
        f"{SOGOU_SEARCH_URL}?type=2&query={quote_plus(query)}"
        "&ie=utf8&s_from=input&_sug_=n&_sug_type_="
    )
    if time_range:
        # tsn=1/2/3/4 分别对应一天、一周、一月和一年。
        url += f"&tsn={time_range}"
    elif start_date and end_date:
        # tsn=5 是搜狗公开页面的自定义日期范围模式。
        url += f"&tsn=5&ft={start_date}&et={end_date}"
    if page > 1:
        url += f"&page={page}"
    return url


def parse_sogou_results(
    html: str,
    *,
    page_url: str,
    query: str = "",
) -> tuple[list[dict[str, str | None]], int, int]:
    """
    从搜狗微信结果页解析文章。

    只收录同时满足 AI 与音乐关键词的标题/简介。链接保留为搜狗文章跳转地址，
    因为它需要搜狗的搜索上下文，直接改写成微信链接通常无法稳定访问。
    """

    soup = BeautifulSoup(html, "html.parser")
    result_nodes = soup.select("ul.news-list li")
    matched_items: list[dict[str, str | None]] = []
    explicit_site = SOGOU_EXPLICIT_SITES.get(query)
    item_category = "音乐科技" if explicit_site else "搜狗微信"
    item_source = explicit_site["name"] if explicit_site else ""

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
        if not is_relevant_news(
            title,
            summary,
            category=item_category,
            source=item_source,
        ):
            continue

        # 没有可靠发布时间的旧结果不进入每日排行。
        publish_time = _extract_publish_time(node)
        if publish_time is None:
            continue

        account_node = node.select_one(
            ".account, .s-p a, [class*='account'], a[uigsig]"
        )
        account = (
            " ".join(account_node.get_text(" ", strip=True).split())
            if account_node is not None
            else ""
        )
        if not account:
            if explicit_site:
                account = explicit_site["name"]
            else:
                account = "搜狗搜索"
        link = urljoin(page_url, relative_link)
        matched_items.append(
            {
                "title": title,
                "link": link,
                "source": account or "搜狗微信",
                "publish_time": publish_time,
                "summary": summary,
                "category": item_category,
                "dedupe_key": make_sogou_dedupe_key(title),
            }
        )

    return matched_items, len(result_nodes), len(matched_items)


def _resolve_sogou_article_link(
    session: requests.Session,
    link: str,
) -> str:
    """
    尝试把搜狗跳转链接解析成真实文章链接。

    搜狗可能直接 302，也可能返回一段包含目标 URL 的脚本。解析失败时保留
    原链接，仍然可以在浏览器中打开文章。
    """

    if "/link?" not in link:
        return link
    try:
        response = session.get(
            link,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if not response.url.startswith("https://weixin.sogou.com/"):
            return response.url
        response_text = response.text
    except requests.RequestException:
        return link

    redirect_match = re.search(
        r"window\.location\.replace\([\"']([^\"']+)[\"']\)",
        response_text,
    )
    if redirect_match:
        target = redirect_match.group(1)
    else:
        parts = re.findall(
            r"url\s*\+=\s*[\"']([^\"']+)[\"']",
            response_text,
        )
        target = "".join(parts)
    if not target:
        return link
    target = target.replace("\\x26", "&").replace("\\/", "/")
    target = html.unescape(target)
    return target if target.startswith(("http://", "https://")) else link


def fetch_sogou_query(
    session: requests.Session,
    query: str,
    *,
    source_query: str = "",
    start_date: str = "",
    end_date: str = "",
    time_range: str = "",
    minimum_publish_date: str = "",
    pages: int = SOGOU_PAGES_PER_QUERY,
) -> tuple[list[dict[str, str | None]], int, int]:
    """
    请求并解析一个搜狗微信关键词。

    页面出现“请输入验证码”等限制时直接抛出 ValueError，交由上层记录；
    不尝试识别验证码或伪造登录态。
    """

    # 日期筛选请求比普通搜索更容易触发重定向。先访问一次首页建立正常
    # 搜索会话，再发起关键词请求；这不会绕过验证码或登录。
    if not getattr(session, "_ai_music_sogou_warmed", False):
        try:
            session.get(
                "https://weixin.sogou.com/",
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException:
            pass
        session.headers.update({"Referer": "https://weixin.sogou.com/"})
        session._ai_music_sogou_warmed = True

    all_items: list[dict[str, str | None]] = []
    total_entries = 0
    page_count = max(1, pages)
    result_query = source_query or query
    explicit_site = SOGOU_EXPLICIT_SITES.get(result_query)
    for page in range(1, page_count + 1):
        url = build_sogou_url(
            query,
            start_date=start_date,
            end_date=end_date,
            time_range=time_range,
            page=page,
        )
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding
        except requests.RequestException:
            if page == 1:
                raise
            break

        if (
            "请输入验证码" in response.text
            or "seccodeImage" in response.text
            or "antispider" in response.text
            or "访问过于频繁" in response.text
        ):
            raise ValueError("搜狗要求输入验证码，本类来源本轮跳过")

        page_items, page_total, _page_matched = parse_sogou_results(
            response.text,
            page_url=response.url,
            query=result_query,
        )
        cutoff_date = minimum_publish_date or start_date
        if cutoff_date:
            page_items = [
                item
                for item in page_items
                if str(item.get("publish_time") or "")[:10] >= cutoff_date
            ]
        if page_total == 0:
            if page == 1:
                SOGOU_DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
                SOGOU_DEBUG_PATH.write_text(
                    f"URL: {response.url}\n"
                    f"STATUS: {response.status_code}\n"
                    f"LENGTH: {len(response.text)}\n\n"
                    "HISTORY:\n"
                    + "\n".join(
                        f"{item.status_code} {item.url}"
                        for item in response.history
                    )
                    + "\n\n"
                    + response.text,
                    encoding="utf-8",
                )
                raise ValueError(
                    "搜狗没有返回搜索结果，可能为空结果或页面访问受限"
                )
            break

        total_entries += page_total
        resolved_links = 0
        for item in page_items:
            if explicit_site:
                item["source"] = explicit_site["name"]
            # 每个站点关键词只额外解析少量链接，避免为了真实地址再次触发风控。
            if explicit_site and resolved_links < 3:
                original_link = str(item.get("link") or "")
                item["link"] = _resolve_sogou_article_link(
                    session,
                    original_link,
                )
                resolved_links += 1
            current_link = str(item.get("link") or "")
            canonical_link = canonicalize_wechat_article_link(current_link)
            if canonical_link:
                item["link"] = canonical_link
            elif is_temporary_article_link(current_link):
                # 临时 token 无法长期使用，但完整标题可以用于以后重新定位。
                item["link"] = build_stable_sogou_fallback_link(
                    str(item.get("title") or "")
                )
        all_items.extend(page_items)
        if page_total < 10 or page >= page_count:
            break
        time.sleep(SOGOU_PAGE_DELAY_SECONDS)

    unique_items = {
        str(item.get("dedupe_key") or item.get("link")): item
        for item in all_items
    }
    result_items = list(unique_items.values())
    return result_items, total_entries, len(result_items)
