"""Normalize raw event data into validated Event models.

Handles parsing various date formats and converting raw scraped data
into standardized Event objects with timezone-aware datetimes.
"""

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import pytz
from pytz.exceptions import InvalidTimeError

from .models import Event

VALENCIA_TZ = pytz.timezone("Europe/Madrid")


class DateParseError(ValueError):
    """Raised when an event timestamp cannot be interpreted without guessing."""


# Spanish month mapping
SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
SPANISH_MONTHS_ABBR = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}


def normalize_raw(raw_item: dict[str, Any]) -> Event:
    """Convert raw scraped item into normalized Event model.

    Args:
        raw_item: Dictionary with raw event data from scrapers

    Returns:
        Validated Event model with timezone-aware datetime

    Raises:
        ValueError: If required fields are missing or invalid
    """
    if not raw_item.get("title"):
        raise ValueError("Event missing title")
    if not raw_item.get("start"):
        raise ValueError("Event missing start date")

    start_dt = parse_datetime(str(raw_item["start"]))

    # Clean description if it's a filename (common for Visit Valencia)
    description = str(raw_item.get("description", "")).strip()
    is_image = description.lower().endswith((".jpg", ".png", ".jpeg"))
    description = "" if is_image else description

    return Event(
        title=str(raw_item.get("title", "")).strip(),
        start=start_dt,
        url=str(raw_item.get("url", "")).strip(),
        description=description.strip(),
        source=str(raw_item.get("source", "unknown")),
    )


def parse_datetime(date_string: str) -> datetime:
    """Parse various date/time formats into timezone-aware datetime.

    Handles:
    - ISO 8601
    - DD/MM/YYYY
    - "From DD/MM/YYYY..." (ranges)
    - Spanish dates: "DD de Month de YYYY"

    Args:
        date_string: Date/time string in various formats

    Returns:
        Timezone-aware datetime in Europe/Madrid timezone

    Raises:
        DateParseError: If the value is malformed or names an ambiguous or
            nonexistent Europe/Madrid local time.
    """
    date_string = date_string.strip()
    original_date_string = date_string
    lower_str = date_string.lower()

    # 1. Handle ranges like "From 28/11/2025 to ..." and "Del SA 28.02.26 ..."
    range_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", date_string, re.IGNORECASE)
    if date_string.lower().startswith("from ") and range_match:
        date_string = range_match.group(1)
        lower_str = date_string.lower()

    dot_range_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{2,4})", date_string)
    if dot_range_match and ("del " in lower_str or " al " in lower_str):
        date_string = dot_range_match.group(1)
        lower_str = date_string.lower()

    dt: datetime | None = None

    # 2. Try simple DD/MM/YYYY (default to noon for date-only values)
    try:
        parsed = datetime.strptime(date_string, "%d/%m/%Y")
        dt = parsed.replace(hour=12, minute=0, second=0, microsecond=0)
    except ValueError:
        pass

    # 3. Try DD/MM/YYYY HH:MM
    if not dt:
        try:
            dt = datetime.strptime(date_string, "%d/%m/%Y %H:%M")
        except ValueError:
            pass

    # 4. Try DD.MM.YY or DD.MM.YYYY (+ optional hour)
    if not dt:
        dot_match = re.search(
            r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})(?:\D+(\d{1,2}):(\d{2}))?",
            date_string,
        )
        if dot_match:
            day, month, year, hour, minute = dot_match.groups()
            year_num = int(year)
            if year_num < 100:
                year_num += 2000
            try:
                dt = datetime(
                    year_num,
                    int(month),
                    int(day),
                    int(hour) if hour else 12,
                    int(minute) if minute else 0,
                )
            except ValueError:
                pass

    # 5. Try Spanish format "12 de octubre de 2025" or with time
    if not dt:
        for month_name, month_num in SPANISH_MONTHS.items():
            if month_name in lower_str:
                match = re.search(
                    r"(\d+)\s+de\s+(\w+)\s+de\s+(\d+)(?:\s+(\d+):(\d+))?",
                    lower_str,
                )
                if match:
                    d, m_name, y, h, minute = match.groups()
                    if m_name == month_name:
                        try:
                            dt = datetime(
                                int(y),
                                month_num,
                                int(d),
                                int(h) if h else 12,
                                int(minute) if minute else 0,
                            )
                        except ValueError:
                            pass
                break

    # 6. Try abbreviated Spanish dates (e.g. "21 feb. 2026" or with time)
    if not dt:
        abbr_match = re.search(
            r"(\d{1,2})\s+([a-z]{3})\.?\s+(\d{4})(?:\D+(\d{1,2}):(\d{2}))?",
            lower_str,
        )
        if abbr_match:
            d, month_abbr, y, hour, minute = abbr_match.groups()
            if month_abbr in SPANISH_MONTHS_ABBR:
                try:
                    dt = datetime(
                        int(y),
                        SPANISH_MONTHS_ABBR[month_abbr],
                        int(d),
                        int(hour) if hour else 12,
                        int(minute) if minute else 0,
                    )
                except ValueError:
                    pass

    # 7. Try RFC 822 (common in RSS pubDate fields)
    if not dt:
        try:
            dt = parsedate_to_datetime(date_string)
        except (TypeError, ValueError):
            pass

    # 8. Fallback: ISO format (from utils or other scrapers)
    if not dt:
        try:
            normalized = date_string.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            pass

    if dt:
        # Assign timezone if naive, otherwise convert
        if dt.tzinfo is None:
            try:
                return VALENCIA_TZ.localize(dt, is_dst=None)
            except InvalidTimeError as exc:
                raise DateParseError(
                    f"Invalid Europe/Madrid local time: {original_date_string}"
                ) from exc
        return dt.astimezone(VALENCIA_TZ)

    raise DateParseError(f"Could not parse date: {original_date_string}")
