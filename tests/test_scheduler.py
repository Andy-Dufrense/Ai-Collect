"""固定刷新时间测试。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scheduler_utils import next_scheduled_refresh


class SchedulerTests(unittest.TestCase):
    def test_next_schedule_is_noon_beijing(self) -> None:
        # UTC 01:00 是北京时间 09:00，下一次应为北京时间中午 12:00。
        now = datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc)
        expected = datetime(2026, 11, 17, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(next_scheduled_refresh(now), expected)

    def test_after_noon_schedules_midnight(self) -> None:
        # UTC 05:00 是北京时间 13:00，下一次应为北京时间次日 00:00。
        now = datetime(2026, 11, 17, 5, 0, tzinfo=timezone.utc)
        expected = datetime(2026, 11, 17, 16, 0, tzinfo=timezone.utc)
        self.assertEqual(next_scheduled_refresh(now), expected)


if __name__ == "__main__":
    unittest.main()
