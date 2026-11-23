"""文本编码修复工具。"""

from __future__ import annotations

import re


# 中文 UTF-8 被误按 MacRoman 或 Windows 编码解码后，通常会出现这些字符。
# 这里仅用于快速跳过正常中文和纯英文，真正的修复仍会严格验证结果。
_MOJIBAKE_HINT = re.compile(r"[‰∏ÄÈ¶ñÊ≠åÂèòÁâÔºÅËãØ∫ÃÂâð]")
_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
_CYRILLIC_RUN_PATTERN = re.compile(r"[\u0400-\u04ffЃІЇЈЎў·]{2,}")
_SUSPICIOUS_MOJIBAKE_PATTERN = re.compile(
    r"[\u0370-\u03ff\u0400-\u04ff]|ő|Ň|Ę|ľ|Σ"
)
_META_CHARSET_PATTERN = re.compile(
    br"<meta[^>]+charset\s*=\s*[\"']?\s*([A-Za-z0-9._-]+)",
    re.IGNORECASE,
)
_XML_ENCODING_PATTERN = re.compile(
    br"<\?xml[^>]+encoding\s*=\s*[\"']([^\"']+)",
    re.IGNORECASE,
)
_TITLE_CATEGORY_PREFIX_PATTERN = re.compile(
    r"^\s*[\[【]\s*"
    r"(?:新闻|资讯|讨论|分享|新品|视频|资源|评测|教程|公告|转载|原创)"
    r"\s*[\]】]\s*(?:[-—|｜:：]\s*)?",
    re.IGNORECASE,
)
_COMMON_CJK = frozenset(
    "的一是了我不人在他有这个上们来到时大地为子中你说生国年着就那和要"
    "下以能会对发新片闻资讯布推免费配套编辑监听音音箱设备硬件软件智能"
    "乐器吉他钢琴合成器模块固件工作站键盘虚拟模拟器用于支持功能更新"
    "仿首款系列原子演奏四算子讨论分享扩展工具"
)
_DOMAIN_CJK_TERMS = (
    "新闻",
    "资讯",
    "发布",
    "推出",
    "免费",
    "配套",
    "编辑器",
    "监听",
    "音箱",
    "音频",
    "工作站",
    "内置",
    "模块",
    "键盘",
    "虚拟",
    "模拟",
    "合成器",
    "固件",
)
_PREFERRED_LABEL_TERMS = (
    "[新闻]",
    "[ 新闻 ]",
    "[资讯]",
    "[ 资讯 ]",
    "[讨论]",
    "[新品]",
)
_CHINESE_PUNCTUATION = "【】《》，：！？"
_LEGACY_GBK_ENCODINGS = (
    "ptcp154",
    "mac_latin2",
    "iso8859_5",
    "cp1251",
    "mac_cyrillic",
    "cp1250",
    "iso8859_2",
    "mac_roman",
    "cp1252",
    "cp1257",
    "iso8859_13",
)


def _cjk_count(text: str) -> int:
    """统计中日韩统一表意文字数量，用于判断修复结果是否更像中文。"""

    return len(_CJK_PATTERN.findall(text))


