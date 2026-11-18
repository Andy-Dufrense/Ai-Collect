"""
RSS 抓取、解析与入库模块。

该模块不依赖 Flask，既可以被 app.py 手动触发，也可以由 cron 通过
fetch_news.py 独立运行。网络请求使用 requests，RSS 内容交给 feedparser。
"""

from __future__ import annotations

import calendar
import fcntl
import ipaddress
import logging
import os
import re
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import feedparser
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    GITHUB_DISCOVERY_ENABLED,
    GITHUB_RELEASE_REPOSITORIES,
    PROXY_AUTO_DISCOVERY,
    PROXY_DISCOVERY_PORTS,
    PROXY_PROBE_TIMEOUT_SECONDS,
    NEWS_DIRECT_FALLBACK,
    NEWS_PROXY,
    REQUEST_BACKOFF_SECONDS,
    REQUEST_RETRY_COUNT,
    REQUEST_TIMEOUT_SECONDS,
    RSS_SOURCES,
    SOGOU_MIN_INTERVAL_SECONDS,
    SOGOU_QUERY_DELAY_SECONDS,
    SOGOU_WECHAT_QUERIES,
    get_fetch_lock_path,
)
from database import (
    get_all_news,
    get_meta_value,
    initialize_database,
    purge_news_outside_retention,
    record_fetch_run,
    save_news_items,
    set_meta_value,
)
from news_filter import is_relevant_news
from github_discovery import fetch_github_discovery
from github_releases import fetch_github_releases
from sogou_wechat import fetch_sogou_query
from translation import translate_items


LOGGER = logging.getLogger(__name__)
MAX_SUMMARY_LENGTH = 500


class FetchAlreadyRunningError(RuntimeError):
    """已有抓取任务正在运行时抛出，避免两个任务同时下载和写库。"""


@dataclass
class FetchRoute:
    """一条可能可用的网络通道及其 requests 会话。"""

    label: str
    session: requests.Session


@dataclass
class FetchResult:
    """一次完整抓取任务的统计结果，供命令行和网页共同使用。"""

    fetched_at: datetime
    source_count: int
    successful_sources: int
    total_entries: int
    matched_entries: int
    new_count: int
    errors: list[str] = field(default_factory=list)

    @property
    def failed_sources(self) -> int:
        """网络或解析失败的数据源数量。"""

        return self.source_count - self.successful_sources


