"""Event data model using Pydantic."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Event(BaseModel):
    """Normalized event model for all scraped events."""

    title: str = Field(..., description="Event title")
    description: Optional[str] = Field(None, description="Event description")
    location: Optional[str] = Field(None, description="Event location")
    start_time: datetime = Field(..., description="Event start time")
    end_time: Optional[datetime] = Field(None, description="Event end time")
    url: Optional[str] = Field(None, description="Event URL for more information")
    source: str = Field(..., description="Source of the event (e.g., website name)")
    neighborhood: Optional[str] = Field(
        None, description="Neighborhood (e.g., La Roqueta, Russafa)"
    )

    def __hash__(self):
        """Generate hash for deduplication based on title, start_time, and location."""
        return hash((self.title.lower(), self.start_time, self.location))

    def __eq__(self, other):
        """Check equality for deduplication."""
        if not isinstance(other, Event):
            return False
        return (
            self.title.lower() == other.title.lower()
            and self.start_time == other.start_time
            and self.location == other.location
        )
