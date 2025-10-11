"""Normalize raw event data into validated Event models.

Handles parsing various date formats and converting raw scraped data
into standardized Event objects with timezone-aware datetimes.
"""

from datetime import datetime
from typing import Any, Dict

import pytz

from models import Event


VALENCIA_TZ = pytz.timezone("Europe/Madrid")


def normalize_raw(raw_item: Dict[str, Any]) -> Event:
    """Convert raw scraped item into normalized Event model.
    
    Args:
        raw_item: Dictionary with raw event data from scrapers
        
    Returns:
        Validated Event model with timezone-aware datetime
        
    Raises:
        ValueError: If required fields are missing or invalid
        
    Example:
        >>> raw = {
        ...     "title": "Concert",
        ...     "start": "12/10/2025 20:00",
        ...     "url": "https://example.com/event",
        ...     "description": "Great show",
        ...     "source": "sala_russafa"
        ... }
        >>> event = normalize_raw(raw)
        >>> event.start.tzinfo is not None
        True
    """
    # TODO: Implement date parsing for various formats
    # Supported formats should include:
    # - ISO 8601 strings
    # - "DD/MM/YYYY HH:MM"
    # - "DD de mes de YYYY HH:MM" (Spanish month names)
    # - RFC 822 (from RSS feeds)
    
    raise NotImplementedError("normalize_raw() not yet implemented")


def parse_datetime(date_string: str) -> datetime:
    """Parse various date/time formats into timezone-aware datetime.
    
    Args:
        date_string: Date/time string in various formats
        
    Returns:
        Timezone-aware datetime in Europe/Madrid timezone
        
    Raises:
        ValueError: If date string cannot be parsed
    """
    # TODO: Implement parsing logic for multiple date formats
    raise NotImplementedError("parse_datetime() not yet implemented")
