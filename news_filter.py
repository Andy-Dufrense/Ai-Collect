"""
“AI + 音乐”资讯过滤器。

系统接受 AI、音乐或乐器任一领域的内容；同时命中多个领域时，由排名模块
提高相关度。英文关键词按完整单词匹配，避免把 “daily” 中的 “ai” 误判成
人工智能资讯；中文关键词直接进行包含匹配。所有比较均忽略大小写。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from config import AI_KEYWORDS, MUSIC_KEYWORDS, TECH_KEYWORDS
from filter_learning import is_learned_accepted, is_learned_excluded


SOFTWARE_SIGNAL_KEYWORDS = (
    "软件",
    "应用",
    "工具",
    "平台",
    "功能",
    "更新",
    "插件",
    "工作流",
    "接口",
    "模型",
    "算法",
    "生成",
    "编曲",
    "混音",
    "母带",
    "分轨",
    "调音",
    "音色",
    "合成器",
    "效果器",
    "音效",
    "教程",
    "攻略",
    "体验",
    "玩法",
    "开发",
    "实现",
    "software",
    "application",
    "app",
    "tool",
    "plugin",
    "plugins",
    "platform",
    "feature",
    "update",
    "workflow",
    "connector",
    "integration",
    "api",
    "model",
    "algorithm",
    "generate",
    "generation",
    "editing",
    "mixing",
    "mastering",
    "stems",
    "midi",
    "daw",
    "synthesizer",
    "effect",
    "effects",
    "processor",
    "reverb",
    "modulation",
    "sequencer",
    "looper",
    "sampler",
    "virtual instrument",
    "logic pro",
    "ableton",
    "dsp",
    "sound design",
    "tutorial",
    "how to",
    "production",
    "composition",
    "developer",
)

GOSSIP_OR_BUSINESS_NOISE = (
    "卸任",
    "离职",
    "上任",
    "任命",
    "接任",
    "辞职",
    "跳槽",
    "诉讼",
    "起诉",
    "被诉",
    "和解",
    "版权纠纷",
    "收购",
    "融资",
    "估值",
    "股价",
    "财报",
    "裁员",
    "格莱美",
    "巡演",
    "演唱会",
    "致敬",
    "纪念",
    "去世",
    "逝世",
    "八卦",
    "绯闻",
    "榜单",
    "优惠",
    "折扣",
    "黑五",
    "降价",
    "促销",
    "表示",
    "认为",
    "回应争议",
    "steps down",
    "resign",
    "appointed",
    "appointment",
    "lawsuit",
    "sues",
    "sued",
    "settlement",
    "copyright dispute",
    "acquisition",
    "acquires",
    "funding",
    "raises",
    "valuation",
    "earnings",
    "layoffs",
    "chairman",
    "ceo",
    "executive",
    "grammy",
    "tour",
    "concert",
    "tribute",
    "quiz",
    "obituary",
    "dies",
    "dead",
    "sale",
    "deal",
    "deals",
    "bundle",
    "price",
    "black friday",
    "discount",
    "thinks",
    "believes",
    "criticizes",
    "slams",
)

def _normalize_text(value: str) -> str:
    """统一大小写并压缩多余空白，减少无意义的匹配差异。"""

    return re.sub(r"\s+", " ", value.casefold()).strip()


def _contains_keyword(text: str, keyword: str) -> bool:
    """
    判断文本是否包含指定关键词。

    对纯英文/数字关键词使用边界检查。例如：
    - “AI 音乐”和“AI音乐”会匹配 ai；
    - “daily news”不会因为里面恰好有 ai 两个字母而误匹配。
    中文关键词没有空格边界，因此直接使用普通子串匹配。
    """

    normalized_keyword = keyword.casefold()
    if re.fullmatch(r"[a-z0-9]+", normalized_keyword):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return normalized_keyword in text


def find_matched_keywords(
    text: str,
    keywords: Iterable[str],
) -> tuple[str, ...]:
    """返回文本实际命中的关键词，便于调试过滤结果。"""

    normalized_text = _normalize_text(text)
    return tuple(
        keyword
        for keyword in keywords
        if _contains_keyword(normalized_text, keyword)
    )


def is_relevant_news(
    *text_parts: str,
    category: str = "",
) -> bool:
    """
    判断一条资讯是否属于 AI、音乐或乐器相关领域。

    传入的多个文本片段（通常是标题和简介）会先合并再判断。
    标题命中了 AI、简介命中了音乐，同样算同时满足条件。
    编辑规则：
    - AI、技术、音乐或乐器命中任一类即可收录；
    - 高管、诉讼、融资、明星、巡演、购物和纯观点等噪音排除；
    """

    combined_text = _normalize_text(" ".join(part for part in text_parts if part))
    has_ai_keyword = bool(find_matched_keywords(combined_text, AI_KEYWORDS))
    has_music_keyword = bool(find_matched_keywords(combined_text, MUSIC_KEYWORDS))
    has_software_signal = bool(
        find_matched_keywords(combined_text, SOFTWARE_SIGNAL_KEYWORDS)
    )
    has_tech_keyword = bool(find_matched_keywords(combined_text, TECH_KEYWORDS))

    title_for_review = str(text_parts[0]) if text_parts else ""
    # 人工保留白名单只保护容易因词形变化被误伤的音乐科技文章。
    # 综合科技来源仍须标题涉及 AI 或音乐，避免永久保留普通手机/硬件新闻。
    if category == "音乐科技" and is_learned_accepted(title_for_review):
        return True
    if is_learned_excluded(title_for_review):
        return False

    # 噪音词只检查标题。简介中顺带提到诉讼或融资不应错误删除技术文章。
    title_text = _normalize_text(" ".join(text_parts[:1]))
    if find_matched_keywords(title_text, GOSSIP_OR_BUSINESS_NOISE):
        return False

    title_ai = bool(find_matched_keywords(title_text, AI_KEYWORDS))
    title_music = bool(find_matched_keywords(title_text, MUSIC_KEYWORDS))
    title_software = bool(
        find_matched_keywords(title_text, SOFTWARE_SIGNAL_KEYWORDS)
    )

    # 音乐科技媒体保留音乐、AI 或明确软件功能内容。
    if category == "音乐科技":
        return (
            has_music_keyword
            or has_ai_keyword
            or has_software_signal
        )

    # 综合科技媒体允许标题涉及音乐，或正文确实涉及 AI 技术。
    if category in {"国内科技", "国际科技"}:
        return title_music or (has_ai_keyword and has_tech_keyword)

    # 搜狗微信允许 AI 或音乐单类内容。
    if category == "搜狗微信":
        return has_ai_keyword or has_music_keyword

    return has_ai_keyword or has_music_keyword
