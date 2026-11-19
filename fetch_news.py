"""
命令行抓取入口，专门给 cron 或手动测试调用。

示例：
    python3 fetch_news.py

退出码说明：
    0：至少一个 RSS 源成功处理（即使没有新增资讯也算成功）
    2：所有 RSS 源都失败，便于 cron 邮件或日志发现异常
"""

from __future__ import annotations

import logging
import sys

from auto_fetcher import launch_background_translation
from rss_fetcher import fetch_and_save_news


def main() -> int:
    """执行一次抓取并输出适合终端和 cron 日志阅读的结果。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    try:
        result = fetch_and_save_news()
    except Exception:
        logging.exception("抓取任务发生未预期异常")
        return 1

    print(
        "本轮抓取结果："
        f"成功源 {result.successful_sources}/{result.source_count}，"
        f"RSS 条目 {result.total_entries} 条，"
        f"关键词命中 {result.matched_entries} 条，"
        f"数据库新增 {result.new_count} 条。"
    )
    for error in result.errors:
        print(f"数据源错误：{error}", file=sys.stderr)

    if result.successful_sources > 0:
        try:
            launch_background_translation()
            print("英文标题已交给独立后台翻译任务处理。")
        except Exception:
            logging.exception("后台翻译任务启动失败，但不影响本轮抓取")

    # 全部源失败时返回非零，让 cron 能识别这次任务并没有成功。
    return 0 if result.successful_sources > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
