"""Filtering helpers for raw scraped items before normalization."""

from __future__ import annotations

import re
from typing import Any

EDITORIAL_SOURCES = {"valencia_secreta", "valenciabonita"}

DATE_HINT_RE = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{2,4})|(\d{4}-\d{2}-\d{2})"
    r"|(\d{1,2}\s+de\s+[a-záéíóúñ]+\s+de\s+\d{4})",
    re.IGNORECASE,
)

EDITORIAL_BLOCKLIST = {
    "opinion",
    "editorial",
    "patrocinado",
    "publirreportaje",
}


def should_keep_raw_event(raw_item: dict[str, Any]) -> bool:
    """Return True when a raw item appears to be a valid event candidate."""
    title = str(raw_item.get("title", "")).strip()
    url = str(raw_item.get("url", "")).strip()
    start = str(raw_item.get("start", "")).strip()

    if not title or not url or not start:
        return False

    source = str(raw_item.get("source", "")).strip().lower()
    if source in EDITORIAL_SOURCES:
        title_lower = title.lower()
        if any(token in title_lower for token in EDITORIAL_BLOCKLIST):
            return False
        if not DATE_HINT_RE.search(start):
            return False

    return True
