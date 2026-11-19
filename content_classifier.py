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
CONTENT_CLASSIFICATION_VERSION = "12"


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
    "音乐视频",
    "ai mv",
    "music video",
    "视频生成",
    "cloud",
    "web app",
    "fork",
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
    "daw controller",
    "midi keyboard",
    "drum pad",
    "pad controller",
    "stage keyboard",
    "keyboard synthesizer",
    "audio interface",
    "audio transmitter",
    "wireless audio transmitter",
    "audio receiver",
    "sound card",
    "microphone",
    "mic",
    "headphones",
    "in-ear monitor",
    "iem",
    "headphone amplifier",
    "dac",
    "audio capture card",
    "speaker",
    "studio monitor",
    "amplifier",
    "pedal",
    "module",
    "drum machine",
    "mixer",
)

# 这些词组出现在简介中时，通常已经足以确认文章主体是实体设备。
# 使用完整产品词而不是泛泛的 hardware/device，减少软件文章误判。
SUMMARY_STRONG_HARDWARE_HINTS = (
    "audio interface",
    "audio transmitter",
    "wireless audio transmitter",
    "audio receiver",
    "sound card",
    "microphone",
    "mic",
    "headphones",
    "in-ear monitor",
    "iem",
    "headphone amplifier",
    "dac",
    "audio capture card",
    "speaker",
    "daw controller",
    "midi controller",
    "midi keyboard",
    "drum pad",
    "pad controller",
    "hardware synthesizer",
    "analog synthesizer",
    "stage keyboard",
    "groovebox",
    "drum machine",
    "effects pedal",
    "eurorack",
    "studio monitor",
    "音频接口",
    "声卡",
    "麦克风",
    "监听音箱",
    "监听耳机",
    "midi控制器",
    "midi键盘",
    "打击垫",
    "硬件合成器",
    "音频发射器",
)

# 琴弦、吉他、钢琴等词既可能出现在艺人故事中，也可能是实体乐器新品。
# 只有同时出现发布、评测、上市等产品动作时，才补为硬件。
INSTRUMENT_PRODUCT_TERMS = (
    "吉他",
    "电吉他",
    "民谣吉他",
    "古典吉他",
    "钢琴",
    "电子琴",
    "电钢琴",
    "小提琴",
    "尤克里里",
    "琴弦",
    "乐器",
    "guitar",
    "electric guitar",
    "acoustic guitar",
    "bass guitar",
    "piano",
    "digital piano",
    "stage piano",
    "keyboard",
    "violin",
    "ukulele",
    "guitar strings",
)

INSTRUMENT_PRODUCT_ACTION_PATTERN = re.compile(
    r"(?:"
    r"\b(?:launch(?:es|ed)?|release(?:s|d)?|announc(?:es|ed)?|"
    r"introduc(?:es|ed|ing)|unveil(?:s|ed)?|recreat(?:es|ed)|"
    r"review(?:s|ed)?|hands-on|first look|now available|shipping|"
    r"pre-?order|new)\b"
    r"|发布|推出|上市|新品|评测|上手|开箱|预售|亮相"
    r")",
    re.IGNORECASE,
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
    "plugins",
    "daw",
    "vst",
    "vst2",
    "vst3",
    "aax",
    "software",
    "application",
    "virtual instrument",
    "音源",
    "ios",
    "ipados",
    "android",
    "iphone",
    "ipad",
    "mac",
    "windows",
    "browser",
    "web",
    "ableton live",
    "logic pro",
    "fl studio",
    "kontakt",
    "max for live",
    "fork",
)

GENERAL_NON_PRODUCT_HARDWARE_PATTERN = re.compile(
    r"(?:"
    r"表示|认为|想象空间|商业机会|行业趋势|生态伙伴|高管|访谈"
    r"|创始人|联合创始人|演讲|实录|专访|对话|大会|峰会"
    r"|CoRL|NeurIPS|ICML|CVPR|ACL"
    r"|早报|日报|周报|早知道|盘点|总结|观察|评论"
    r"|thinks|believes|interview|keynote|fireside|roundup|daily briefing"
    r")",
    re.IGNORECASE,
)


