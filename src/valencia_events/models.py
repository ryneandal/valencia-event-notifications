"""Data models for Valencia Events.

Defines Pydantic models for validated, normalized event data.
"""

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class Event(BaseModel):
    """Normalized event model with validated fields.

    Attributes:
        title: Event title or name.
        start: Event start date/time in Europe/Madrid.
        url: URL to the event details page.
        description: Event description text.
        source: Source identifier.
        event_hash: Unique hash for deduplication.
    """

    title: str = Field(..., min_length=1)
    start: datetime
    url: HttpUrl
    description: str = Field(default="")
    source: str
    event_hash: str | None = None


class User(BaseModel):
    """Registered user record.

    Attributes:
        id: Primary key.
        email: Normalized email address.
        preferences: Serialized preference blob.
        is_active: Whether the subscription is active.
        created_at: Account creation timestamp.
    """

    id: int
    email: str = Field(..., min_length=3)
    preferences: str | None = None
    is_active: bool = True
    created_at: datetime


class LoginSession(BaseModel):
    """Session created after a successful login.

    Attributes:
        session_token: Plaintext bearer token.
        user: Authenticated user.
    """

    session_token: str
    user: User
