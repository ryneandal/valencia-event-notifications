"""Tests for user storage tables."""

import sqlite3
import tempfile
from pathlib import Path

import pytest
from valencia_events.storage import EventStorage

class TestUserStorage:
    """Test suite for user storage tables."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def storage(self, temp_db):
        """Create storage instance."""
        return EventStorage(temp_db)

    def test_create_tables(self, storage):
        """Test that user tables are created correctly."""
        with storage._get_connection() as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            assert cur.fetchone() is not None
            
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users_events'")
            assert cur.fetchone() is not None

    def test_user_operations(self, storage):
        """Test basic user insertion and retrieval (raw SQL for now)."""
        with storage._get_connection() as conn:
            conn.execute(
                "INSERT INTO users (email, preferences) VALUES (?, ?)",
                ("test@example.com", "I like hiking")
            )
            
            cur = conn.execute("SELECT * FROM users WHERE email=?", ("test@example.com",))
            user = cur.fetchone()
            assert user is not None
            assert user[1] == "test@example.com"
            assert user[2] == "I like hiking"
            
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO users (email, preferences) VALUES (?, ?)",
                    ("test@example.com", "duplicate")
                )

    def test_user_events_join(self, storage):
        """Test users_events join table constraints."""
        with storage._get_connection() as conn:
            cur = conn.execute("INSERT INTO users (email) VALUES (?)", ("user@test.com",))
            user_id = cur.lastrowid
            
            conn.execute(
                "INSERT INTO events (event_hash, title, start) VALUES (?, ?, ?)",
                ("hash123", "Test Event", "2025-01-01")
            )
            
            conn.execute(
                """INSERT INTO users_events (user_id, event_hash, relevance_score) 
                   VALUES (?, ?, ?)""",
                (user_id, "hash123", 0.95)
            )
            
            cur = conn.execute("SELECT * FROM users_events WHERE user_id=?", (user_id,))
            link = cur.fetchone()
            assert link is not None
            assert link[1] == "hash123"
            assert link[3] == 0.95
