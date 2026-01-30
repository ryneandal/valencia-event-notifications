"""Data models for Valencia Events.

Defines Pydantic models for validated, normalized event data.
"""

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, ConfigDict


class Event(BaseModel):
    """Normalized event model with validated fields.

    Attributes:
        title: Event title/name
        start: Event start date/time (timezone-aware, Europe/Madrid)
        url: URL to event details page
        description: Event description text
        source: Source identifier
        event_hash: Unique hash for deduplication
    """

    title: str = Field(..., min_length=1)
    start: datetime
    url: HttpUrl
    description: str = Field(default="")
    source: str
    event_hash: str | None = None

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
        }
    )
