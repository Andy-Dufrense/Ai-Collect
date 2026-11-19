"""
后台自动抓取工作进程的单元测试。

这里直接注入一个假的抓取函数，不依赖真实 RSS 网络。
重点验证每轮抓取结束都会刷新工作进程心跳，网页因此可以判断自动同步在线。
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from auto_fetcher import (
    STOP_EVENT,
    run_fetch_cycle,
    run_forever,
    should_fetch_on_startup,
)
from database import (
    get_worker_heartbeat,
    initialize_database,
    set_meta_value,
)
from rss_fetcher import FetchResult


class AutoFetcherTests(unittest.TestCase):
    def test_startup_fetch_respects_recent_run_cooldown(self) -> None:
        """刚抓取完成后 restart 不应再次请求全部来源。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "startup-cooldown.db"
            with patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}):
                initialize_database()
                now = datetime.now(timezone.utc)
                self.assertTrue(should_fetch_on_startup(now))
                set_meta_value("last_fetch_at", now.isoformat(timespec="seconds"))
                self.assertFalse(should_fetch_on_startup(now))

    def test_fetch_cycle_updates_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "auto-test.db"
            with patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}):
                initialize_database()

                def fake_fetch() -> FetchResult:
                    return FetchResult(
                        fetched_at=datetime.now(timezone.utc),
                        source_count=2,
                        successful_sources=2,
                        total_entries=10,
                        matched_entries=1,
                        new_count=1,
                    )

                result = run_fetch_cycle(fake_fetch)
                self.assertIsNotNone(result)
                self.assertIsNotNone(get_worker_heartbeat())

    def test_forever_loop_clears_heartbeat_when_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "auto-loop-test.db"
            with patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}):
                initialize_database()

                def fake_fetch_and_stop() -> FetchResult:
                    # 第一轮结束后主动设置停止事件，使常驻循环能够正常退出。
                    STOP_EVENT.set()
                    return FetchResult(
                        fetched_at=datetime.now(timezone.utc),
                        source_count=1,
                        successful_sources=1,
                        total_entries=1,
                        matched_entries=0,
                        new_count=0,
                    )

                run_forever(fake_fetch_and_stop, run_immediately=True)
                self.assertIsNone(get_worker_heartbeat())

    def test_fetch_cycle_can_launch_background_translation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "auto-translation-test.db"
            with patch.dict(os.environ, {"NEWS_DB_PATH": str(database_path)}):
                initialize_database()
                called = []

                def fake_fetch() -> FetchResult:
                    return FetchResult(
                        fetched_at=datetime.now(timezone.utc),
                        source_count=1,
                        successful_sources=1,
                        total_entries=1,
                        matched_entries=1,
                        new_count=1,
                    )

                run_fetch_cycle(
                    fake_fetch,
                    translation_launcher=lambda: called.append(True),
                )
                self.assertEqual(called, [True])


if __name__ == "__main__":
    unittest.main()
