"""补齐数据库中尚未翻译的英文标题。"""

from __future__ import annotations

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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    initialize_database()
    items = get_all_news()
    translated = translate_items(items, existing_items=items)
    if translated:
        save_news_items(items, datetime.now(timezone.utc))
    print(f"本次补齐中文标题：{translated} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
