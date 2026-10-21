import re
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo


def _last_sunday(year: int, month: int) -> date:
    if month == 12:
        first_next_month = date(year + 1, 1, 1)
    else:
        first_next_month = date(year, month + 1, 1)
    last_day = first_next_month - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() + 1) % 7)


def _named_offset(hours: int) -> tzinfo:
    return timezone(timedelta(hours=hours), "CEST" if hours == 2 else "CET")


def madrid_timezone_for_local(local: datetime) -> tzinfo:
    """Return the modern Europe/Madrid offset for a local wall-clock value."""
    naive = local.replace(tzinfo=None)
    dst_start = datetime.combine(_last_sunday(naive.year, 3), time(hour=2))
    dst_end = datetime.combine(_last_sunday(naive.year, 10), time(hour=3))
    return _named_offset(2 if dst_start <= naive < dst_end else 1)


def localize_madrid(local: datetime) -> datetime:
    """Attach the Europe/Madrid CET/CEST offset to a naive local value."""
    return local.replace(tzinfo=madrid_timezone_for_local(local))


def to_madrid(value: datetime) -> datetime:
    """Convert an aware instant to modern Europe/Madrid without tzdata."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    utc_value = value.astimezone(UTC)
    dst_start = datetime.combine(_last_sunday(utc_value.year, 3), time(hour=1), UTC)
    dst_end = datetime.combine(_last_sunday(utc_value.year, 10), time(hour=1), UTC)
    offset = _named_offset(2 if dst_start <= utc_value < dst_end else 1)
    return utc_value.astimezone(offset)


def madrid_noon(value: date) -> datetime:
    """Create an unambiguous local noon for a València calendar date."""
    return localize_madrid(datetime.combine(value, time(hour=12)))


def available_preview_dates(now: datetime | None = None) -> list[str]:
    """The seven upcoming local dates, independent of the caller's timezone."""
    today = to_madrid(now or datetime.now(UTC)).date()
    return [(today + timedelta(days=offset)).isoformat() for offset in range(1, 8)]


def validate_preview_date(value: object, now: datetime | None = None) -> str:
    """Keep preview collection within tomorrow through the next seven days."""
    dates = available_preview_dates(now)
    if value is None:
        return dates[0]
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Choose a date from tomorrow through the next seven days.")
    if value not in dates:
        raise ValueError("Choose a date from tomorrow through the next seven days.")
    return value
