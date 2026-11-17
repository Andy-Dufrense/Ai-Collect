"""命令行历史回填入口。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from backfill import backfill_history
from config import HISTORY_BACKFILL_DAYS


def main() -> int:
    parser = argparse.ArgumentParser(description="按真实发布日期回填历史资讯")
    parser.add_argument(
        "--days",
        type=int,
        default=HISTORY_BACKFILL_DAYS,
        help="回填最近多少天，默认 60",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    added = backfill_history(max(1, args.days))
    print(f"本次历史回填完成，新增 {added} 条资讯。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
