"""三个问题来源诊断脚本测试。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.fetch_problem_sources import three_day_cutoff


class ProblemSourceScriptTests(unittest.TestCase):
    def test_three_day_cutoff_uses_beijing_calendar_days(self) -> None:
        now = datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(
            three_day_cutoff(now).isoformat(timespec="seconds"),
            "2026-11-17T16:00:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
