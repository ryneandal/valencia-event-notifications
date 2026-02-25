"""Data models for Valencia Events.

Defines Pydantic models for validated, normalized event data.
"""

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


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


class User(BaseModel):
    """Registered user record."""

    id: int
    email: str = Field(..., min_length=3)
    preferences: str | None = None
    is_active: bool = True
    created_at: datetime


class LoginSession(BaseModel):
    """Session created after a successful login."""

    session_token: str
    user: User
