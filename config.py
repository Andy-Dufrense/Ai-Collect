"""
AI + 音乐资讯收集系统的集中配置。

把容易变化的配置放在这个文件里，后续增加 RSS 源或修改关键词时，
通常只需要编辑这里，不需要改动抓取、存储和网页代码。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final


# 项目根目录始终取 config.py 所在目录。
# 这样无论从哪个目录启动脚本，数据库、模板等资源都能被正确定位。
BASE_DIR: Final[Path] = Path(__file__).resolve().parent
DATA_DIR: Final[Path] = BASE_DIR / "data"


def get_database_path() -> Path:
    """
    返回 SQLite 数据库文件路径。

    默认使用项目内的 data/news.db。测试或部署时也可以通过环境变量
    NEWS_DB_PATH 指定另一个路径，避免测试数据污染正式数据库。
    """

    configured_path = os.getenv("NEWS_DB_PATH", "").strip()
    if not configured_path:
        return DATA_DIR / "news.db"

    database_path = Path(configured_path).expanduser()
    # 如果环境变量写的是相对路径，就相对于项目根目录解释，结果更可预测。
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path
    return database_path


def get_fetch_lock_path() -> Path:
    """
    返回抓取任务锁文件路径。

    锁文件与数据库放在同一目录。多个后台命令或运维任务同时运行时，
    只有一个任务能够真正访问 RSS，避免重复请求与并写入。
    """

    return get_database_path().with_suffix(".fetch.lock")


# 当前网络环境下可直接访问的 RSS 源。
#
# 原需求中的 rsshub.app 公共实例在当前网络连接超时，不适合作为生产数据入口。
# 这里优先使用媒体官方 RSS；Bing News RSS 用于补充“AI + 音乐/吉他”的搜索结果。
# 后续要增加公众号或其他 RSS 时，按相同格式追加字典即可。
BUILT_IN_RSS_SOURCES: Final[tuple[dict[str, str], ...]] = (
    {
        "source": "IT之家24小时榜",
        "url": "https://www.ithome.com/rss/",
        "category": "国内科技",
    },
    {
        "source": "爱范儿",
        "url": "https://www.ifanr.com/feed",
        "category": "国内科技",
    },
    {
        "source": "少数派",
        "url": "https://sspai.com/feed",
        "category": "国内科技",
    },
    {
        "source": "钛媒体",
        "url": "https://www.tmtpost.com/rss.xml",
        "category": "国内科技",
    },
    {
        "source": "极客公园",
        "url": "https://www.geekpark.net/rss",
        "category": "国内科技",
    },
    {
        "source": "雷锋网",
        "url": "https://www.leiphone.com/feed",
        "category": "国内科技",
    },
    {
        "source": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "category": "国际科技",
    },
    {
        "source": "Music Business Worldwide",
        "url": "https://www.musicbusinessworldwide.com/feed/",
        "category": "音乐科技",
    },
    {
        "source": "MusicRadar",
        "url": "https://www.musicradar.com/feeds/all",
        "category": "音乐科技",
    },
    {
        "source": "Guitar World",
        "url": "https://www.guitarworld.com/feeds/all",
        "category": "音乐科技",
    },
    {
        "source": "Synthtopia",
        "url": "https://www.synthtopia.com/feed/",
        "category": "音乐科技",
    },
    {
        "source": "CDM",
        "url": "https://cdm.link/feed/",
        "category": "音乐科技",
    },
    {
        "source": "MusicTech",
        "url": "https://musictech.com/feed/",
        "category": "音乐科技",
    },
    {
        "source": "Rekkerd",
        "url": "https://rekkerd.org/feed/",
        "category": "音乐科技",
    },
    {
        "source": "Synthanatomy",
        "url": "https://www.synthanatomy.com/feed/",
        "category": "音乐科技",
    },
    {
        "source": "arXiv Sound",
        "url": "https://rss.arxiv.org/rss/cs.SD",
        "category": "AI音频研究",
    },
)


# 通过 GitHub Releases API 跟踪开源 AI 音频项目的功能与版本更新。
GITHUB_RELEASE_REPOSITORIES: Final[tuple[str, ...]] = (
    "facebookresearch/audiocraft",
    "Stability-AI/stable-audio-tools",
    "magenta/magenta",
    "riffusion/riffusion",
    "facebookresearch/demucs",
    "sonic-pi-net/sonic-pi",
)


# GitHub 自动发现会搜索近期新建的 AI 音乐仓库，以及相关 commit。
# 查询窗口刻意大于 12 小时刷新间隔，避免 GitHub Actions 延迟时漏掉内容；
# 重叠结果会在入库前按链接去重，不会重复显示。
GITHUB_DISCOVERY_ENABLED: Final[bool] = os.getenv(
    "GITHUB_DISCOVERY_ENABLED",
    "1",
).strip().casefold() not in {"0", "false", "no", "off"}


def _load_custom_rss_sources() -> tuple[dict[str, str], ...]:
    """
    读取用户增加的授权 RSS 源。

    典型用途是 WeRSS 等公众号桥接服务：用户在服务端扫码授权后取得专属 RSS，
    再写入 custom_sources.json。这里只读取配置，不处理第三方账号密码。
    """

    custom_path = BASE_DIR / "custom_sources.json"
    if not custom_path.exists():
        return ()

    try:
        raw_data = json.loads(custom_path.read_text(encoding="utf-8"))
        entries = raw_data.get("sources", []) if isinstance(raw_data, dict) else raw_data
    except (OSError, json.JSONDecodeError, AttributeError):
        return ()

    valid_sources: list[dict[str, str]] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source", "")).strip()
        url = str(entry.get("url", "")).strip()
        category = str(entry.get("category", "授权 RSS")).strip() or "授权 RSS"
        if source and url.startswith(("http://", "https://")):
            valid_sources.append(
                {"source": source, "url": url, "category": category}
            )
    return tuple(valid_sources)


# 内置稳定来源 + 用户授权的公众号/自定义 RSS。
RSS_SOURCES: Final[tuple[dict[str, str], ...]] = (
    BUILT_IN_RSS_SOURCES + _load_custom_rss_sources()
)


# 搜狗微信搜索使用公开结果页，不绕过登录、验证码或平台风控。
# 如果搜狗要求验证，抓取器会跳过本类来源并在日志中说明，不影响 RSS。
SOGOU_WECHAT_QUERIES: Final[tuple[str, ...]] = (
    "AI音乐",
    "AI吉他",
    "AI钢琴 乐理",
    "AI音频制作",
    "AI硬件 音乐",
    "智能乐器",
    "音频硬件",
)

# AI 与音乐/乐器关键词采用并集收录；交叉命中会在排行榜中获得额外加权。
AI_KEYWORDS: Final[tuple[str, ...]] = (
    "ai",
    "人工智能",
    "大模型",
    "aigc",
    "机器学习",
    "生成式人工智能",
    "suno",
    "udio",
    "riffusion",
    "mubert",
    "artificial intelligence",
    "machine learning",
    "large language model",
    "generative ai",
)

MUSIC_KEYWORDS: Final[tuple[str, ...]] = (
    "音乐",
    "吉他",
    "编曲",
    "歌手",
    "乐器",
    "音色",
    "音效",
    "歌曲",
    "作曲",
    "旋律",
    "混音",
    "母带",
    "钢琴",
    "乐理",
    "贝斯",
    "鼓手",
    "说唱",
    "声乐",
    "合成器",
    "音频生成",
    "音频创作",
    "ai音频",
    "ai 音频",
    "music",
    "guitar",
    "song",
    "singer",
    "musician",
    "instrument",
    "piano",
    "music theory",
    "bass",
    "drums",
    "rapper",
    "vocal",
    "synthesizer",
    "music production",
    "music generation",
    "generative audio",
    "ai audio",
    "audio generation",
    "sound design",
    "sound effect",
)

# 与 AI 或音乐方向直接相关的硬件词。
# 普通手机、机械键盘、家电等只有出现“AI/音乐/乐器/音频”等方向词时才收录，
# 避免单纯按“硬件”二字把所有消费电子产品都抓进来。
AI_HARDWARE_KEYWORDS: Final[tuple[str, ...]] = (
    "ai硬件",
    "ai 硬件",
    "ai芯片",
    "ai 芯片",
    "人工智能硬件",
    "端侧ai",
    "边缘ai",
    "推理芯片",
    "神经网络处理器",
    "张量处理器",
    "智能硬件",
    "智能眼镜",
    "智能音箱",
    "智能穿戴",
    "可穿戴设备",
    "ai pc",
    "ai手机",
    "ai 手机",
    "ai眼镜",
    "ai 眼镜",
    "ai耳机",
    "ai 耳机",
    "ai hardware",
    "ai chip",
    "ai accelerator",
    "edge ai device",
    "neural processing unit",
    "tensor processing unit",
    "npu",
    "tpu",
    "ai pc",
    "ai phone",
    "ai glasses",
    "ai earbuds",
    "smart glasses",
    "smart speaker",
    "wearable device",
)

MUSIC_HARDWARE_KEYWORDS: Final[tuple[str, ...]] = (
    "乐器硬件",
    "音乐硬件",
    "音频硬件",
    "智能乐器",
    "电子乐器",
    "数字乐器",
    "midi",
    "midi控制器",
    "midi 控制器",
    "键盘控制器",
    "合成器",
    "模块合成器",
    "模块化合成器",
    "鼓机",
    "采样器",
    "效果器",
    "吉他效果器",
    "贝斯效果器",
    "效果踏板",
    "音频接口",
    "声卡",
    "麦克风",
    "监听音箱",
    "监听耳机",
    "调音台",
    "混音台",
    "音序器",
    "打击垫",
    "music hardware",
    "audio hardware",
    "instrument hardware",
    "midi controller",
    "synthesizer",
    "modular synth",
    "eurorack",
    "drum machine",
    "sampler",
    "effects pedal",
    "guitar pedal",
    "audio interface",
    "sound card",
    "microphone",
    "studio monitor",
    "groovebox",
    "sequencer",
    "digital instrument",
)

# 供筛选器和排序器共同使用，避免两个模块的硬件范围不一致。
DIRECTION_HARDWARE_KEYWORDS: Final[tuple[str, ...]] = (
    AI_HARDWARE_KEYWORDS + MUSIC_HARDWARE_KEYWORDS
)


TECH_KEYWORDS: Final[tuple[str, ...]] = (
    "科技",
    "技术",
    "软件",
    "硬件",
    "芯片",
    "处理器",
    "显卡",
    "服务器",
    "手机",
    "电脑",
    "平板",
    "操作系统",
    "系统更新",
    "开发",
    "算法",
    "模型",
    "网络安全",
    "安全漏洞",
    "人工智能",
    "technology",
    "tech",
    "software",
    "hardware",
    "chip",
    "processor",
    "gpu",
    "cpu",
    "operating system",
    "security",
    "cybersecurity",
    "developer",
    "api",
    "cloud",
    "ios",
    "android",
    "windows",
    "linux",
    "macos",
    "server",
    "phone",
    "computer",
    "tablet",
    "data breach",
)


def _read_positive_number(name: str, default: float) -> float:
    """
    从环境变量读取正数配置。

    例如把超时时间误写成 0 或普通文字时，自动回退到安全默认值，
    这样一个小配置错误不会让整个抓取任务永久失败。
    """

    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        value = float(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


# GitHub 查询窗口刻意大于 12 小时刷新间隔，避免 Actions 延迟时漏数据。
# 两次查询可能命中同一项目，入库时会按唯一链接自动去重。
GITHUB_REPOSITORY_LOOKBACK_DAYS: Final[int] = max(
    1,
    int(_read_positive_number("GITHUB_REPOSITORY_LOOKBACK_DAYS", 14)),
)
GITHUB_COMMIT_LOOKBACK_DAYS: Final[int] = max(
    1,
    int(_read_positive_number("GITHUB_COMMIT_LOOKBACK_DAYS", 3)),
)


# 搜狗对连续搜索较敏感。默认每 12 小时才刷新一次微信来源，
# 查询之间再等待 2 秒，避免每 5 分钟触发访问限制。
SOGOU_MIN_INTERVAL_SECONDS: Final[float] = max(
    60.0,
    _read_positive_number("SOGOU_MIN_INTERVAL_SECONDS", 43200.0),
)
SOGOU_QUERY_DELAY_SECONDS: Final[float] = max(
    1.0,
    _read_positive_number("SOGOU_QUERY_DELAY_SECONDS", 2.0),
)

HISTORY_BACKFILL_DAYS: Final[int] = max(
    1,
    int(_read_positive_number("HISTORY_BACKFILL_DAYS", 60)),
)
HISTORY_BACKFILL_DELAY_SECONDS: Final[float] = max(
    2.0,
    _read_positive_number("HISTORY_BACKFILL_DELAY_SECONDS", 5.0),
)
HISTORY_BACKFILL_QUERIES: Final[tuple[str, ...]] = (
    "AI 音乐",
    "AI音乐",
    "AI音乐 软件 工具",
)
ON_DEMAND_DATE_BACKFILL_SECONDS: Final[float] = max(
    600.0,
    _read_positive_number("ON_DEMAND_DATE_BACKFILL_SECONDS", 21600.0),
)


# 单次网络请求的最长等待时间，单位是秒。
REQUEST_TIMEOUT_SECONDS: Final[float] = _read_positive_number(
    "NEWS_REQUEST_TIMEOUT",
    20.0,
)

# 网络临时失败时的重试次数（只重试 GET 请求）。
REQUEST_RETRY_COUNT: Final[int] = int(
    _read_positive_number("NEWS_REQUEST_RETRIES", 2)
)

# RSSHub 或网络服务暂时不可用时，程序会按指数退避策略等待后重试。
REQUEST_BACKOFF_SECONDS: Final[float] = _read_positive_number(
    "NEWS_REQUEST_BACKOFF",
    0.8,
)

# 整轮抓取完全失败时不必等待完整的 5 分钟，网络恢复后应在 60 秒内自动重试。
AUTO_FETCH_RETRY_SECONDS: Final[float] = max(
    15.0,
    _read_positive_number("AUTO_FETCH_RETRY_SECONDS", 60.0),
)

# 后台抓取固定在北京时间每天 00:00 和 12:00 执行。
AUTO_FETCH_TIME_ZONE: Final[str] = os.getenv(
    "AUTO_FETCH_TIME_ZONE",
    "Asia/Shanghai",
)
AUTO_FETCH_SCHEDULE_HOURS: Final[tuple[int, ...]] = (0, 12)
AUTO_FETCH_HEARTBEAT_MAX_AGE_SECONDS: Final[int] = 13 * 3600
NEWS_RETENTION_DAYS: Final[int] = max(
    1,
    int(_read_positive_number("NEWS_RETENTION_DAYS", 60)),
)

# requests 会自动识别 HTTP_PROXY / HTTPS_PROXY。
# 某些 cron 环境不会继承终端的代理变量，因此这里额外支持统一的 NEWS_PROXY。
# 示例：NEWS_PROXY=http://127.0.0.1:7890
NEWS_PROXY: Final[str] = os.getenv("NEWS_PROXY", "").strip()

# 当系统代理连接失败时，是否自动绕过代理再尝试一次直连。
# 默认开启可避免“代理软件忘记启动”导致整个资讯系统完全不可用。
# 如果当前网络必须通过代理，可设置 NEWS_DIRECT_FALLBACK=0 强制关闭直连。
NEWS_DIRECT_FALLBACK: Final[bool] = os.getenv(
    "NEWS_DIRECT_FALLBACK",
    "1",
).strip().casefold() not in {"0", "false", "no", "off"}

# 自动发现代理：检查 VMware 网段中的 Windows 主机及常见本地代理端口。
# 只要代理软件已开启“允许局域网连接”，后台就能自行选中它。
PROXY_AUTO_DISCOVERY: Final[bool] = os.getenv(
    "PROXY_AUTO_DISCOVERY",
    "1",
).strip().casefold() not in {"0", "false", "no", "off"}

PROXY_DISCOVERY_PORTS: Final[tuple[int, ...]] = (
    7890,
    7897,
    10809,
    10808,
    1080,
    8888,
    8080,
)

# 探测端口时只等待很短时间，避免一个未启动的代理拖慢整轮抓取。
PROXY_PROBE_TIMEOUT_SECONDS: Final[float] = _read_positive_number(
    "PROXY_PROBE_TIMEOUT_SECONDS",
    0.5,
)

# 网页时间按这个时区展示；数据库内部仍统一保存 UTC 时间，便于稳定排序。
DISPLAY_TIME_ZONE: Final[str] = os.getenv("DISPLAY_TIME_ZONE", "Asia/Shanghai")

# 默认监听所有网卡，便于从 Windows 主机通过虚拟机 IP 访问网页。
# 如果只希望虚拟机内部访问，可以设置 FLASK_HOST=127.0.0.1。
FLASK_HOST: Final[str] = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT: Final[int] = int(_read_positive_number("FLASK_PORT", 5000))

