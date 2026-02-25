"""Storage layer for events using SQLite.

Handles database creation, event storage, and deduplication.
"""

import hashlib
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import Event, User


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

                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_hash TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE INDEX IF NOT EXISTS idx_users_is_active
                ON users (is_active);

                CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id
                ON user_sessions (user_id);
            """)

    @staticmethod
    def _normalize_email(email: str) -> str:
        normalized = email.strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("Invalid email address")
        return normalized

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_user(row: tuple) -> User:
        user_id, email, preferences, is_active, created_at = row
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return User(
            id=user_id,
            email=email,
            preferences=preferences,
            is_active=bool(is_active),
            created_at=created_at,
        )

    def create_user(
        self,
        email: str,
        preferences: str | None = None,
        *,
        is_active: bool = True,
    ) -> User:
        """Create a new user account."""
        normalized_email = self._normalize_email(email)
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO users (email, preferences, is_active)
                    VALUES (?, ?, ?)
                    """,
                    (normalized_email, preferences, int(is_active)),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"User already exists: {normalized_email}") from exc

        user = self.get_user_by_email(normalized_email)
        if user is None:
            raise RuntimeError("Failed to create user")
        return user

    def get_user_by_email(self, email: str) -> User | None:
        """Retrieve user by email address."""
        normalized_email = self._normalize_email(email)
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, email, preferences, is_active, created_at
                FROM users
                WHERE email = ?
                """,
                (normalized_email,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

    def get_user_by_id(self, user_id: int) -> User | None:
        """Retrieve user by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, email, preferences, is_active, created_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

    def get_active_users(self) -> list[User]:
        """Retrieve all users with active subscriptions."""
        users: list[User] = []
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, email, preferences, is_active, created_at
                FROM users
                WHERE is_active = 1
                ORDER BY id ASC
                """
            ).fetchall()
        for row in rows:
            users.append(self._row_to_user(row))
        return users

    def update_user_preferences(self, user_id: int, preferences: str | None) -> User:
        """Update persisted preference blob for a user."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE users
                SET preferences = ?
                WHERE id = ?
                """,
                (preferences, user_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"User not found: {user_id}")

        updated = self.get_user_by_id(user_id)
        if updated is None:
            raise RuntimeError("Failed to load updated user")
        return updated

    def create_user_session(self, user_id: int, *, ttl_hours: int = 24) -> str:
        """Create a login session and return plaintext bearer token."""
        token = secrets.token_urlsafe(32)
        token_hash = self._token_hash(token)
        expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_sessions (user_id, token_hash, expires_at)
                VALUES (?, ?, ?)
                """,
                (user_id, token_hash, expires_at),
            )
        return token

    def get_user_by_session_token(self, session_token: str) -> User | None:
        """Resolve bearer token to current user."""
        token_hash = self._token_hash(session_token)
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    u.id,
                    u.email,
                    u.preferences,
                    u.is_active,
                    u.created_at,
                    s.expires_at
                FROM user_sessions AS s
                INNER JOIN users AS u ON u.id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()

        if row is None:
            return None

        user_row = row[:-1]
        expires_at = row[-1]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if expires_at <= datetime.now(UTC):
            self.revoke_user_session(session_token)
            return None

        user = self._row_to_user(user_row)
        if not user.is_active:
            return None
        return user

    def revoke_user_session(self, session_token: str) -> bool:
        """Invalidate an existing session token."""
        token_hash = self._token_hash(session_token)
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM user_sessions
                WHERE token_hash = ?
                """,
                (token_hash,),
            )
            return cursor.rowcount > 0

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
