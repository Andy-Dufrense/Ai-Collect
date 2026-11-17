"""固定时间抓取调度计算。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import AUTO_FETCH_SCHEDULE_HOURS, AUTO_FETCH_TIME_ZONE


def schedule_time_zone() -> ZoneInfo:
    """返回自动刷新时区，异常时回退北京时间。"""

    try:
        return ZoneInfo(AUTO_FETCH_TIME_ZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Shanghai")


def next_scheduled_refresh(now: datetime | None = None) -> datetime:
    """返回下一次 00:00 或 12:00 刷新时间，结果统一为 UTC。"""

    current_utc = now or datetime.now(timezone.utc)
    if current_utc.tzinfo is None:
        current_utc = current_utc.replace(tzinfo=timezone.utc)
    local_now = current_utc.astimezone(schedule_time_zone())
    candidates: list[datetime] = []
    for day_offset in (0, 1):
        target_date = local_now.date() + timedelta(days=day_offset)
        for hour in AUTO_FETCH_SCHEDULE_HOURS:
            local_candidate = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                hour,
                0,
                tzinfo=schedule_time_zone(),
            )
            candidate_utc = local_candidate.astimezone(timezone.utc)
            if candidate_utc > current_utc:
                candidates.append(candidate_utc)
    return min(candidates)
