"""
直接读取音乐科技站点文章列表。

部分国内垂直网站没有可用 RSS，搜狗也只能返回按相关度排序的旧文章。
本模块直接从站点列表页提取标题和链接，再读取文章页元数据补齐发布时间，
不依赖搜索引擎中转。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT_SECONDS
from news_filter import is_relevant_news
from text_utils import repair_mojibake


MAX_ARTICLE_PROBES = 12
MAX_LIST_CANDIDATES = 160
DATE_TEXT_PATTERN = re.compile(
    r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})"
)
SKIPPED_TITLE_PATTERN = re.compile(
    r"(?:首页|登录|注册|下载|关于我们|联系我们|广告|投稿|导航|更多|"
    r"上一页|下一页|版权所有|隐私|用户协议|APP|客户端)",
    re.IGNORECASE,
)
ASSET_SUFFIX_PATTERN = re.compile(
    r"\.(?:jpg|jpeg|png|gif|webp|svg|css|js|pdf|zip|rar|mp3|wav)(?:$|\?)",
    re.IGNORECASE,
)
NON_ARTICLE_PATH_PATTERN = re.compile(
    r"(?:/forum-\d+-\d+\.(?:html|php)|/tag/|/category/|/search"
    r"|/author/|/page/\d+|/space-uid-|/space-username-|/forum-)",
    re.IGNORECASE,
)
TRAILING_RELATIVE_TIME_PATTERN = re.compile(
    r"\s*(?:刚刚|\d+\s*(?:分钟|小时|天)前|昨天|前天)\s*$",
    re.IGNORECASE,
)
LABELLED_DATE_PATTERN = re.compile(
    r"(?:发布时间|发布日期|发表时间|发表于|"
    r"publish(?:ed)?(?:\s+time)?)"
    r"[^\d]{0,12}(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})",
    re.IGNORECASE,
)
PAGINATION_TEXT_PATTERN = re.compile(
    r"(?:下一页|下页|next|›|»|加载更多)",
    re.IGNORECASE,
)
PAGINATION_URL_PATTERN = re.compile(
    r"(?:[?&](?:page|p|paged)=\d+|/page/\d+/?|_\d+\.html?$)",
    re.IGNORECASE,
)


def _normalize_date(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        match = DATE_TEXT_PATTERN.search(text)
        if not match:
            return None
        year, month, day = map(int, match.groups())
        try:
            parsed = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _extract_json_ld_date(soup: BeautifulSoup) -> str | None:
    for node in soup.select('script[type="application/ld+json"]'):
        raw_text = node.get_text(" ", strip=True)
        if not raw_text:
            continue
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            match = re.search(
                r'"datePublished"\s*:\s*"([^"]+)"',
                raw_text,
                re.IGNORECASE,
            )
            if match:
                normalized = _normalize_date(match.group(1))
                if normalized:
                    return normalized
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for key in ("datePublished", "dateCreated", "dateModified"):
                normalized = _normalize_date(str(candidate.get(key, "")))
                if normalized:
                    return normalized
    return None


def _canonicalize_forum_thread_link(link: str) -> str:
    """把 Discuz 论坛跳转链接转换为稳定的主题链接。"""

    parsed = urlsplit(link)
    if "forum.php" not in parsed.path.casefold():
        return ""
    query = parse_qs(parsed.query)
    thread_id = str((query.get("tid") or [""])[0]).strip()
    if not thread_id.isdigit():
        return ""
    stable_query = urlencode({"mod": "viewthread", "tid": thread_id})
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, stable_query, "")
    )


def extract_article_publish_time(
    html_text: str,
    *,
    allow_unlabelled_fallback: bool = True,
) -> str | None:
    """从文章页的 meta、time 或 JSON-LD 中提取发布时间。"""

    soup = BeautifulSoup(html_text, "html.parser")
    for selector, attribute in (
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="article:published_time"]', "content"),
        ('meta[name="publishdate"]', "content"),
        ('meta[name="pubdate"]', "content"),
        ('meta[itemprop="datePublished"]', "content"),
        ("time[datetime]", "datetime"),
    ):
        node = soup.select_one(selector)
        if node is None:
            continue
        normalized = _normalize_date(str(node.get(attribute, "")))
        if normalized:
            return normalized
    json_ld_date = _extract_json_ld_date(soup)
    if json_ld_date:
        return json_ld_date
    # Discuz 的第一个帖子通常带有 authorposton 标识。完整日期可能只在
    # title 属性中，因此文本和属性都要检查。
    for node in soup.select('em[id^="authorposton"]'):
        values = [node.get_text(" ", strip=True)]
        values.extend(
            str(item.get("title", ""))
            for item in node.select("[title]")
        )
        normalized = _normalize_date(" ".join(values))
        if normalized:
            return normalized
    text = soup.get_text(" ", strip=True)
    labelled_match = LABELLED_DATE_PATTERN.search(text)
    if labelled_match:
        year, month, day = map(int, labelled_match.groups())
        try:
            return datetime(
                year,
                month,
                day,
                tzinfo=timezone.utc,
            ).isoformat(timespec="seconds")
        except ValueError:
            pass
    if allow_unlabelled_fallback:
        return _normalize_date(text[:5000])
    return None


def extract_article_title(html_text: str, source: str = "") -> str | None:
    """从文章页提取比列表卡片更干净的标题。"""

    soup = BeautifulSoup(html_text, "html.parser")
    candidates: list[str] = []
    for selector in (
        "h1",
        'meta[property="og:title"]',
        "title",
    ):
        node = soup.select_one(selector)
        if node is None:
            continue
        if selector.startswith("meta"):
            value = str(node.get("content", ""))
        else:
            value = node.get_text(" ", strip=True)
        title = repair_mojibake(" ".join(value.split()))
        if source:
            title = re.sub(
                rf"\s*[-_|·—]\s*{re.escape(source)}.*$",
                "",
                title,
                flags=re.IGNORECASE,
            )
        if len(title) >= 8:
            candidates.append(title)
    if not candidates:
        return None
    mojibake_pattern = re.compile(r"(?:锟|å|æ|ç|è|é)")
    return min(
        candidates,
        key=lambda value: (
            1000 if mojibake_pattern.search(value) else 0,
            len(value),
        ),
    )


def _same_site_url(base_url: str, link: str) -> bool:
    base_host = (urlsplit(base_url).hostname or "").removeprefix("www.")
    target_host = (urlsplit(link).hostname or "").removeprefix("www.")
    return not target_host or not base_host or target_host == base_host


def _next_page_url(html_text: str, page_url: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    for anchor in soup.select("a[href]"):
        text = " ".join(anchor.get_text(" ", strip=True).split())
        rel = " ".join(anchor.get("rel", []))
        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith(("#", "javascript:")):
            continue
        target = urljoin(page_url, href)
        if not _same_site_url(page_url, target):
            continue
        if (
            "next" in rel.casefold()
            or PAGINATION_TEXT_PATTERN.search(text)
            or PAGINATION_URL_PATTERN.search(target)
        ):
            return target
    return ""


def _render_with_chromium(url: str) -> str | None:
    """使用本机 Chromium 渲染 JavaScript 页面，失败时返回 None。"""

    executable = (
        os.getenv("CHROMIUM_BIN", "").strip()
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
    )
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [
                executable,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--virtual-time-budget=10000",
                "--dump-dom",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _extract_link_title(anchor: object) -> str:
    """优先使用 title 属性或标题节点，避免把整段摘要拼进标题。"""

    raw_title = str(getattr(anchor, "get", lambda *_: "")("title", "")).strip()
    if not raw_title:
        heading = getattr(anchor, "select_one", lambda *_: None)(
            "h1, h2, h3, h4, h5, [class*='title']"
        )
        if heading is not None:
            raw_title = heading.get_text(" ", strip=True)
    if not raw_title:
        raw_title = anchor.get_text(" ", strip=True)
    title = " ".join(raw_title.split())
    return TRAILING_RELATIVE_TIME_PATTERN.sub("", title).strip()


def _candidate_links(
    html_text: str,
    page_url: str,
    *,
    source: str,
    category: str,
) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(html_text, "html.parser")
    candidates: list[tuple[str, str, str]] = []
    seen_links: set[str] = set()
    for anchor in soup.select("a[href]"):
        title = _extract_link_title(anchor)
        if len(title) < 8 or SKIPPED_TITLE_PATTERN.search(title):
            continue
        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        link = urljoin(page_url, href)
        if not link.startswith(("http://", "https://")):
            continue
        if link == page_url or link in seen_links or not _same_site_url(page_url, link):
            continue
        path = urlsplit(link).path
        if ASSET_SUFFIX_PATTERN.search(path) or NON_ARTICLE_PATH_PATTERN.search(path):
            continue
        context_node = anchor.find_parent(["article", "li", "div", "section"])
        context = (
            " ".join(context_node.get_text(" ", strip=True).split())[:500]
            if context_node is not None
            else title
        )
        if not is_relevant_news(
            title,
            context,
            category=category,
            source=source,
        ):
            continue
        seen_links.add(link)
        candidates.append((title, link, context))
        if len(candidates) >= MAX_LIST_CANDIDATES:
            break
    return candidates


def fetch_direct_site(
    session: object,
    source: str,
    url: str,
    category: str = "音乐科技",
    *,
    max_pages: int = 1,
    max_articles: int = MAX_ARTICLE_PROBES,
    browser_fallback: bool = False,
    since: str = "",
) -> tuple[list[dict[str, str | None]], int, int]:
    """
    读取站点列表页，直到覆盖上次成功抓取时间。

    `since` 表示该来源上次成功抓取时间；列表页通常按时间倒序排列，
    一旦当前页出现早于该时间的文章，就可以停止继续翻页。
    """

    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            since_dt = since_dt.astimezone(timezone.utc)
        except ValueError:
            since_dt = None

    items: list[dict[str, str | None]] = []
    seen_candidates: set[str] = set()
    seen_pages: set[str] = set()
    total_candidates = 0
    page_url = url
    page_limit = max(1, max_pages)
    for page_index in range(1, page_limit + 1):
        if not page_url or page_url in seen_pages:
            break
        seen_pages.add(page_url)
        try:
            response = session.get(page_url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding
            page_text = response.text
            effective_page_url = response.url
        except Exception:
            rendered = (
                _render_with_chromium(page_url)
                if page_index == 1 and browser_fallback
                else None
            )
            if not rendered:
                raise
            page_text = rendered
            effective_page_url = page_url
        page_candidates = _candidate_links(
            page_text,
            effective_page_url,
            source=source,
            category=category,
        )
        if page_index == 1 and not page_candidates and browser_fallback:
            rendered = _render_with_chromium(url)
            if rendered:
                page_text = rendered
                page_candidates = _candidate_links(
                    page_text,
                    effective_page_url,
                    source=source,
                    category=category,
                )
        total_candidates += len(page_candidates)
        page_reached_since = False
        for candidate in page_candidates:
            title, link, context = candidate
            canonical_link = _canonicalize_forum_thread_link(link)
            candidate_key = canonical_link or link
            if candidate_key in seen_candidates:
                continue
            seen_candidates.add(candidate_key)
            is_forum_thread = bool(canonical_link)
            # 论坛版块页显示的是最后回复时间，不是主题发布时间。
            publish_time = (
                None if is_forum_thread else _normalize_date(context)
            )
            if not publish_time:
                try:
                    article_response = session.get(
                        link,
                        timeout=REQUEST_TIMEOUT_SECONDS,
                    )
                    article_response.raise_for_status()
                    article_response.encoding = (
                        article_response.apparent_encoding
                        or article_response.encoding
                    )
                    article_text = article_response.text
                    publish_time = extract_article_publish_time(
                        article_text,
                        allow_unlabelled_fallback=not is_forum_thread,
                    )
                    article_title = extract_article_title(article_text, source)
                    if article_title:
                        title = article_title
                except Exception:
                    publish_time = None
            if not publish_time:
                continue
            publish_dt = datetime.fromisoformat(
                publish_time.replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            if since_dt is not None and publish_dt <= since_dt:
                page_reached_since = True
            items.append(
                {
                    "title": title,
                    "link": canonical_link or link,
                    "source": source,
                    "publish_time": publish_time,
                    "summary": context,
                    "category": category,
                }
            )
            if len(items) >= max_articles:
                break
        if (
            len(page_candidates) == 0
            or len(items) >= max_articles
            or page_reached_since
        ):
            break
        page_url = _next_page_url(page_text, effective_page_url)

    unique_items = {
        str(item.get("link")): item
        for item in items
    }
    result_items = list(unique_items.values())
    return result_items, total_candidates, len(result_items)
