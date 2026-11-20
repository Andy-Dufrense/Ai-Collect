"""来源名称展示规则。"""

from __future__ import annotations

from urllib.parse import urlsplit


GENERIC_SEARCH_SOURCE_PREFIXES = (
    "搜狗搜索",
    "搜狗微信",
)


def display_source_name(source: str) -> str:
    """
    返回页面展示用的来源名称。

    搜狗只是发现通道，不是内容发布者。没有解析出真实公众号名称时，
    页面显示“微信文章”，不再显示“搜狗搜索/搜狗微信”。
    """

    value = str(source or "").strip()
    if not value:
        return "未知来源"
    for prefix in ("百度新闻：", "百度新闻:"):
        if value.startswith(prefix):
            return value[len(prefix):].strip() or "新闻搜索"
    if any(value.startswith(prefix) for prefix in GENERIC_SEARCH_SOURCE_PREFIXES):
        return "微信文章"
    return value


def is_safe_http_url(value: str) -> bool:
    """只接受可直接打开的 HTTP(S) 文章链接。"""

    candidate = str(value or "").strip()
    if not candidate or any(char.isspace() for char in candidate):
        return False
    try:
        parsed = urlsplit(candidate)
        # 访问 port 会触发合法端口校验，非法端口按危险链接处理。
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.casefold() in {"http", "https"}
        and bool(parsed.hostname)
    )
