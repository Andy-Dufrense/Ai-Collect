"""
“AI + 音乐”资讯过滤器。

系统接受 AI、音乐或乐器任一领域的内容；同时命中多个领域时，由排名模块
提高相关度。英文关键词按完整单词匹配，避免把 “daily” 中的 “ai” 误判成
人工智能资讯；中文关键词直接进行包含匹配。所有比较均忽略大小写。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from config import (
    AI_HARDWARE_KEYWORDS,
    AI_KEYWORDS,
    DIRECTION_HARDWARE_KEYWORDS,
    DISCOVERY_KEYWORDS,
    MUSIC_KEYWORDS,
)
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
    "ipo",
    "套现",
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

PRICE_OR_PROMOTION_PATTERN = re.compile(
    r"(?:"
    r"[¥$€£]\s*\d+"
    r"|\d+(?:\.\d+)?\s*(?:元|万元|美元|英镑|欧元)"
    r"|\d+(?:\.\d+)?\s*亿\s*美元"
    r"|\d+(?:\.\d+)?\s*%\s*(?:off|折扣)"
    r"|save\s+(?:up\s+to\s+)?\d+(?:\.\d+)?\s*%"
    r"|\d+(?:\.\d+)?\s*%\s+on\b"
    r"|售价|首发价|起售价|到手价|券后价|价格|定价|折扣|优惠|促销"
    r"|降价|涨价|黑五|清仓|甩卖|特价|秒杀|满减|折后|优惠券"
    r"|限时|限免|免费领|会员|订阅|会员费|廉价|便宜|预算"
    r"|gift\s+(?:drop|guide|ideas?)"
    r"|\b(?:price|pricing|discount|coupon|deal|deals|sale|bundle|"
    r"membership|subscriptions?|clearance|markdown|budget)\b"
    r"|black friday|cyber monday|prime day|limited time"
    r")",
    re.IGNORECASE,
)

# GitHub commit 搜索会被批量账号投递的代理、直播引流和电商广告污染。
# 这些标题通常包含“更新、接口、软件”等泛词，必须在入库前单独排除。
GITHUB_SPAM_PATTERN = re.compile(
    r"(?:"
    r"住宅(?:动态)?IP|海外(?:住宅|家庭|专线|直播|电商)|代理(?:线路|服务)?"
    r"|跨境电商|数据标注|多机位直播|推流软件|账号|登录态|多开"
    r"|机房段|出口线路|出口(?:IP|城市|参数)|固定IP|包月线路|带宽"
    r"|家宽|纯净家宽|线路扩容|频道运营|多频道|红人合作|续费"
    r"|平台判成|机器行为|海外.{0,8}(?:平台|频道|视频|社交)"
    r"|residential\s+proxy|proxy\s+service|multi[-\s]?account"
    r"|traffic\s+bot|click\s+farm"
    r")",
    re.IGNORECASE,
)

SOGOU_LOW_VALUE_PATTERN = re.compile(
    r"(?:"
    r"报名|报考|招募|招聘|招生|培训|课程|证书|认证|考试|考中心"
    r"|大赛|比赛|音乐节|音乐季|音乐会|演唱会|展演|活动预告|直播预告"
    r"|论坛|峰会|大会|沙龙|研讨会|日报|早报|晚报|周报|榜单|榜第|合集|收藏"
    r"|生日快乐|人物|访谈|观点|评论|解读|真相|怎么看|为什么|是什么|效果如何"
    r"|政策|细则|补贴|税务|交税|税率|股价|科技股|融资|估值"
    r"|图谱|产业链|市场格局|指数|研究报告"
    r"|免费获取|免费领取|扫码|加群|进群|领取"
    r")",
    re.IGNORECASE,
)

GENERAL_TECH_ROUNDUP_PATTERN = re.compile(
    r"(?:早报|日报|晚报|周报|盘点|汇总|一览|速览|简报)",
    re.IGNORECASE,
)

GENERAL_BUSINESS_ENTERTAINMENT_NOISE = (
    "卸任",
    "离职",
    "上任",
    "任命",
    "接任",
    "辞职",
    "跳槽",
    "诉讼",
    "起诉",
    "融资",
    "估值",
    "股价",
    "财报",
    "收购",
    "裁员",
    "演唱会",
    "巡演",
    "女团",
    "明星",
    "代言",
    "榜单",
    "ceo",
    "chairman",
    "executive",
    "layoffs",
)

GITHUB_PIRACY_PATTERN = re.compile(
    r"(?:"
    r"\b(?:cracked|crack|keygen|pirated|torrent|activation key|license key)\b"
    r"|how\s+to\s+get\s+fl\s+studio"
    r"|fl\s+studio.*producer\s+2026"
    r"|ableton.*portable\s+mode"
    r")",
    re.IGNORECASE,
)

SOGOU_CONCRETE_SOFTWARE_SIGNALS = (
    "软件",
    "应用",
    "app",
    "插件",
    "工具",
    "平台",
    "功能",
    "生成",
    "编曲",
    "作曲",
    "写歌",
    "混音",
    "母带",
    "分轨",
    "音色",
    "音源",
    "提示词",
    "工作流",
    "开发",
    "编程",
    "代码",
    "开源",
    "接口",
    "api",
    "sdk",
    "daw",
    "vst",
    "midi",
    "音频",
    "声音",
    "视频",
    "模型发布",
    "模型更新",
    "开源模型",
)


def is_github_spam_text(text: str) -> bool:
    """判断文本是否属于 GitHub 搜索中出现过的批量引流垃圾内容。"""

    return (
        GITHUB_SPAM_PATTERN.search(text) is not None
        or GITHUB_PIRACY_PATTERN.search(text) is not None
    )


def is_promotional_title(*text_parts: str) -> bool:
    """判断标题是否属于价格、折扣、会员或限时促销内容。"""

    title_text = _normalize_text(
        " ".join(part for part in text_parts if part)
    )
    return PRICE_OR_PROMOTION_PATTERN.search(title_text) is not None


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
    has_hardware_signal = bool(
        find_matched_keywords(combined_text, DIRECTION_HARDWARE_KEYWORDS)
    )
    has_discovery_signal = bool(
        find_matched_keywords(combined_text, DISCOVERY_KEYWORDS)
    )
    title_for_review = str(text_parts[0]) if text_parts else ""
    if is_learned_excluded(title_for_review):
        return False

    # 噪音词只检查标题。简介中顺带提到诉讼或融资不应错误删除技术文章。
    title_text = _normalize_text(" ".join(text_parts[:1]))
    if is_promotional_title(title_text):
        return False
    if (
        category in {"音乐科技", "搜狗微信"}
        and find_matched_keywords(title_text, GOSSIP_OR_BUSINESS_NOISE)
    ):
        return False

    # 人工保留白名单只保护音乐科技文章，价格和优惠仍优先生效。
    if category == "音乐科技" and is_learned_accepted(title_for_review):
        return True

    title_ai = bool(find_matched_keywords(title_text, AI_KEYWORDS))
    title_music = bool(find_matched_keywords(title_text, MUSIC_KEYWORDS))
    title_hardware = bool(
        find_matched_keywords(title_text, DIRECTION_HARDWARE_KEYWORDS)
    )
    title_software = bool(
        find_matched_keywords(title_text, SOFTWARE_SIGNAL_KEYWORDS)
    )

    # 音乐科技媒体保留音乐、AI 或明确软件功能内容。
    if category in {"音乐科技", "AI音频研究", "AI音频开发"}:
        return (
            has_music_keyword
            or has_ai_keyword
            or has_software_signal
            or has_hardware_signal
        )

    # 综合科技媒体只保留标题涉及 AI、音乐或方向硬件的内容。
    # 普通硬件不会因为“硬件”二字直接通过。
    if category in {"国内科技", "国际科技"}:
        if GENERAL_TECH_ROUNDUP_PATTERN.search(title_text):
            return False
        if find_matched_keywords(
            title_text,
            GENERAL_BUSINESS_ENTERTAINMENT_NOISE,
        ):
            return False
        title_ai_hardware = bool(
            find_matched_keywords(title_text, AI_HARDWARE_KEYWORDS)
        )
        title_concrete_software = bool(
            find_matched_keywords(
                title_text,
                SOGOU_CONCRETE_SOFTWARE_SIGNALS,
            )
        )
        return (
            title_music
            or title_ai_hardware
            or (title_ai and title_hardware)
            or (title_ai and title_concrete_software)
        )

    # 搜狗微信允许 AI 或音乐单类内容。
    if category == "搜狗微信":
        compact_title = re.sub(r"\s+", "", title_text)
        if len(compact_title) < 10:
            return False
        if SOGOU_LOW_VALUE_PATTERN.search(title_text):
            return False
        title_concrete_software = bool(
            find_matched_keywords(
                title_text,
                SOGOU_CONCRETE_SOFTWARE_SIGNALS,
            )
        )
        has_real_direction = (
            title_ai and (title_music or title_hardware)
        ) or (
            title_music and (title_hardware or title_software)
        ) or (
            title_ai and title_concrete_software
        )
        return has_real_direction

    return has_discovery_signal
