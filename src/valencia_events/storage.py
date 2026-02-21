"""Storage layer for events using SQLite.

Handles database creation, event storage, and deduplication.
"""

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import Event


# Register adapters and converters for datetime to avoid
# Python 3.12 deprecation warnings.
def adapt_datetime(dt: datetime) -> str:
    """Adapt datetime to ISO 8601 string."""
    return dt.isoformat(sep=" ")


def convert_timestamp(val: bytes) -> datetime:
    """Convert valid ISO 8601 byte string to datetime."""
    return datetime.fromisoformat(val.decode())


sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("TIMESTAMP", convert_timestamp)


class EventStorage:
    """SQLite-based storage for events with deduplication.

    Attributes:
        db_path: Path to SQLite database file
    """

    def __init__(self, db_path: str = "events.db"):
        """Initialize storage with database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        return sqlite3.connect(
            self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )

    def _init_db(self):
        """Create database and tables if they don't exist."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_hash TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    start TIMESTAMP NOT NULL,
                    url TEXT,
                    description TEXT,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    preferences TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS users_events (
                    user_id INTEGER NOT NULL,
                    event_hash TEXT NOT NULL,
                    is_sent BOOLEAN DEFAULT 0,
                    relevance_score FLOAT,
                    relevance_reason TEXT,
                    PRIMARY KEY (user_id, event_hash),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (event_hash) REFERENCES events(event_hash)
                );
            """)

    def store_event(self, event: Event) -> bool:
        """Store an event in the database.

        Deduplicates based on event_hash. If event with same hash exists,
        it is not inserted.

        Args:
            event: Event to store

        Returns:
            True if event was inserted, False if duplicate was skipped
        """
        # Ensure hash is computed
        if not event.event_hash:
            event.event_hash = compute_event_hash(event)

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO events (
                        event_hash, title, start, url, description, source
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_hash,
                        event.title,
                        event.start,
                        str(event.url),
                        event.description,
                        event.source,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_events_for_date(self, date: datetime) -> list[Event]:
        """Retrieve all events for a specific date.

        Args:
            date: Date to retrieve events for

        Returns:
            List of events scheduled for the given date
        """
        target_date_str = date.strftime("%Y-%m-%d")
        events = []

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT title, start, url, description, source, event_hash
                FROM events
                WHERE date(start) = ?
                """,
                (target_date_str,),
            )

            for row in cursor:
                # sqlite3 with detect_types returns datetime objects for TIMESTAMP
                # columns but depending on storage it might be naive.
                # Pydantic expects zone info if defined, so we reconstruct.
                title, start, url, description, source, event_hash = row

                # Check if start is string (if detect_types failed) or datetime
                if isinstance(start, str):
                    # Should be ISO format
                    try:
                        start = datetime.fromisoformat(start)
                    except ValueError:
                        pass  # Let validation fail if strictly required or handle basic

                events.append(
                    Event(
                        title=title,
                        start=start,
                        url=url,
                        description=description,
                        source=source,
                        event_hash=event_hash,
                    )
                )
        return events

    def close(self):
        """Close database connection."""
        # Connections are context managed in methods, nothing to close
        # unless we kept a persistent self.conn
        pass


def compute_event_hash(event: Event) -> str:
    """Compute unique hash for event deduplication.

    Uses title, start datetime, and URL to create a hash.

    Args:
        event: Event to hash

    Returns:
        SHA256 hash string
    """
    # Normalize inputs for consistent hashing
    data = f"{event.title}|{event.start.isoformat()}|{event.url}"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
