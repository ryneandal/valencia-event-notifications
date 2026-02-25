"""User onboarding service.

Implements registration, login, and preference management.
"""

from __future__ import annotations

from .models import LoginSession, User
from .storage import EventStorage


class OnboardingService:
    """High-level onboarding workflow backed by EventStorage."""

    def __init__(self, storage: EventStorage):
        self.storage = storage

    def register(
        self,
        *,
        email: str,
        preferences_blob: str | None = None,
    ) -> LoginSession:
        """Create user and immediately create a login session."""
        user = self.storage.create_user(email=email, preferences=preferences_blob)
        token = self.storage.create_user_session(user.id)
        return LoginSession(session_token=token, user=user)

    def login(self, *, email: str) -> LoginSession:
        """Login existing user and return a fresh bearer token."""
        user = self.storage.get_user_by_email(email)
        if user is None:
            raise ValueError("User not found")
        if not user.is_active:
            raise ValueError("User subscription is paused")
        token = self.storage.create_user_session(user.id)
        return LoginSession(session_token=token, user=user)

    def get_current_user(self, *, session_token: str) -> User:
        """Resolve bearer token to active user."""
        user = self.storage.get_user_by_session_token(session_token)
        if user is None:
            raise ValueError("Invalid or expired session")
        return user

    def save_preferences(
        self,
        *,
        session_token: str,
        preferences_blob: str | None,
    ) -> User:
        """Persist preference blob for the logged-in user."""
        user = self.get_current_user(session_token=session_token)
        return self.storage.update_user_preferences(user.id, preferences_blob)

    def logout(self, *, session_token: str) -> None:
        """Invalidate the active session."""
        self.storage.revoke_user_session(session_token)