def charset_from_content_type(content_type: str) -> str:
    """从 HTTP Content-Type 中提取明确声明的 charset。"""

    match = re.search(
        r"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)",
        str(content_type or ""),
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _normalize_charset(value: str) -> str:
    """统一中文网页常见编码别名。"""

    encoding = str(value or "").strip().casefold()
    if encoding in {"gb2312", "gbk", "x-gbk", "gb_2312-80"}:
        return "gb18030"
    if encoding in {"utf8", "utf-8-sig"}:
        return "utf-8"
    return encoding


def decode_html_content(
    content: bytes,
    *,
    declared_encoding: str = "",
) -> str:
    """
    解码 HTML 响应。

    优先使用响应头和 HTML meta 的明确声明；没有声明时先尝试 UTF-8，
    再尝试中国大陆网站常见的 GB18030。不能先使用 apparent_encoding，
    否则 GBK 中文页面可能被误判成 Windows-1251。
    """

    if not content:
        return ""
    declared = _normalize_charset(declared_encoding)
    meta_match = _META_CHARSET_PATTERN.search(content[:20_000])
    xml_match = _XML_ENCODING_PATTERN.search(content[:1_000])
    document_declared = _normalize_charset(
        meta_match.group(1).decode("ascii", errors="ignore")
        if meta_match
        else (
            xml_match.group(1).decode("ascii", errors="ignore")
            if xml_match
            else ""
        )
    )
    candidates: list[str] = []
    for encoding in (
        document_declared,
        "utf-8",
        "gb18030",
        "big5",
        declared,
        "cp1252",
    ):
        if encoding and encoding not in candidates:
            candidates.append(encoding)
    for encoding in candidates:
        try:
            decoded = content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
        return decoded.lstrip("\ufeff")
    return content.decode("utf-8", errors="replace").lstrip("\ufeff")


def is_likely_mojibake(text: str) -> bool:
    """判断文本是否仍包含明显的中文编码错乱字符。"""

    value = str(text or "")
    if not value:
        return False
    if "\ufffd" in value or "锟" in value:
        return True
    suspicious_count = len(_SUSPICIOUS_MOJIBAKE_PATTERN.findall(value))
    return suspicious_count >= 2


def strip_title_category_prefix(title: str) -> str:
    """去掉标题开头的短栏目标签，但保留日期等有效前缀。"""

    value = str(title or "").strip()
    cleaned = _TITLE_CATEGORY_PREFIX_PATTERN.sub("", value, count=1).strip()
    return cleaned or value


def _mojibake_candidate_score(candidate: str) -> int:
    """给候选中文文本打分，优先选择常见中文和领域词。"""

    candidate_cjk = _cjk_count(candidate)
    domain_score = sum(
        100 for term in _DOMAIN_CJK_TERMS if term in candidate
    )
    label_score = sum(
        300 for term in _PREFERRED_LABEL_TERMS if term in candidate
    )
    punctuation_score = sum(
        10 for char in candidate if char in _CHINESE_PUNCTUATION
    )
    common_score = sum(
        2 for char in candidate if char in _COMMON_CJK
    )
    return (
        label_score
        + punctuation_score
        + domain_score
        + common_score
        + candidate_cjk
    )


def _repair_whole_string_gbk_mojibake(text: str) -> str:
    """尝试把整条误按单字节编码解码的 GBK 文本恢复成中文。"""

    best_candidate = text
    best_score = 0
    for encoding in _LEGACY_GBK_ENCODINGS:
        try:
            candidate = text.encode(encoding).decode("gb18030")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        candidate_cjk = _cjk_count(candidate)
        if candidate_cjk < 2 or "\ufffd" in candidate:
            continue
        score = _mojibake_candidate_score(candidate)
        if score > best_score:
            best_candidate = candidate
            best_score = score
    return best_candidate


def _repair_gbk_decoded_as_cp1251(text: str) -> str:
    """修复 GBK 字节被错误按西里尔编码解码后形成的片段。"""

    def replace(match: re.Match[str]) -> str:
        fragment = match.group(0)
        best_candidate = fragment
        best_score = 0
        for encoding in (
            "cp1251",
            "iso8859_5",
            "mac_cyrillic",
            "cp1250",
            "iso8859_2",
        ):
            try:
                candidate = fragment.encode(encoding).decode("gb18030")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            candidate_cjk = _cjk_count(candidate)
            compact_length = len(re.sub(r"\s+", "", candidate))
            if (
                candidate_cjk < 1
                or candidate_cjk * 2 < max(1, compact_length)
            ):
                continue
            score = _mojibake_candidate_score(candidate)
            if score > best_score:
                best_candidate = candidate
                best_score = score
        return best_candidate

    return _CYRILLIC_RUN_PATTERN.sub(replace, text)


def repair_mojibake(text: str) -> str:
    """
    尝试还原常见的 UTF-8 乱码。

    只有当候选结果明显包含更多中文、没有替换符，并且原字符串符合常见
    乱码特征时才替换。这样可以避免误改正常英文、法语重音字母或产品名。
    """

    value = str(text or "")
    if is_likely_mojibake(value):
        whole_candidate = _repair_whole_string_gbk_mojibake(value)
        fragment_candidate = _repair_gbk_decoded_as_cp1251(value)
        value = max(
            (whole_candidate, fragment_candidate),
            key=_mojibake_candidate_score,
        )
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
