"""
常驻后台自动抓取进程。

只要通过 manage.sh 启动后端，这个进程就会立即抓取一次，此后每隔
AUTO_FETCH_INTERVAL_SECONDS（默认 300 秒）自动执行：

    下载 RSS -> 双重关键词过滤 -> SQLite 去重入库

Flask 不参与抓取，只读取数据库。因此后台更新时网页无需重启，
刷新浏览器即可看到新数据。
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from config import AUTO_FETCH_INTERVAL_SECONDS, AUTO_FETCH_RETRY_SECONDS
from database import (
    clear_worker_heartbeat,
    initialize_database,
    set_worker_heartbeat,
)
from rss_fetcher import FetchAlreadyRunningError, FetchResult, fetch_and_save_news


LOGGER = logging.getLogger("auto_fetcher")
STOP_EVENT = threading.Event()


def _handle_stop_signal(signum: int, _frame: object) -> None:
    """
    收到 SIGTERM 或 Ctrl+C 时设置停止事件。

    使用事件等待而不是长时间 sleep，可以让进程在停止命令发出后迅速退出。
    """

    LOGGER.info("收到停止信号 %s，正在结束自动抓取进程", signum)
    STOP_EVENT.set()


def run_fetch_cycle(
    fetch_function: Callable[[], FetchResult] = fetch_and_save_news,
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
        # 手动同步正在进行时，本轮让路，下一轮按计划继续。
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
    return result


def run_forever(
    fetch_function: Callable[[], FetchResult] = fetch_and_save_news,
) -> None:
    """启动即抓取一次，然后按固定间隔持续轮询，直到收到停止信号。"""

    initialize_database()
    STOP_EVENT.clear()

    # SIGTERM 是 manage.sh stop 使用的信号；SIGINT 对应终端 Ctrl+C。
    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    LOGGER.info(
        "自动抓取进程已启动，轮询间隔 %.0f 秒",
        AUTO_FETCH_INTERVAL_SECONDS,
    )
    try:
        while not STOP_EVENT.is_set():
            result = run_fetch_cycle(fetch_function)

            if result is not None and result.successful_sources == 0:
                wait_seconds = min(
                    AUTO_FETCH_INTERVAL_SECONDS,
                    AUTO_FETCH_RETRY_SECONDS,
                )
                LOGGER.info(
                    "本轮没有来源成功，%.0f 秒后自动重试",
                    wait_seconds,
                )
            elif result is None:
                # 手动同步占用锁或出现未预期异常时，快速回到调度循环。
                wait_seconds = min(30.0, AUTO_FETCH_INTERVAL_SECONDS)
            else:
                wait_seconds = AUTO_FETCH_INTERVAL_SECONDS

            if STOP_EVENT.wait(wait_seconds):
                break
    finally:
        clear_worker_heartbeat()
        LOGGER.info("自动抓取进程已退出")


def main() -> None:
    """配置日志后启动常驻循环。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    run_forever()


if __name__ == "__main__":
    main()
