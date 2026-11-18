"""
把资讯分为“硬件相关”和“软件相关”。

一条资讯允许同时命中两类。例如硬件控制器发布时同步升级配套 App，
它既会出现在硬件筛选中，也会出现在软件筛选中。
"""

from __future__ import annotations

import re

from config import DIRECTION_HARDWARE_KEYWORDS
from news_filter import find_matched_keywords


# 分类版本会写入数据库。以后如果大幅修改分类规则，把版本加一，
# 程序会在下一次启动时自动重新分类已有资讯。
CONTENT_CLASSIFICATION_VERSION = "4"


SOFTWARE_CLASSIFICATION_KEYWORDS = (
    "软件",
    "应用",
    "app",
    "工具",
    "平台",
    "插件",
    "云端",
    "网页版",
    "网页应用",
    "模型",
    "算法",
    "代码",
    "开源",
    "接口",
    "工作流",
    "更新",
    "升级",
    "版本",
    "固件",
    "生成",
    "编曲",
    "混音",
    "母带",
    "分轨",
    "音频编辑",
    "虚拟乐器",
    "音源",
    "效果器软件",
    "daw",
    "vst",
    "vst2",
    "vst3",
    "au plugin",
    "aax",
    "plugin",
    "plugins",
    "software",
    "application",
    "platform",
    "model",
    "algorithm",
    "code",
    "open source",
    "open-source",
    "repository",
    "commit",
    "api",
    "sdk",
    "workflow",
    "update",
    "upgrade",
    "version",
    "firmware",
    "virtual instrument",
    "audio editor",
    "music generation",
    "audio generation",
    "ai audio",
    "cloud",
    "web app",
)

# 标题中明确出现这些实体词时，优先视为硬件。它们比 RSS 简介中的
# 泛泛提及“设备”更可靠，用于处理“软件合成器”和“合成器硬件”的差异。
TITLE_HARDWARE_HINTS = (
    "硬件",
    "设备",
    "控制器",
    "音频接口",
    "声卡",
    "麦克风",
    "监听音箱",
    "监听耳机",
    "功放",
    "踏板",
    "模块",
    "鼓机",
    "调音台",
    "混音台",
    "打击垫",
    "硬件工作站",
    "hardware",
    "device",
    "controller",
    "audio interface",
    "sound card",
    "microphone",
    "studio monitor",
    "amplifier",
    "pedal",
    "module",
    "drum machine",
    "mixer",
)

TITLE_SOFTWARE_HINTS = (
    "软件",
    "应用",
    "app",
    "插件",
    "模型",
    "算法",
    "代码",
    "开源",
    "工作流",
    "更新",
    "升级",
    "版本",
    "固件",
    "虚拟乐器",
    "音源",
    "daw",
    "vst",
    "plugin",
    "software",
    "application",
    "model",
    "algorithm",
    "code",
    "open source",
    "open-source",
    "api",
    "sdk",
    "workflow",
    "update",
    "upgrade",
    "firmware",
    "virtual instrument",
)

TITLE_SOFTWARE_ONLY_HINTS = (
    "软件",
    "应用",
    "app",
    "网页版",
    "web app",
    "插件",
    "plugin",
    "daw",
    "vst",
    "software",
    "application",
    "virtual instrument",
    "音源",
)

GENERAL_NON_PRODUCT_HARDWARE_PATTERN = re.compile(
    r"(?:"
    r"表示|认为|想象空间|商业机会|行业趋势|生态伙伴|高管|访谈"
    r"|早报|日报|周报|早知道|盘点|总结|观察|评论"
    r"|thinks|believes|interview|roundup|daily briefing"
    r")",
    re.IGNORECASE,
)


def classify_content_flags(
    title: str,
    summary: str = "",
    *,
    category: str = "",
    source: str = "",
) -> tuple[bool, bool]:
    """
    返回 ``(is_hardware, is_software)``。

    标题信号权重高于简介，因为 RSS 简介经常包含导航、推荐阅读或其他
    产品的附带描述。两个分数都达到阈值时，保留“软硬结合”双重分类。
    """

    title_text = title.casefold()
    summary_text = summary.casefold()
    combined_text = f"{title_text} {summary_text}"

    hardware_title = find_matched_keywords(
        title_text,
        DIRECTION_HARDWARE_KEYWORDS,
    )
    hardware_summary = find_matched_keywords(
        summary_text,
        DIRECTION_HARDWARE_KEYWORDS,
    )
    software_title = find_matched_keywords(
        title_text,
        SOFTWARE_CLASSIFICATION_KEYWORDS,
    )
    software_summary = find_matched_keywords(
        summary_text,
        SOFTWARE_CLASSIFICATION_KEYWORDS,
    )

    hardware_score = len(hardware_title) * 4 + len(hardware_summary)
    software_score = len(software_title) * 4 + len(software_summary)

    title_has_hardware_hint = bool(
        find_matched_keywords(title_text, TITLE_HARDWARE_HINTS)
    )
    title_has_software_hint = bool(
        find_matched_keywords(title_text, TITLE_SOFTWARE_HINTS)
    )
    title_has_strong_software_hint = bool(
        find_matched_keywords(title_text, TITLE_SOFTWARE_ONLY_HINTS)
    )

    # 开源项目、commit 和开发分类默认属于软件，但保留命中明确硬件词的例外。
    if category == "AI音频开发" or source.startswith("GitHub"):
        software_score += 4

    is_hardware = hardware_score >= 2
    is_software = software_score >= 2

    # “software synthesizer”“合成器插件”等标题虽然包含硬件词表中的
    # synthesizer/合成器，但明确写了软件，且没有实体设备提示，应只归软件类。
    if title_has_strong_software_hint and not title_has_hardware_hint:
        is_hardware = False
        is_software = True

    # 明确写的是硬件或实体设备，即使简介顺便提到软件，也不能被错误排除。
    if title_has_hardware_hint and not title_has_software_hint:
        is_hardware = True

    # 综合科技媒体中的“人物观点、早报汇总、行业评论”经常顺便提到
    # 手机、机器人或算力设备，但文章主体并不是硬件产品。此类内容只允许
    # 根据标题中的直接硬件描述分类，不能因为 RSS 简介提到了设备就误标。
    if category in {"国内科技", "国际科技"}:
        title_hardware_direction = bool(
            title_has_hardware_hint
            or find_matched_keywords(
                title_text,
                DIRECTION_HARDWARE_KEYWORDS,
            )
        )
        if (
            not title_hardware_direction
            or GENERAL_NON_PRODUCT_HARDWARE_PATTERN.search(title_text)
        ):
            is_hardware = False

    return is_hardware, is_software
