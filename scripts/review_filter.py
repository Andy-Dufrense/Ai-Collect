"""
人工审核新闻过滤规则。

用法：
    python3 scripts/review_filter.py --list 20
    python3 scripts/review_filter.py --apply "1=y,2=n,3=s"
    python3 scripts/review_filter.py

y=保留，n=排除，s=跳过，q=退出。答案会写入 data/filter_decisions.jsonl；
被排除的当前新闻会从数据库删除，并据此生成 data/learned_filter.json。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config import DATA_DIR
from database import delete_news_by_ids, get_all_news, initialize_database
from filter_learning import DECISIONS_PATH, learn_rules_from_decisions


SESSION_PATH = DATA_DIR / "filter_review_session.json"
DECISION_NAMES = {"y": "keep", "n": "exclude", "s": "skip"}


def load_decisions() -> list[dict[str, Any]]:
    """读取历史审核答案，并忽略损坏的行。"""

    if not DECISIONS_PATH.exists():
        return []
    decisions = []
    for line in DECISIONS_PATH.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            decisions.append(value)
    return decisions


def sampled_questions(limit: int) -> list[dict[str, Any]]:
    """从数据库均匀抽样尚未审核的新闻，避免只看到同一来源。"""

    initialize_database()
    reviewed_titles = {
        str(item.get("title", "")).strip() for item in load_decisions()
    }
    items = [
        item for item in get_all_news()
        if str(item.get("title", "")).strip() not in reviewed_titles
    ]
    if not items or limit <= 0:
        return []
    if len(items) <= limit:
        return items
    step = max(1, len(items) // limit)
    sampled = items[::step][:limit]
    if len(sampled) < limit:
        for item in items:
            if item not in sampled:
                sampled.append(item)
            if len(sampled) >= limit:
                break
    return sampled


def write_session(questions: list[dict[str, Any]]) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "questions": questions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def print_questions(questions: list[dict[str, Any]]) -> None:
    for number, item in enumerate(questions, start=1):
        summary = str(item.get("summary", "")).replace("\n", " ")[:180]
        print(f"\n{number}. [{item.get('category')}] {item.get('title')}")
        print(f"   来源：{item.get('source')}  发布时间：{item.get('publish_time')}")
        if summary:
            print(f"   简介：{summary}")


def save_decisions(
    questions: list[dict[str, Any]],
    answers: dict[int, str],
) -> None:
    """保存答案、删除明确排除的新闻并重新生成过滤规则。"""

    existing = load_decisions()
    by_title = {str(item.get("title", "")): item for item in existing}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    excluded_ids: list[int] = []

    for number, decision_code in answers.items():
        if number < 1 or number > len(questions):
            continue
        item = questions[number - 1]
        decision = DECISION_NAMES[decision_code]
        record = {
            "id": item.get("id"),
            "title": item.get("title"),
            "link": item.get("link"),
            "source": item.get("source"),
            "category": item.get("category"),
            "decision": decision,
            "reviewed_at": now,
        }
        by_title[str(item.get("title", ""))] = record
        if decision == "exclude" and item.get("id") is not None:
            excluded_ids.append(int(item["id"]))

    DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISIONS_PATH.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False) + "\n"
            for item in by_title.values()
        ),
        encoding="utf-8",
    )
    deleted = delete_news_by_ids(excluded_ids)
    rules = learn_rules_from_decisions()
    print(f"已保存 {len(answers)} 条答案，删除 {deleted} 条当前新闻。")
    print(f"已生成规则：{len(rules.get('blocked_terms', []))} 个排除词。")


def run_interactive(limit: int) -> None:
    questions = sampled_questions(limit)
    if not questions:
        print("没有待审核的新闻。")
        return
    write_session(questions)
    answers: dict[int, str] = {}

    for number, item in enumerate(questions, start=1):
        print_questions([item])
        while True:
            answer = input("这条算目标资讯吗？[y=保留 n=排除 s=跳过 q=退出] ").strip().lower()
            if answer in {"y", "n", "s"}:
                answers[number] = answer
                break
            if answer == "q":
                save_decisions(questions, answers)
                return
            print("请输入 y、n、s 或 q。")
    save_decisions(questions, answers)


def parse_answers(raw: str) -> dict[int, str]:
    """解析 “1=y,2=n,3=s” 格式。"""

    answers: dict[int, str] = {}
    for part in raw.split(","):
        if "=" not in part:
            raise ValueError(f"无法解析答案：{part}")
        number_text, answer = part.split("=", 1)
        number = int(number_text.strip())
        answer = answer.strip().lower()
        if answer not in DECISION_NAMES:
            raise ValueError(f"答案必须是 y/n/s：{part}")
        answers[number] = answer
    return answers


def main() -> int:
    parser = argparse.ArgumentParser(description="人工审核新闻过滤规则")
    parser.add_argument("--list", type=int, metavar="N", help="列出 N 条待审核新闻")
    parser.add_argument("--apply", help='批量应用答案，例如 "1=y,2=n,3=s"')
    parser.add_argument("--limit", type=int, default=20, help="交互审核数量")
    args = parser.parse_args()

    if args.apply:
        if not SESSION_PATH.exists():
            print("还没有问题列表，请先运行 --list。")
            return 1
        session = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
        questions = session.get("questions", [])
        save_decisions(questions, parse_answers(args.apply))
        return 0

    if args.list is not None:
        questions = sampled_questions(args.list)
        write_session(questions)
        print_questions(questions)
        print(
            '\n请用 “1=y,2=n,3=s” 回复，再执行：'
            f' python3 scripts/review_filter.py --apply "..."'
        )
        return 0

    run_interactive(args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
