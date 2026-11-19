"""
常驻后台自动抓取进程。

只要通过 manage.sh 启动后端，这个进程就会常驻，并在北京时间每天
00:00 和 12:00 自动执行：

    下载 RSS -> 双重关键词过滤 -> SQLite 去重入库

Flask 不参与抓取，只读取数据库。因此后台更新时网页无需重启，
刷新浏览器即可看到新数据。
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import AUTO_FETCH_RETRY_SECONDS
from database import (
    clear_meta_value,
    clear_worker_heartbeat,
    initialize_database,
    set_meta_value,
    set_worker_heartbeat,
)
from rss_fetcher import FetchAlreadyRunningError, FetchResult, fetch_and_save_news
from scheduler_utils import next_scheduled_refresh


LOGGER = logging.getLogger("auto_fetcher")
STOP_EVENT = threading.Event()
PROJECT_DIR = Path(__file__).resolve().parent
TRANSLATION_LOG = PROJECT_DIR / "data" / "translation.log"


def launch_background_translation() -> None:
    """
    启动独立的限速翻译进程。

    翻译不是抓取成功的前置条件。进程被 detach 后，即使接口很慢也不会
    占用抓取锁或阻止下一轮自动抓取。
    """

    TRANSLATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with TRANSLATION_LOG.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [
                sys.executable,
                str(PROJECT_DIR / "scripts" / "translate_missing.py"),
                "--limit",
                "80",
            ],
            cwd=PROJECT_DIR,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )


def _handle_stop_signal(signum: int, _frame: object) -> None:
    """
    收到 SIGTERM 或 Ctrl+C 时设置停止事件。

    使用事件等待而不是长时间 sleep，可以让进程在停止命令发出后迅速退出。
    """

    LOGGER.info("收到停止信号 %s，正在结束自动抓取进程", signum)
    STOP_EVENT.set()


def run_fetch_cycle(
    fetch_function: Callable[[], FetchResult] = fetch_and_save_news,
    translation_launcher: Callable[[], None] | None = None,
) -> FetchResult | None:
    """
    执行一轮抓取并更新心跳。

    单轮网络或解析异常不会让常驻进程退出，下一轮仍会继续尝试。
    fetch_function 参数允许测试传入模拟函数，不访问真实网络。
    """

    set_worker_heartbeat(datetime.now(timezone.utc))
    try:
        result = fetch_function()
    except FetchAlreadyRunningError:
        # 其他抓取任务正在进行时，本轮让路，下一轮按计划继续。
        LOGGER.info("已有抓取任务运行，本轮自动抓取跳过")
        return None
    except Exception:
        LOGGER.exception("本轮自动抓取发生异常，将在下一轮继续重试")
        return None
    finally:
        # 心跳在成功、跳过或失败后都更新，表示工作进程本身仍然存活。
        set_worker_heartbeat(datetime.now(timezone.utc))

    LOGGER.info(
        "自动抓取完成：成功源 %d/%d，命中 %d 条，新增 %d 条",
        result.successful_sources,
        result.source_count,
        result.matched_entries,
        result.new_count,
    )
    for error in result.errors:
        LOGGER.warning("数据源错误：%s", error)
    if translation_launcher is not None:
        try:
            translation_launcher()
            LOGGER.info("已启动后台标题翻译任务")
        except Exception:
            # 翻译失败不能影响已经完成的抓取任务。
            LOGGER.exception("后台标题翻译任务启动失败")
    return result


def run_forever(
    fetch_function: Callable[[], FetchResult] = fetch_and_save_news,
    *,
    run_immediately: bool = False,
    translation_launcher: Callable[[], None] | None = None,
) -> None:
    """按北京时间 00:00、12:00 调度，直到收到停止信号。"""

    initialize_database()
    STOP_EVENT.clear()
    set_worker_heartbeat(datetime.now(timezone.utc))

    # SIGTERM 是 manage.sh stop 使用的信号；SIGINT 对应终端 Ctrl+C。
    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    LOGGER.info("自动抓取进程已启动，计划为北京时间每天 00:00 和 12:00")
    next_run = (
        datetime.now(timezone.utc)
        if run_immediately
        else next_scheduled_refresh()
    )
    try:
        while not STOP_EVENT.is_set():
            set_meta_value(
                "next_auto_fetch_at",
                next_run.isoformat(timespec="seconds"),
            )
            wait_seconds = max(
                0.0,
                (next_run - datetime.now(timezone.utc)).total_seconds(),
            )
            LOGGER.info(
                "下次自动刷新：%s UTC",
                next_run.isoformat(timespec="seconds"),
            )
            if STOP_EVENT.wait(wait_seconds):
                break

            result = run_fetch_cycle(
                fetch_function,
                translation_launcher=translation_launcher,
            )

            if result is not None and result.successful_sources == 0:
                LOGGER.info(
                    "本轮没有来源成功，%.0f 秒后重试",
                    AUTO_FETCH_RETRY_SECONDS,
                )
                next_run = datetime.now(timezone.utc) + timedelta(
                    seconds=AUTO_FETCH_RETRY_SECONDS
                )
            elif result is None:
                # 抓取锁被占用或出现未预期异常时，快速回到调度循环。
                next_run = datetime.now(timezone.utc) + timedelta(seconds=30)
            else:
                next_run = next_scheduled_refresh(
                    datetime.now(timezone.utc) + timedelta(seconds=1)
                )
    finally:
        clear_meta_value("next_auto_fetch_at")
        clear_worker_heartbeat()
        LOGGER.info("自动抓取进程已退出")


def main() -> None:
    """配置日志后启动常驻循环。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # 每次通过 manage.sh 启动或重启后台时先立即同步一次，随后再回到
    # 北京时间 00:00 / 12:00 的固定日程。否则上午重启会一直等到中午，
    # 页面看起来像“没有抓到新信息”。
    run_forever(
        run_immediately=True,
        translation_launcher=launch_background_translation,
    )


if __name__ == "__main__":
    main()
