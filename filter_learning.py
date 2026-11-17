"""根据人工审核答案保存和生成可复用过滤规则。"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DATA_DIR


RULES_PATH = DATA_DIR / "learned_filter.json"
DECISIONS_PATH = DATA_DIR / "filter_decisions.jsonl"

ENGLISH_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "about",
    "new", "how", "why", "what", "you", "your", "our", "its", "are", "was",
    "has", "have", "will", "can", "more", "than", "out", "over", "after",
}

CHINESE_STOP_TERMS = {
    "新闻", "最新", "消息", "发布", "推出", "今天", "本周", "今年", "我们",
    "可以", "一个", "这个", "进行", "相关", "公司", "行业",
}


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().casefold()


def _candidate_terms(title: str) -> set[str]:
    """提取英文词、英文双词和较长中文片段作为候选规则。"""

    terms: set[str] = set()
    normalized = _normalize_title(title)
    english_words = [
        word for word in re.findall(r"[a-z][a-z'-]{2,}", normalized)
        if word not in ENGLISH_STOPWORDS
    ]
    # 单个英文词至少 7 个字符，避免把 black、price 等常见词变成永久规则。
    terms.update(word for word in english_words if len(word) >= 7)
    for left, right in zip(english_words, english_words[1:]):
        terms.add(f"{left} {right}")

    for segment in re.findall(r"[\u3400-\u9fff]{4,}", title):
        for size in (4, 5, 6):
            for index in range(0, len(segment) - size + 1):
                term = segment[index:index + size]
                if term not in CHINESE_STOP_TERMS:
                    terms.add(term)
    return terms


def load_learned_rules() -> dict[str, Any]:
    """读取人工审核生成的规则；文件不存在时返回空规则。"""

    try:
        payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    return {"excluded_titles": [], "blocked_terms": []}


def is_learned_excluded(title: str) -> bool:
    """判断标题是否命中人工审核学习出的排除规则。"""

    rules = load_learned_rules()
    normalized = _normalize_title(title)
    excluded_titles = {
        str(value).casefold() for value in rules.get("excluded_titles", [])
    }
    if normalized in excluded_titles:
        return True
    blocked_terms = [str(value).casefold() for value in rules.get("blocked_terms", [])]
    return any(term and term in normalized for term in blocked_terms)


def learn_rules_from_decisions() -> dict[str, Any]:
    """
    从审核答案中生成保守规则。

    候选词至少在 2 条排除新闻中出现，且从未出现在保留新闻中，避免根据单条
    样本过度过滤。
    """

    decisions: list[dict[str, Any]] = []
    if DECISIONS_PATH.exists():
        for line in DECISIONS_PATH.read_text(encoding="utf-8").splitlines():
            try:
                decision = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(decision, dict):
                decisions.append(decision)

    rejected_terms: Counter[str] = Counter()
    accepted_terms: set[str] = set()
    excluded_titles: list[str] = []
    accepted_titles: list[str] = []
    for item in decisions:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        terms = _candidate_terms(title)
        if item.get("decision") == "exclude":
            excluded_titles.append(title)
            rejected_terms.update(terms)
        elif item.get("decision") == "keep":
            accepted_terms.update(terms)
            accepted_titles.append(title)

    blocked_terms = [
        term
        for term, count in rejected_terms.most_common()
        if count >= 2 and term not in accepted_terms
    ][:60]
    rules = {
        "excluded_titles": sorted(set(excluded_titles)),
        "accepted_titles": sorted(set(accepted_titles)),
        "blocked_terms": blocked_terms,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "decision_count": len(decisions),
    }
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(
        json.dumps(rules, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return rules


def is_learned_accepted(title: str) -> bool:
    """人工明确保留过的标题不受后续自动规则误删。"""

    rules = load_learned_rules()
    normalized = _normalize_title(title)
    accepted_titles = {
        str(value).casefold() for value in rules.get("accepted_titles", [])
    }
    return normalized in accepted_titles
