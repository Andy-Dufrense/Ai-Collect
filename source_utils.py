"""来源名称展示规则。"""

from __future__ import annotations


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
