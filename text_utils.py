"""文本编码修复工具。"""

from __future__ import annotations

import re


# 中文 UTF-8 被误按 MacRoman 或 Windows 编码解码后，通常会出现这些字符。
# 这里仅用于快速跳过正常中文和纯英文，真正的修复仍会严格验证结果。
_MOJIBAKE_HINT = re.compile(r"[‰∏ÄÈ¶ñÊ≠åÂèòÁâÔºÅËãØ∫ÃÂâð]")
_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")


def _cjk_count(text: str) -> int:
    """统计中日韩统一表意文字数量，用于判断修复结果是否更像中文。"""

    return len(_CJK_PATTERN.findall(text))


def repair_mojibake(text: str) -> str:
    """
    尝试还原常见的 UTF-8 乱码。

    只有当候选结果明显包含更多中文、没有替换符，并且原字符串符合常见
    乱码特征时才替换。这样可以避免误改正常英文、法语重音字母或产品名。
    """

    value = str(text or "")
    if len(value) < 4 or not _MOJIBAKE_HINT.search(value):
        return value

    original_cjk = _cjk_count(value)
    best_candidate = value
    best_cjk = original_cjk
    for encoding in ("mac_roman", "cp1252", "latin1"):
        try:
            candidate = value.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        candidate_cjk = _cjk_count(candidate)
        if (
            "\ufffd" not in candidate
            and candidate_cjk >= 2
            and candidate_cjk > best_cjk
        ):
            best_candidate = candidate
            best_cjk = candidate_cjk
    return best_candidate