def classify_content_flags(
    title: str,
    summary: str = "",
    *,
    category: str = "",
    source: str = "",
    focus: str = "",
) -> tuple[bool, bool]:
    """
    返回 ``(is_hardware, is_software)``。

    标题信号权重高于简介，因为 RSS 简介经常包含导航、推荐阅读或其他
    产品的附带描述。两个分数都达到阈值时，保留“软硬结合”双重分类。
    """

    title_text = title.casefold()
    summary_text = summary.casefold()
    combined_text = f"{title_text} {summary_text}"

    # “hardware-inspired”只是软件功能描述，不代表文章主体是硬件实体。
    hardware_hint_text = re.sub(
        r"hardware[\s-]*inspired|受硬件启发",
        "",
        title_text,
        flags=re.IGNORECASE,
    )

    hardware_title = find_matched_keywords(
        hardware_hint_text,
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
        find_matched_keywords(hardware_hint_text, TITLE_HARDWARE_HINTS)
    )
    title_has_software_hint = bool(
        find_matched_keywords(title_text, TITLE_SOFTWARE_HINTS)
    )
    title_has_strong_software_hint = bool(
        find_matched_keywords(title_text, TITLE_SOFTWARE_ONLY_HINTS)
    )
    summary_has_strong_software_hint = bool(
        find_matched_keywords(summary_text, TITLE_SOFTWARE_ONLY_HINTS)
    )
    summary_has_strong_hardware_hint = bool(
        find_matched_keywords(summary_text, SUMMARY_STRONG_HARDWARE_HINTS)
    )
    has_instrument_product = bool(
        find_matched_keywords(combined_text, INSTRUMENT_PRODUCT_TERMS)
        and INSTRUMENT_PRODUCT_ACTION_PATTERN.search(title_text)
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

    # RSS 摘要明确写 plugin/VST/AU/App/fork 时，即使标题只写 Synthesizer，
    # 也应归软件。若标题同时有 controller/interface/hardware 等实体提示，
    # 则保留硬件或软硬结合分类。
    if summary_has_strong_software_hint and not title_has_hardware_hint:
        is_hardware = False
        is_software = True

    # 标题可能是产品评测名，实体类型只写在简介里，例如
    # “Shure MV7i review” + “audio interface”。没有软件限定词时补为硬件。
    if (
        summary_has_strong_hardware_hint
        and not title_has_strong_software_hint
    ):
        is_hardware = True

    if has_instrument_product and not title_has_strong_software_hint:
        is_hardware = True

    if re.search(
        r"hardware[\s-]*inspired|受硬件启发",
        title_text,
        flags=re.IGNORECASE,
    ):
        is_hardware = False
        is_software = True

    # 软件信号明显强于硬件信号，且标题没有实体设备词时，不能因为
    # synthesizer/sampler/MIDI 等兼容词就把插件、App 或网页工具归为硬件。
    if software_score > hardware_score and not title_has_hardware_hint:
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

    # 百度“合成器新品”“音频接口新品”等检索入口已经明确表达分类意图。
    # 只有标题没有明确的插件/App/软件信号时，才使用来源焦点补足分类。
    if focus == "hardware" and not (
        title_has_strong_software_hint
        or summary_has_strong_software_hint
        or GENERAL_NON_PRODUCT_HARDWARE_PATTERN.search(title_text)
    ):
        is_hardware = True
    elif focus == "software" and not title_has_hardware_hint:
        is_software = True

    # arXiv 声音与音乐计算论文通常是算法/模型研究，除非标题明确写硬件。
    if category == "AI音频研究" and not title_has_hardware_hint:
        is_hardware = False
        is_software = True

    return is_hardware, is_software
