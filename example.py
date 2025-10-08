#!/usr/bin/env python3
"""Example script demonstrating the Valencia Event Notifications system."""

from datetime import datetime

import pytz

from valencia_events.database import EventDatabase
from valencia_events.email_digest import generate_html_digest
from valencia_events.filters import deduplicate_events, filter_events_for_tomorrow
from valencia_events.models import Event

# Create some example events
madrid_tz = pytz.timezone("Europe/Madrid")
tomorrow = datetime.now(madrid_tz).replace(
    hour=0, minute=0, second=0, microsecond=0
) + __import__("datetime").timedelta(days=1)

events = [
    Event(
        title="Live Music at Café Berlin",
        description="Jazz night featuring local artists",
        location="Café Berlin, Russafa",
        start_time=tomorrow.replace(hour=21, minute=0),
        url="https://example.com/event1",
        source="Example Source",
        neighborhood="Russafa",
    ),
    Event(
        title="Art Exhibition Opening",
        description="Contemporary art showcase",
        location="Gallery XYZ, La Roqueta",
        start_time=tomorrow.replace(hour=19, minute=0),
        url="https://example.com/event2",
        source="Example Source",
        neighborhood="La Roqueta",
    ),
    Event(
        title="Food Market",
        description="Local produce and street food",
        location="Plaza del Ayuntamiento",
        start_time=tomorrow.replace(hour=10, minute=0),
        url="https://example.com/event3",
        source="Example Source",
        neighborhood="La Roqueta",
    ),
]

# Deduplicate events
events = deduplicate_events(events)

# Store in database
print("Initializing database...")
db = EventDatabase("/tmp/example_events.db")

print(f"Adding {len(events)} events to database...")
added = db.add_events(events)
print(f"Added {added} new events")

# Filter for tomorrow
print("\nFiltering for tomorrow's events...")
tomorrow_events = filter_events_for_tomorrow(events)
print(f"Found {len(tomorrow_events)} events for tomorrow")

# Generate HTML digest
print("\nGenerating HTML email digest...")
html = generate_html_digest(tomorrow_events, tomorrow)
print("HTML digest generated successfully!")
print(f"\nPreview (first 500 chars):\n{html[:500]}...")

# Retrieve from database
print("\nRetrieving events from database...")
db_events = db.get_events_by_date(tomorrow)
print(f"Retrieved {len(db_events)} events from database")

for event in db_events:
    print(f"  - {event.title} at {event.start_time.strftime('%I:%M %p')} ({event.neighborhood})")

print("\n✅ Example completed successfully!")
