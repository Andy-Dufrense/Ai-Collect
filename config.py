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
        "source": "Premier Guitar",
        "url": "https://www.premierguitar.com/rss",
        "category": "音乐科技",
        "focus": "hardware",
    },
    {
        "source": "Guitar.com",
        "url": "https://guitar.com/feed/",
        "category": "音乐科技",
        "focus": "hardware",
    },
    {
        "source": "Guitar Player",
        "url": "https://www.guitarplayer.com/rss",
        "category": "音乐科技",
        "focus": "hardware",
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
        "source": "Attack Magazine",
        "url": "https://www.attackmagazine.com/feed/",
        "category": "音乐科技",
    },
    {
        "source": "Bedroom Producers Blog",
        "url": "https://bedroomproducersblog.com/feed/",
        "category": "音乐科技",
        "focus": "software",
    },
    {
        "source": "VI-Control",
        "url": "https://vi-control.net/community/forums/-/index.rss",
        "category": "音乐科技",
        "focus": "software",
    },
    {
        "source": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "category": "音乐科技",
        "focus": "software",
    },
    {
        "source": "Matrixsynth",
        "url": "https://www.matrixsynth.com/feeds/posts/default",
        "category": "音乐科技",
        "focus": "hardware",
    },
    # 百度只使用宽泛方向词发现内容。具体硬件/软件分类在入库后完成。
    {
        "source": "百度新闻：小旭音乐",
        "url": (
            "https://news.baidu.com/ns?word=%E5%B0%8F%E6%97%AD%E9%9F%B3%E4%B9%90"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "音乐科技",
    },
    {
        "source": "百度新闻：Soomal",
        "url": (
            "https://news.baidu.com/ns?word=Soomal"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "音乐科技",
    },
    {
        "source": "百度新闻：音频应用",
        "url": (
            "https://news.baidu.com/ns?word=%E9%9F%B3%E9%A2%91%E5%BA%94%E7%94%A8"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "音乐科技",
    },
    {
        "source": "百度新闻：AI音乐",
        "url": (
            "https://news.baidu.com/ns?word=AI%E9%9F%B3%E4%B9%90"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "国内科技",
    },
    {
        "source": "百度新闻：AI音频",
        "url": (
            "https://news.baidu.com/ns?word=AI%E9%9F%B3%E9%A2%91"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "国内科技",
    },
    {
        "source": "百度新闻：音乐制作",
        "url": (
            "https://news.baidu.com/ns?word=%E9%9F%B3%E4%B9%90%E5%88%B6%E4%BD%9C"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "国内科技",
    },
    {
        "source": "百度新闻：音乐生成",
        "url": (
            "https://news.baidu.com/ns?word=%E9%9F%B3%E4%B9%90%E7%94%9F%E6%88%90"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "国内科技",
    },
    {
        "source": "百度新闻：乐器",
        "url": (
            "https://news.baidu.com/ns?word=%E4%B9%90%E5%99%A8"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "国内科技",
    },
    {
        "source": "百度新闻：合成器",
        "url": (
            "https://news.baidu.com/ns?word=%E5%90%88%E6%88%90%E5%99%A8"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "国内科技",
    },
    {
        "source": "百度新闻：音频",
        "url": (
            "https://news.baidu.com/ns?word=%E9%9F%B3%E9%A2%91"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "国内科技",
    },
    {
        "source": "百度新闻：AI编程",
        "url": (
            "https://news.baidu.com/ns?word=AI%E7%BC%96%E7%A8%8B"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "国内科技",
    },
    {
        "source": "百度新闻：AI模型",
        "url": (
            "https://news.baidu.com/ns?word=AI%E6%A8%A1%E5%9E%8B"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "国内科技",
    },
    {
        "source": "百度新闻：AI芯片",
        "url": (
            "https://news.baidu.com/ns?word=AI%E8%8A%AF%E7%89%87"
            "&tn=newsrss&sr=0&cl=2&rn=20&ct=0"
        ),
        "category": "国内科技",
    },
    {
        "source": "arXiv Sound",
        "url": "https://rss.arxiv.org/rss/cs.SD",
        "category": "AI音频研究",
    },
)


# 没有稳定 RSS 的站点逐个接入直接文章列表抓取。先确认一个站点的真实
# 链接、标题和发布时间都稳定，再扩展下一条。
DIRECT_SITE_SOURCES: Final[tuple[dict[str, str], ...]] = (
    {
        "source": "Midifan",
        "url": "https://www.midifan.com/",
        "category": "音乐科技",
        "provider": "html",
        "max_pages": "8",
        "max_articles": "200",
        "browser_fallback": "1",
    },
    {
        "source": "键盘中国",
        "url": "https://www.cnkeyboard.com/",
        "category": "音乐科技",
        "provider": "html",
        "max_pages": "8",
        "max_articles": "200",
        "browser_fallback": "1",
    },
    {
        "source": "小旭音乐",
        "url": "http://www.xiaoxumusic.com/",
        "category": "音乐科技",
        "provider": "html",
        "max_pages": "8",
        "max_articles": "200",
        "browser_fallback": "1",
    },
    {
        "source": "Soomal",
        "url": "http://www.soomal.com/",
        "fallback_urls": "https://soomal.com/,https://www.soomal.com/",
        "category": "音乐科技",
        "provider": "html",
        "max_pages": "8",
        "max_articles": "200",
        "browser_fallback": "1",
    },
    {
        "source": "我爱音频网",
        "url": "https://www.52audio.com/",
        "category": "音乐科技",
        "provider": "html",
        "max_pages": "8",
        "max_articles": "200",
    },
    {
        "source": "音频应用",
        "url": "https://www.audiobar.cn/",
        "fallback_urls": "https://www.audiobar.net/,http://www.audiobar.net/",
        "category": "音乐科技",
        "provider": "html",
        "max_pages": "8",
        "max_articles": "200",
    },
    {
        "source": "中国电子琴信息网",
        "url": "https://www.cndzq.com/",
        "category": "音乐科技",
        "provider": "html",
        "max_pages": "8",
        "max_articles": "200",
    },
    {
        "source": "叉烧网",
        "url": "https://www.exound.com/",
        "category": "音乐科技",
        "provider": "html",
        "max_pages": "8",
        "max_articles": "200",
        "browser_fallback": "1",
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


def _load_watched_article_urls() -> tuple[dict[str, str], ...]:
    """
    读取需要直接监控的微信公众号文章链接。

    微信公众号没有公开账号 Feed，搜狗也不能保证索引每一篇文章。对于已经
    确认的重要官方文章，可以通过此文件固定监控。链接会像普通来源一样每轮
    请求并在入库时去重，不会重复显示。
    """

    watch_path = BASE_DIR / "watched_articles.json"
    if not watch_path.exists():
        return ()
    try:
        raw_data = json.loads(watch_path.read_text(encoding="utf-8"))
        entries = raw_data.get("urls", []) if isinstance(raw_data, dict) else []
    except (OSError, json.JSONDecodeError, AttributeError):
        return ()

    result: list[dict[str, str]] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url", "")).strip()
        source = str(entry.get("source", "")).strip() or "微信公众号"
        if url.startswith(("https://mp.weixin.qq.com/",)):
            result.append({"url": url, "source": source})
    return tuple(result)


# 内置稳定来源 + 用户授权的公众号/自定义 RSS。
RSS_SOURCES: Final[tuple[dict[str, str], ...]] = (
    BUILT_IN_RSS_SOURCES
    + DIRECT_SITE_SOURCES
    + _load_custom_rss_sources()
)
WATCHED_ARTICLE_URLS: Final[tuple[dict[str, str], ...]] = (
    _load_watched_article_urls()
)


# 搜狗微信搜索使用公开结果页，不绕过登录、验证码或平台风控。
# 这里只负责用宽泛领域词发现内容，硬件/软件分类在入库阶段完成。
# 不在这里预先堆叠具体产品名，否则会漏掉尚未预见的新产品和新技术。
# 明确站点查询使用展示名称和站点首页。页面来源只显示站点名；Sogou
# 跳转链接无法解析成文章真实地址时，链接回退到对应站点首页。
SOGOU_EXPLICIT_SITES: Final[dict[str, dict[str, str]]] = {
    "Midifan": {"name": "Midifan", "url": "https://www.midifan.com/"},
    "叉烧网": {"name": "叉烧网", "url": "https://www.exound.com/"},
    "键盘中国": {"name": "键盘中国", "url": "https://www.cnkeyboard.com/"},
    "小旭音乐": {"name": "小旭音乐", "url": "https://www.xiaoxumusic.com/"},
    "KVR Audio": {"name": "KVR Audio", "url": "https://www.kvraudio.com/"},
    "Gearspace": {"name": "Gearspace", "url": "https://gearspace.com/"},
    "Production Expert": {
        "name": "Production Expert",
        "url": "https://www.production-expert.com/",
    },
    "Music Ally": {"name": "Music Ally", "url": "https://musically.com/"},
    "Keyboard Magazine": {
        "name": "Keyboard Magazine",
        "url": "https://www.keyboardmag.com/",
    },
    "Soomal": {"name": "Soomal", "url": "https://www.soomal.com/"},
    "我爱音频网": {"name": "我爱音频网", "url": "https://www.52audio.com/"},
    "音频应用": {"name": "音频应用", "url": "https://www.audiobar.cn/"},
    "吉他中国": {"name": "吉他中国", "url": "https://www.guitarchina.com/"},
    "中国电子琴信息网": {
        "name": "中国电子琴信息网",
        "url": "https://www.cndzq.com/",
    },
    "MIDI协会": {"name": "MIDI协会", "url": "https://midi.org/"},
    "刘润 AI音乐": {"name": "刘润", "url": "https://www.runliu.com/"},
    "黑马创业 AI音乐": {
        "name": "黑马创业",
        "url": "https://www.iheima.com/",
    },
}

SOGOU_SOURCE_QUERIES: Final[tuple[str, ...]] = tuple(
    SOGOU_EXPLICIT_SITES
)

AI_MUSIC_SEARCH_QUERIES: Final[tuple[str, ...]] = (
    "AI",
    "人工智能",
    "音乐",
    "音频",
    "乐器",
    "编曲",
    "混音",
    "母带",
    "MIDI",
    "音源",
    "插件",
    "录音",
    "声音设计",
    "AI音乐",
    "AI音频",
    "AI编曲",
    "AI作曲",
    "AI写歌",
    "AI混音",
    "AI母带",
    "AI分轨",
    "AI修音",
    "AI音频修复",
    "AI音效",
    "声音克隆",
    "音乐生成",
    "音乐大模型",
    "音频大模型",
    "AI MV",
    "音乐视频",
    "Suno",
    "Udio",
    "Stable Audio",
    "ElevenLabs Music",
    "AI编程",
    "AI芯片",
    "AI模型",
)

SOFTWARE_SEARCH_QUERIES: Final[tuple[str, ...]] = (
    "音乐软件",
    "音乐制作软件",
    "编曲软件",
    "混音软件",
    "母带软件",
    "修音软件",
    "制谱软件",
    "DAW",
    "DAW更新",
    "宿主软件",
    "VST3",
    "AUv3",
    "AAX",
    "CLAP插件",
    "音频插件",
    "音源插件",
    "效果器插件",
    "母带插件",
    "混音插件",
    "插件更新",
    "音源",
    "人声分离",
    "伴奏提取",
    "音频修复",
    "降噪插件",
    "混响插件",
    "Kontakt",
    "Serum",
)

HARDWARE_SEARCH_QUERIES: Final[tuple[str, ...]] = (
    "声卡",
    "音频接口",
    "USB声卡",
    "耳机",
    "监听耳机",
    "监听音箱",
    "音箱",
    "音响",
    "音频发射器",
    "无线音频",
    "接收器",
    "无线麦克风",
    "MIDI键盘",
    "MIDI控制器",
    "打击垫",
    "合成器",
    "鼓机",
    "电子鼓",
    "电钢琴",
    "舞台钢琴",
    "电子琴",
    "吉他",
    "钢琴",
    "琴弦",
    "智能乐器",
    "智能吉他",
    "智能钢琴",
)

SOGOU_KEYWORD_QUERIES: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        AI_MUSIC_SEARCH_QUERIES
        + SOFTWARE_SEARCH_QUERIES
        + HARDWARE_SEARCH_QUERIES
    )
)

SOGOU_WECHAT_QUERIES: Final[tuple[str, ...]] = (
    SOGOU_SOURCE_QUERIES + SOGOU_KEYWORD_QUERIES
)

# AI 与音乐/乐器关键词采用并集收录；交叉命中会在排行榜中获得额外加权。
AI_KEYWORDS: Final[tuple[str, ...]] = (
    "ai",
    "人工智能",
    "大模型",
    "aigc",
    "机器学习",
    "生成式人工智能",
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "deepseek",
    "通义千问",
    "豆包",
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
    "midi",
    "daw",
    "vst",
    "音频制作",
    "音频编辑",
    "音频插件",
    "音乐制作",
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
    "audio production",
    "audio editing",
    "audio plugin",
    "mixing",
    "mastering",
    "music generation",
    "generative audio",
    "ai audio",
    "audio generation",
    "sound design",
    "sound effect",
    "音乐视频",
    "ai mv",
    "music video",
    "视频配乐",
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
    "智能主机",
    "智能眼镜",
    "智能音箱",
    "智能穿戴",
    "可穿戴设备",
    "智能终端",
    "ai终端",
    "ai 终端",
    "端侧设备",
    "边缘计算设备",
    "芯片",
    "半导体",
    "显卡",
    "处理器",
    "加速卡",
    "推理卡",
    "ai服务器",
    "ai 服务器",
    "智算中心",
    "算力中心",
    "算力设备",
    "服务器",
    "光模块",
    "传感器",
    "机器人",
    "具身智能",
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
    "smart hub",
    "wearable device",
    "smart terminal",
    "edge device",
    "semiconductor",
    "gpu",
    "cpu",
    "accelerator card",
    "inference card",
    "ai server",
    "data center hardware",
    "optical module",
    "sensor",
    "robot",
    "robotics",
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
    "midi键盘",
    "midi 键盘",
    "pad控制器",
    "打击垫控制器",
    "daw控制器",
    "daw 控制器",
    "键盘控制器",
    "舞台键盘",
    "合成器",
    "硬件合成器",
    "模拟合成器",
    "数字合成器",
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
    "音频发射器",
    "无线音频发射器",
    "接收器",
    "麦克风",
    "话筒",
    "监听音箱",
    "监听音响",
    "音箱",
    "音响",
    "监听耳机",
    "耳机",
    "入耳式监听",
    "耳返",
    "耳放",
    "解码器",
    "dac",
    "音频采集卡",
    "音频线",
    "音频转接头",
    "调音台",
    "混音台",
    "音序器",
    "打击垫",
    "硬件工作站",
    "音乐工作站",
    "功放",
    "监听设备",
    "music hardware",
    "audio hardware",
    "instrument hardware",
    "midi controller",
    "midi keyboard",
    "midi keyboard controller",
    "drum pad",
    "pad controller",
    "daw controller",
    "stage keyboard",
    "keyboard synthesizer",
    "synthesizer",
    "synthesizers",
    "synth",
    "analog synth",
    "digital synth",
    "hardware synth",
    "modular synth",
    "eurorack",
    "modular",
    "drum machine",
    "sampler",
    "effects pedal",
    "guitar pedal",
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
    "audio cable",
    "audio adapter",
    "monitor speaker",
    "speaker",
    "studio headphones",
    "studio monitor",
    "amplifier",
    "music workstation",
    "groovebox",
    "sequencer",
    "digital instrument",
)

# 供筛选器和排序器共同使用，避免两个模块的硬件范围不一致。
DIRECTION_HARDWARE_KEYWORDS: Final[tuple[str, ...]] = (
    AI_HARDWARE_KEYWORDS + MUSIC_HARDWARE_KEYWORDS
)

# 所有来源共用的“发现词表”。RSS、搜狗微信、GitHub 和历史回填都应先用
# 这组宽领域信号发现 AI、音乐、乐器、音频、MIDI、混音等内容，随后再由
# content_classifier.py 判断硬件或软件。搜索词和分类词职责保持分离。
DISCOVERY_KEYWORDS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        AI_KEYWORDS + MUSIC_KEYWORDS + DIRECTION_HARDWARE_KEYWORDS
    )
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


# 每个搜狗查询读取前两页。宽领域词第一页通常被通用内容占满，
# 第二页能明显增加行业文章覆盖；查询之间仍保留较长冷却时间。
SOGOU_PAGES_PER_QUERY: Final[int] = max(
    1,
    int(_read_positive_number("SOGOU_PAGES_PER_QUERY", 2)),
)
SOGOU_PAGE_DELAY_SECONDS: Final[float] = max(
    0.5,
    _read_positive_number("SOGOU_PAGE_DELAY_SECONDS", 1.5),
)


# GitHub 查询窗口刻意大于 12 小时刷新间隔，避免 Actions 延迟时漏数据。
# 两次查询可能命中同一项目，入库时会按唯一链接自动去重。
GITHUB_REPOSITORY_LOOKBACK_DAYS: Final[int] = max(
    1,
    int(_read_positive_number("GITHUB_REPOSITORY_LOOKBACK_DAYS", 30)),
)
GITHUB_COMMIT_LOOKBACK_DAYS: Final[int] = max(
    1,
    int(_read_positive_number("GITHUB_COMMIT_LOOKBACK_DAYS", 7)),
)

# GitHub 不是更新日志仓库。只有获得一定关注度的新项目，以及来自较高热度
# 仓库的重大功能/模型/架构变化才值得进入资讯列表。阈值可通过环境变量
# 调整，避免把 0～几颗星的一次性练手项目误当成行业动态。
GITHUB_NEW_REPOSITORY_MIN_STARS: Final[int] = max(
    0,
    int(_read_positive_number("GITHUB_NEW_REPOSITORY_MIN_STARS", 8)),
)
GITHUB_COMMIT_MIN_STARS: Final[int] = max(
    0,
    int(_read_positive_number("GITHUB_COMMIT_MIN_STARS", 30)),
)
GITHUB_MAX_NEW_REPOSITORIES_PER_RUN: Final[int] = max(
    1,
    int(_read_positive_number("GITHUB_MAX_NEW_REPOSITORIES_PER_RUN", 10)),
)
GITHUB_MAX_SIGNIFICANT_COMMITS_PER_RUN: Final[int] = max(
    1,
    int(_read_positive_number("GITHUB_MAX_SIGNIFICANT_COMMITS_PER_RUN", 10)),
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
SOGOU_MAX_QUERIES_PER_RUN: Final[int] = max(
    1,
    int(_read_positive_number("SOGOU_MAX_QUERIES_PER_RUN", 32)),
)
SOGOU_FILTER_VERSION: Final[str] = "4"

# 百度新闻搜索页会在一批连续请求后触发安全验证。最多保留 9 个宽方向
# 查询，并在查询之间等待 3 秒；相同查询组合 6 小时内不重复请求。
BAIDU_MIN_INTERVAL_SECONDS: Final[float] = max(
    3600.0,
    _read_positive_number("BAIDU_MIN_INTERVAL_SECONDS", 21600.0),
)
BAIDU_QUERY_DELAY_SECONDS: Final[float] = max(
    1.0,
    _read_positive_number("BAIDU_QUERY_DELAY_SECONDS", 3.0),
)
BAIDU_BLOCK_COOLDOWN_SECONDS: Final[float] = max(
    600.0,
    _read_positive_number("BAIDU_BLOCK_COOLDOWN_SECONDS", 21600.0),
)

# 频繁执行 manage.sh restart 时，如果上一轮刚完成，不立即再次抓取全部来源。
# 这可以避免用户在调试网页时反复触发百度、Synthanatomy 等来源的限流。
STARTUP_FETCH_MIN_INTERVAL_SECONDS: Final[float] = max(
    60.0,
    _read_positive_number("STARTUP_FETCH_MIN_INTERVAL_SECONDS", 900.0),
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

