"""GitHub 项目与更新的重要性判断。"""

from __future__ import annotations

import re


# 这类提交通常只维护工程杂项、界面小修或错误处理，不代表产品或模型能力
# 发生了值得行业关注的变化。
LOW_VALUE_GITHUB_UPDATE_PATTERN = re.compile(
    r"(?:"
    r"^\s*(?:docs?|readme|chore|ci|build|style|test|lint|format|merge|"
    r"revert|bump|deps?|dependencies)(?:\b|:|\(|/)|"
    r"\b(?:initial commit|first commit|daily briefing|status update|"
    r"work in progress|wip|log output|logging output|retry|"
    r"retries|error handling|exception handling|dependency updates?|"
    r"documentation|readme|typo|formatting|lint|cleanup|rename|"
    r"refactor|fix(?:es|ed)? (?:ui|css|button|sleep|typo|log|error)|"
    r"remove (?:unused|deprecated) code|license files?)\b"
    r"|^\s*https?://"
    r")",
    re.IGNORECASE,
)


# 只有包含明确的功能、模型、架构或核心工作流变化时才保留普通仓库提交。
SIGNIFICANT_GITHUB_UPDATE_PATTERN = re.compile(
    r"(?:"
    r"^\s*(?:feat(?:\([^)]*\))?:|add|implement|introduce|support|"
    r"integrate|migrate|launch|release)\b"
    r"|\b(?:new (?:model|engine|architecture|feature|pipeline|workflow)|"
    r"foundation model|fine[- ]tun(?:e|ing)|training pipeline|"
    r"inference engine|text[- ]to[- ]music|audio generation engine|"
    r"music generation engine|stem separation|source separation|"
    r"voice cloning|real[- ]time (?:audio|music)|multi[- ]track|"
    r"plugin system|public api|sdk|architecture migration)\b"
    r")",
    re.IGNORECASE,
)


LOW_VALUE_RELEASE_PATTERN = re.compile(
    r"(?:"
    r"\b(?:maintenance|hotfix|bugfix|bug fixes?|patch|minor fixes?|"
    r"dependencies|dependency updates?|docs?|documentation|readme|"
    r"typo|formatting|cleanup|housekeeping|license files?)\b"
    r")",
    re.IGNORECASE,
)


PIRATED_SOFTWARE_PATTERN = re.compile(
    r"(?:"
    r"\b(?:fl studio|ableton|logic pro|cubase|pro tools|studio one|"
    r"reaper|izotope|ozone|serum|kontakt|sibelius|sonar|encore|"
    r"melody assistant|music maker|magix)\b"
    r".{0,80}"
    r"\b(?:installer|setup|full version|crack|cracked|preactivated|"
    r"activation|download now)\b"
    r")",
    re.IGNORECASE,
)


_SEMVER_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
_STARS_PATTERN = re.compile(r"Stars\s*[：:]\s*(\d+)", re.IGNORECASE)


def is_low_value_commit_message(message: str) -> bool:
    """判断 commit 是否属于文档、小修、日志或工程杂项。"""

    value = re.sub(r"\s+", " ", str(message or "")).strip()
    return not value or LOW_VALUE_GITHUB_UPDATE_PATTERN.search(value) is not None


def is_significant_commit_message(message: str) -> bool:
    """判断 commit 是否代表功能、模型、架构或核心工作流变化。"""

    value = re.sub(r"\s+", " ", str(message or "")).strip()
    if len(value) < 12 or is_low_value_commit_message(value):
        return False
    return SIGNIFICANT_GITHUB_UPDATE_PATTERN.search(value) is not None


def is_low_value_release(
    name: str,
    body: str,
    *,
    tag_name: str = "",
    prerelease: bool = False,
) -> bool:
    """
    判断 GitHub Release 是否只是补丁、预览版、文档或依赖维护。

    补丁版本如果正文明确写了新模型、新引擎等重大能力，仍允许保留。
    """

    if prerelease:
        return True
    combined = f"{name} {body}".strip()
    if LOW_VALUE_RELEASE_PATTERN.search(combined):
        return True
    match = _SEMVER_PATTERN.match(tag_name.strip())
    if (
        match
        and int(match.group(3)) > 0
        and SIGNIFICANT_GITHUB_UPDATE_PATTERN.search(combined) is None
    ):
        return True
    return False


def is_pirated_software_repository(*text_parts: str) -> bool:
    """识别冒充开源项目、实际分发商业音乐软件安装包的新仓库。"""

    combined = " ".join(str(part or "") for part in text_parts)
    return PIRATED_SOFTWARE_PATTERN.search(combined) is not None


def stars_from_summary(summary: str) -> int:
    """从数据库简介中读取新项目 Stars；无法读取时返回 0。"""

    match = _STARS_PATTERN.search(str(summary or ""))
    return int(match.group(1)) if match else 0
