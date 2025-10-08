"""Database layer for storing events in SQLite."""

import sqlite3
from datetime import datetime
from pathlib import Path

from .models import Event


class EventDatabase:
    """SQLite database for storing and retrieving events."""

    def __init__(self, db_path: str = "events.db"):
        """Initialize the database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    location TEXT,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    url TEXT,
                    source TEXT NOT NULL,
                    neighborhood TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(title, start_time, location)
                )
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_start_time ON events(start_time)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_source ON events(source)
            """
            )
            conn.commit()

    def add_event(self, event: Event) -> bool:
        """Add an event to the database.

        Args:
            event: Event to add

        Returns:
            True if event was added, False if it already exists
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO events (
                        title, description, location, start_time, end_time,
                        url, source, neighborhood, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        event.title,
                        event.description,
                        event.location,
                        event.start_time.isoformat(),
                        event.end_time.isoformat() if event.end_time else None,
                        event.url,
                        event.source,
                        event.neighborhood,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            # Event already exists (duplicate)
            return False

    def add_events(self, events: list[Event]) -> int:
        """Add multiple events to the database.

        Args:
            events: List of events to add

        Returns:
            Number of new events added
        """
        added = 0
        for event in events:
            if self.add_event(event):
                added += 1
        return added

    def get_events_by_date(self, date: datetime) -> list[Event]:
        """Get all events for a specific date.

        Args:
            date: Date to filter events

        Returns:
            List of events for the specified date
        """
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = date.replace(hour=23, minute=59, second=59, microsecond=999999)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT title, description, location, start_time, end_time,
                       url, source, neighborhood
                FROM events
                WHERE start_time >= ? AND start_time <= ?
                ORDER BY start_time
            """,
                (start_of_day.isoformat(), end_of_day.isoformat()),
            )

            events = []
            for row in cursor.fetchall():
                events.append(
                    Event(
                        title=row[0],
                        description=row[1],
                        location=row[2],
                        start_time=datetime.fromisoformat(row[3]),
                        end_time=datetime.fromisoformat(row[4]) if row[4] else None,
                        url=row[5],
                        source=row[6],
                        neighborhood=row[7],
                    )
                )
            return events

    def get_all_events(self) -> list[Event]:
        """Get all events from the database.

        Returns:
            List of all events
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT title, description, location, start_time, end_time,
                       url, source, neighborhood
                FROM events
                ORDER BY start_time
            """
            )

            events = []
            for row in cursor.fetchall():
                events.append(
                    Event(
                        title=row[0],
                        description=row[1],
                        location=row[2],
                        start_time=datetime.fromisoformat(row[3]),
                        end_time=datetime.fromisoformat(row[4]) if row[4] else None,
                        url=row[5],
                        source=row[6],
                        neighborhood=row[7],
                    )
                )
            return events