def _build_http_session(
    use_environment_proxy: bool = True,
    proxy_url: str | None = None,
    retry_count: int | None = None,
) -> requests.Session:
    """
    创建带自动重试的网络会话。

    requests 默认会读取 HTTP_PROXY/HTTPS_PROXY；如果设置了 NEWS_PROXY，
    则优先使用该代理地址。直连会话会关闭 trust_env，确保请求不会再次
    意外读取失效的环境代理。
    """

    session = requests.Session()
    session.trust_env = use_environment_proxy
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36 AI-Music-News/1.0"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }
    )

    if proxy_url:
        # 自动发现的代理必须显式传入，并关闭环境变量代理，防止被旧值覆盖。
        session.trust_env = False
        session.proxies.update({"http": proxy_url, "https": proxy_url})
    elif use_environment_proxy and NEWS_PROXY:
        session.proxies.update({"http": NEWS_PROXY, "https": NEWS_PROXY})

    effective_retry_count = (
        REQUEST_RETRY_COUNT if retry_count is None else retry_count
    )
    retry_strategy = Retry(
        total=effective_retry_count,
        connect=effective_retry_count,
        read=effective_retry_count,
        status=effective_retry_count,
        backoff_factor=REQUEST_BACKOFF_SECONDS,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _proxy_endpoint(proxy_url: str) -> tuple[str, int] | None:
    """从 HTTP(S) 代理 URL 中提取主机和端口，忽略账号密码等认证信息。"""

    normalized = proxy_url if "://" in proxy_url else f"http://{proxy_url}"
    try:
        from urllib.parse import urlsplit

        parsed = urlsplit(normalized)
        if not parsed.hostname:
            return None
        default_port = 443 if parsed.scheme == "https" else 80
        return parsed.hostname, parsed.port or default_port
    except ValueError:
        return None


def _tcp_reachable(host: str, port: int, timeout: float | None = None) -> bool:
    """快速检查 TCP 端口是否可连接，不发送 HTTP 请求。"""

    probe_timeout = timeout or PROXY_PROBE_TIMEOUT_SECONDS
    try:
        with socket.create_connection((host, port), timeout=probe_timeout):
            return True
    except OSError:
        return False


def _default_gateway() -> str | None:
    """从 Linux 路由表读取默认网关，找不到时返回 None。"""

    try:
        with open("/proc/net/route", encoding="utf-8") as route_file:
            for line in route_file:
                fields = line.split()
                if len(fields) < 3 or fields[1] != "00000000":
                    continue
                # /proc 中的 IPv4 地址使用小端十六进制表示。
                raw = bytes.fromhex(fields[2])
                return str(ipaddress.IPv4Address(raw[::-1]))
    except (OSError, ValueError):
        pass
    return None


def _arp_hosts() -> list[str]:
    """读取 ARP 表中的局域网主机，尤其是提供网页访问的 Windows 主机。"""

    hosts: list[str] = []
    try:
        with open("/proc/net/arp", encoding="utf-8") as arp_file:
            next(arp_file, None)
            for line in arp_file:
                fields = line.split()
                if len(fields) >= 4 and fields[3] != "00:00:00:00:00:00":
                    hosts.append(fields[0])
    except OSError:
        pass
    return hosts


def _proxy_candidates() -> list[str]:
    """
    汇总环境变量和自动发现的代理 URL。

    VMware NAT 中 Windows 主机通常是虚拟机的同网段地址，例如虚拟机为
    192.168.25.128、网关为 192.168.25.2 时，主机常见地址是 192.168.25.1。
    """

    candidates: list[str] = []
    for name in (
        "NEWS_PROXY",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
    ):
        value = os.getenv(name, "").strip()
        if value and not value.casefold().startswith("socks"):
            candidates.append(value)

    if PROXY_AUTO_DISCOVERY:
        hosts: list[str] = []
        gateway = _default_gateway()
        if gateway:
            try:
                network = ipaddress.ip_network(f"{gateway}/24", strict=False)
                # Windows 主机在 VMware 网段中经常使用 .1 地址。
                hosts.append(str(network.network_address + 1))
            except ValueError:
                pass
            hosts.append(gateway)
        hosts.extend(_arp_hosts())

        unique_hosts = list(dict.fromkeys(hosts))
        for host in unique_hosts:
            for port in PROXY_DISCOVERY_PORTS:
                candidates.append(f"http://{host}:{port}")

    # 去重但保留顺序：显式环境代理优先，自动发现其次。
    return list(dict.fromkeys(candidates))


def _discover_fetch_routes() -> list[FetchRoute]:
    """
    选择当前真实可连接的代理或直连通道。

    仅通过已打开的 TCP 端口进入候选列表，避免不断请求一个没有启动的代理。
    如果所有探测都失败，保留环境代理和直连两条诊断通道，让错误日志能够说明
    究竟是代理未启动还是外网根本不可达。
    """

    routes: list[FetchRoute] = []
    for proxy_url in _proxy_candidates():
        endpoint = _proxy_endpoint(proxy_url)
        if endpoint is None or not _tcp_reachable(*endpoint):
            continue

        # “端口开放”不代表它是 HTTP 代理。先用一个很小的公开页面验证协议，
        # 避免把 Windows 上无关的 8080 Web 服务误当成抓取代理。
        probe_session = _build_http_session(
            use_environment_proxy=False,
            proxy_url=proxy_url,
            retry_count=0,
        )
        try:
            probe_response = probe_session.get(
                "https://www.baidu.com",
                timeout=(2.0, 4.0),
            )
            proxy_is_valid = probe_response.status_code < 500
        except requests.RequestException:
            proxy_is_valid = False
        finally:
            probe_session.close()
        if not proxy_is_valid:
            continue

        routes.append(
            FetchRoute(
                label=f"代理 {endpoint[0]}:{endpoint[1]}",
                session=_build_http_session(
                    use_environment_proxy=False,
                    proxy_url=proxy_url,
                    retry_count=0,
                ),
            )
        )

    # 223.5.5.5 避免 DNS 故障干扰，只检查公网 TCP 出口是否可用。
    if NEWS_DIRECT_FALLBACK and _tcp_reachable(
        "223.5.5.5",
        443,
        timeout=1.0,
    ):
        routes.append(
            FetchRoute(
                label="直接连接",
                session=_build_http_session(use_environment_proxy=False),
            )
        )

    if not routes:
        routes.append(
            FetchRoute(
                label="环境代理（诊断）",
                session=_build_http_session(use_environment_proxy=True),
            )
        )
        if NEWS_DIRECT_FALLBACK:
            routes.append(
                FetchRoute(
                    label="直接连接（诊断）",
                    session=_build_http_session(use_environment_proxy=False),
                )
            )
    return routes


def _sogou_queries_due(now: datetime) -> bool:
    """根据上次尝试时间判断搜狗微信来源是否到达刷新时间。"""

    last_attempt = get_meta_value("sogou_last_attempt_at")
    if not last_attempt:
        return True
    try:
        last_time = datetime.fromisoformat(last_attempt)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        elapsed = (now - last_time.astimezone(timezone.utc)).total_seconds()
        return elapsed >= SOGOU_MIN_INTERVAL_SECONDS
    except (TypeError, ValueError):
        return True


def _clean_html(raw_html: str) -> str:
    """
    去掉 RSS 简介中的 HTML 标签，并还原转义字符，生成适合展示的纯文本。
    """

    if not raw_html:
        return ""

    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ")
    # 将换行、制表符和连续空格压缩为一个空格。
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_SUMMARY_LENGTH:
        text = text[:MAX_SUMMARY_LENGTH].rstrip() + "…"
    return text


def _parse_publish_time(entry: Any) -> str | None:
    """
    从 RSS 条目提取发布时间并统一保存成 UTC ISO 格式。

    不同 RSS 源使用 published_parsed、updated_parsed 等不同字段，
    因此按常见优先级逐个尝试。没有可用时间时返回 None。
    """

    for field_name in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed_time = getattr(entry, field_name, None)
        if not parsed_time:
            continue

        try:
            timestamp = calendar.timegm(parsed_time)
            publish_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            return publish_time.isoformat(timespec="seconds")
        except (OverflowError, TypeError, ValueError):
            continue
    return None


def _extract_summary(entry: Any) -> str:
    """依次从 summary、description、content 中提取简介。"""

    summary = getattr(entry, "summary", "")
    if not summary:
        summary = getattr(entry, "description", "")
    if not summary:
        contents = getattr(entry, "content", None) or []
        if contents and isinstance(contents, list):
            summary = contents[0].get("value", "")
    return _clean_html(str(summary))


def fetch_one_source(
    session: requests.Session,
    source: str,
    url: str,
    category: str = "RSS",
) -> tuple[list[dict[str, str | None]], int, int]:
    """
    抓取并解析一个 RSS 源。

    返回值依次为：通过过滤的资讯列表、RSS 总条目数、通过过滤的条目数。
    网络或解析错误会抛出异常，由上层按数据源分别捕获，避免一个源失败
    导致其他源也不能抓取。
    """

    LOGGER.info("开始抓取：%s (%s)", source, url)
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    # 把原始字节交给 feedparser，让它自行识别常见的 RSS 编码。
    parsed_feed = feedparser.parse(response.content)
    entries = parsed_feed.entries
    if not entries:
        detail = getattr(parsed_feed, "bozo_exception", "没有找到可解析的条目")
        raise ValueError(f"RSS 中没有可用条目：{detail}")

    matched_items: list[dict[str, str | None]] = []
    for entry in entries:
        title = _clean_html(str(getattr(entry, "title", "")))
        link = str(getattr(entry, "link", "")).strip()
        summary = _extract_summary(entry)

        # 标题、简介中任一位置同时覆盖两类关键词即可保留。
        if (
            not title
            or not link
            or not is_relevant_news(
                title,
                summary,
                category=category,
            )
        ):
            continue

        matched_items.append(
            {
                "title": title,
                "link": link,
                "source": source,
                "publish_time": _parse_publish_time(entry),
                "summary": summary,
                "category": category,
            }
        )

    LOGGER.info(
        "抓取完成：%s，共 %d 条，命中 %d 条",
        source,
        len(entries),
        len(matched_items),
    )
    return matched_items, len(entries), len(matched_items)


@contextmanager
def _exclusive_fetch_lock() -> Iterator[None]:
    """
    使用 Linux 文件锁保证整个系统中同一时刻只有一个抓取任务。

    后台自动进程和 Flask 手动按钮运行在不同的 Python 进程中，
    普通线程锁无法跨进程生效，因此这里使用 fcntl.flock。
    LOCK_NB 表示不排队等待：发现已有任务时立即返回，网页可以提示稍后再试。
    """

    lock_path = get_fetch_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise FetchAlreadyRunningError("已有抓取任务正在运行") from exc

        try:
            yield
        finally:
            # 无论抓取成功还是抛出异常，都要释放锁，避免后台永久卡死。
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def fetch_and_save_news() -> FetchResult:
    """
    获取跨进程锁后执行一次完整抓取。

    该函数是自动工作进程和网页手动同步共同调用的入口。
    """

    with _exclusive_fetch_lock():
        return _fetch_and_save_news_unlocked()


def _fetch_and_save_news_unlocked() -> FetchResult:
    """
    抓取全部 RSS 源、过滤并写入数据库。

    调用方已经持有抓取锁，因此内部函数不再处理并发。
    网页、自动工作进程和命令行使用完全相同的过滤与去重逻辑。
    """

    initialize_database()
    fetched_at = datetime.now(timezone.utc)
    all_matched_items: list[dict[str, str | None]] = []
    errors: list[str] = []
    successful_sources = 0
    total_entries = 0
    sogou_queries: tuple[str, ...] = ()
    sogou_attempted = 0
    github_attempted = 0
    github_discovery_attempted = 0

    routes = _discover_fetch_routes()
    LOGGER.info(
        "可用网络通道：%s",
        "、".join(route.label for route in routes),
    )
    try:
        for source_config in RSS_SOURCES:
            source_name = source_config["source"]
            source_url = source_config["url"]
            source_category = source_config.get("category", "RSS")
            source_errors: list[str] = []
            source_loaded = False

            for route in routes:
                LOGGER.info("%s 尝试通过%s抓取", source_name, route.label)
                try:
                    items, source_total, _source_matched = fetch_one_source(
                        route.session,
                        source_name,
                        source_url,
                        source_category,
                    )
                except requests.RequestException as exc:
                    route_error = f"{route.label} 失败：{exc}"
                    LOGGER.warning("%s：%s", source_name, route_error)
                    source_errors.append(route_error)
                    continue
                except (ValueError, TypeError, AttributeError) as exc:
                    message = f"{source_name} 解析失败：{exc}"
                    LOGGER.error(message)
                    errors.append(message)
                    break
                else:
                    source_loaded = True
                    LOGGER.info("%s 通过%s抓取成功", source_name, route.label)
                    break

            if not source_loaded:
                if source_errors:
                    message = (
                        f"{source_name} 所有网络通道均失败："
                        + "；".join(source_errors)
                    )
                    errors.append(message)
                continue

            successful_sources += 1
            total_entries += source_total
            all_matched_items.extend(items)

        # GitHub Releases 反映开源 AI 音频项目的版本、功能和实现更新。
        for repository in GITHUB_RELEASE_REPOSITORIES:
            github_attempted += 1
            source_name = f"GitHub · {repository}"
            source_errors = []
            source_loaded = False
            for route in routes:
                LOGGER.info("%s 尝试通过%s抓取", source_name, route.label)
                try:
                    items, source_total, _source_matched = fetch_github_releases(
                        route.session,
                        repository,
                    )
                except requests.RequestException as exc:
                    route_error = f"{route.label} 失败：{exc}"
                    LOGGER.warning("%s：%s", source_name, route_error)
                    source_errors.append(route_error)
                    continue
                except (ValueError, TypeError, AttributeError) as exc:
                    message = f"{source_name} 解析失败：{exc}"
                    LOGGER.error(message)
                    errors.append(message)
                    break
                else:
                    source_loaded = True
                    break
            if not source_loaded:
                if source_errors:
                    errors.append(
                        f"{source_name} 所有网络通道均失败："
                        + "；".join(source_errors)
                    )
                continue
            successful_sources += 1
            total_entries += source_total
            all_matched_items.extend(items)

        # 自动发现近期新建的 AI 音乐项目和相关 commit。固定项目 Releases
        # 只能看到“正式发版”，这一步补足尚未发版的新仓库和开发动态。
        if GITHUB_DISCOVERY_ENABLED:
            github_discovery_attempted = 1
            source_name = "GitHub 新项目与提交发现"
            source_errors = []
            source_loaded = False
            for route in routes:
                LOGGER.info("%s 尝试通过%s抓取", source_name, route.label)
                try:
                    items, source_total, _source_matched = (
                        fetch_github_discovery(
                            route.session,
                            now=fetched_at,
                        )
                    )
                except requests.RequestException as exc:
                    route_error = f"{route.label} 失败：{exc}"
                    LOGGER.warning("%s：%s", source_name, route_error)
                    source_errors.append(route_error)
                    continue
                except (ValueError, TypeError, AttributeError) as exc:
                    message = f"{source_name} 解析失败：{exc}"
                    LOGGER.error(message)
                    errors.append(message)
                    break
                else:
                    source_loaded = True
                    LOGGER.info(
                        "%s 通过%s抓取成功，命中 %d 条",
                        source_name,
                        route.label,
                        len(items),
                    )
                    break
            if not source_loaded:
                if source_errors:
                    errors.append(
                        f"{source_name} 所有网络通道均失败："
                        + "；".join(source_errors)
                    )
            else:
                successful_sources += 1
                total_entries += source_total
                all_matched_items.extend(items)

        # 搜狗微信单独限频：每 30 分钟最多刷新一次，查询之间等待 2 秒。
        if _sogou_queries_due(fetched_at):
            sogou_queries = SOGOU_WECHAT_QUERIES
            set_meta_value(
                "sogou_last_attempt_at",
                fetched_at.isoformat(timespec="seconds"),
            )
        else:
            LOGGER.info("搜狗微信尚未到达刷新时间，本轮跳过")

        for query_index, query in enumerate(sogou_queries):
            sogou_attempted += 1
            source_name = f"搜狗微信：{query}"
            source_errors = []
            source_loaded = False

            for route in routes:
                LOGGER.info("%s 尝试通过%s抓取", source_name, route.label)
                try:
                    items, source_total, _source_matched = fetch_sogou_query(
                        route.session,
                        query,
                    )
                except requests.RequestException as exc:
                    route_error = f"{route.label} 失败：{exc}"
                    LOGGER.warning("%s：%s", source_name, route_error)
                    source_errors.append(route_error)
                    continue
                except (ValueError, TypeError, AttributeError) as exc:
                    message = f"{source_name} 解析失败：{exc}"
                    LOGGER.error(message)
                    errors.append(message)
                    break
                else:
                    source_loaded = True
                    LOGGER.info(
                        "%s 通过%s抓取成功，结果 %d 条",
                        source_name,
                        route.label,
                        source_total,
                    )
                    break

            if not source_loaded:
                if source_errors:
                    errors.append(
                        f"{source_name} 所有网络通道均失败："
                        + "；".join(source_errors)
                    )
                # 首条搜索被限制时停止本轮剩余关键词，避免连续请求扩大封锁。
                break

            successful_sources += 1
            total_entries += source_total
            all_matched_items.extend(items)
            if query_index < len(sogou_queries) - 1:
                time.sleep(SOGOU_QUERY_DELAY_SECONDS)
    finally:
        for route in routes:
            route.session.close()

    # 所有命中条目最后一次性入库。即使多个源含有相同链接，
    # 数据库的 UNIQUE 索引也会自动完成第二轮去重。
    new_count = save_news_items(all_matched_items, fetched_at)

    # 本地网页与 GitHub Pages 共用中文标题缓存。后台会补齐历史英文标题，
    # 已有 title_zh 不重复调用翻译接口。
    try:
        stored_items = get_all_news()
        translated_count = translate_items(
            stored_items,
            existing_items=stored_items,
        )
        if translated_count:
            save_news_items(stored_items, fetched_at)
            LOGGER.info("新增中文标题翻译：%d 条", translated_count)
    except Exception:
        # 翻译服务故障不应影响资讯抓取和已有数据。
        LOGGER.exception("中文标题翻译失败，保留英文原标题")

    purged_count = purge_news_outside_retention()
    if purged_count:
        LOGGER.info("已清理超出保留期的资讯：%d 条", purged_count)

    result = FetchResult(
        fetched_at=fetched_at,
        source_count=(
            len(RSS_SOURCES)
            + github_attempted
            + github_discovery_attempted
            + sogou_attempted
        ),
        successful_sources=successful_sources,
        total_entries=total_entries,
        matched_entries=len(all_matched_items),
        new_count=new_count,
        errors=errors,
    )

    # 运行统计与新闻分开保存，网页据此提示最近一次任务是否有数据源失败。
    record_fetch_run(
        fetched_at=result.fetched_at,
        source_count=result.source_count,
        successful_sources=result.successful_sources,
        total_entries=result.total_entries,
        matched_entries=result.matched_entries,
        new_count=result.new_count,
        errors=result.errors,
    )

    LOGGER.info(
        "抓取任务结束：成功源 %d/%d，命中 %d 条，新增 %d 条",
        result.successful_sources,
        result.source_count,
        result.matched_entries,
        result.new_count,
    )
    return result
