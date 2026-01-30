"""Normalize raw event data into validated Event models.

Handles parsing various date formats and converting raw scraped data
into standardized Event objects with timezone-aware datetimes.
"""

import re
from datetime import datetime
from typing import Any

import pytz

from .models import Event

VALENCIA_TZ = pytz.timezone("Europe/Madrid")

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
    description = raw_item.get("description", "")
    if description.lower().endswith((".jpg", ".png", ".jpeg")):
        description = ""

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
    """
    date_string = date_string.strip()

    # 1. Handle ranges "From 28/11/2025 to ..."
    if date_string.lower().startswith("from "):
        match = re.search(r"From (\d{2}/\d{2}/\d{4})", date_string, re.IGNORECASE)
        if match:
            date_string = match.group(1)

    dt: datetime | None = None

    # 2. Try simple DD/MM/YYYY
    try:
        dt = datetime.strptime(date_string, "%d/%m/%Y")
    except ValueError:
        pass

    # 3. Try DD/MM/YYYY HH:MM
    if not dt:
        try:
            dt = datetime.strptime(date_string, "%d/%m/%Y %H:%M")
        except ValueError:
            pass

    # 4. Try Spanish format "12 de octubre de 2025" or with time
    if not dt:
        lower_str = date_string.lower()
        for month_name, month_num in SPANISH_MONTHS.items():
            if month_name in lower_str:
                # Replace month name with number
                # "12 de octubre de 2025" -> "12 10 2025" (approx logic)
                # Pattern: (\d+) de (\w+) de (\d+)
                match = re.search(
                    r"(\d+)\s+de\s+(\w+)\s+de\s+(\d+)(?:\s+(\d+):(\d+))?", lower_str
                )
                if match:
                    d, m_name, y, h, minute = match.groups()
                    if m_name == month_name:
                        h = int(h) if h else 0
                        minute = int(minute) if minute else 0
                        dt = datetime(int(y), month_num, int(d), h, minute)
                break

    # 5. Fallback: ISO format (from utils or other scrapers)
    if not dt:
        try:
            dt = datetime.fromisoformat(date_string)
        except ValueError:
            pass

    if dt:
        # Assign timezone if naive, otherwise convert
        if dt.tzinfo is None:
            return VALENCIA_TZ.localize(dt)
        return dt.astimezone(VALENCIA_TZ)

    raise ValueError(f"Could not parse date: {date_string}")
