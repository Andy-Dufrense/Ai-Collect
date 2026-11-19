"""补齐数据库中尚未翻译的英文标题。"""

from __future__ import annotations

import argparse
import fcntl
import logging
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from database import get_all_news, initialize_database, save_news_items
from datetime import datetime, timezone
from translation import translate_items


def main() -> int:
    parser = argparse.ArgumentParser(description="补齐英文资讯的中文标题")
    parser.add_argument(
        "--limit",
        type=int,
        default=80,
        help="本次最多翻译多少条，默认 80",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    lock_path = PROJECT_DIR / "data" / "translation.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            print("已有标题翻译任务运行，本次跳过")
            return 0

        initialize_database()
        translated_total = 0
        remaining_limit = max(1, args.limit)
        while remaining_limit > 0:
            items = get_all_news()
            translated = translate_items(
                items,
                existing_items=items,
                max_translations=min(80, remaining_limit),
            )
            if translated == 0:
                break
            save_news_items(items, datetime.now(timezone.utc))
            translated_total += translated
            remaining_limit -= translated
            print(f"翻译批次完成：{translated} 条")

        print(f"本次补齐中文标题：{translated_total} 条")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
