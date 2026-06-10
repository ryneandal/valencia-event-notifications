"""User onboarding service.

Implements registration, login, and preference management.
"""

from __future__ import annotations

from .models import LoginSession, User
from .storage import EventStorage


class OnboardingService:
    """High-level onboarding workflow backed by ``EventStorage``."""

    def __init__(self, storage: EventStorage):
        """Initialize the service with the backing storage layer.

        Args:
            storage: Storage backend used for users and sessions.
        """
        self.storage = storage

    def register(
        self,
        *,
        email: str,
        preferences_blob: str | None = None,
    ) -> LoginSession:
        """Create a user and immediately issue a login session.

        Args:
            email: User email address.
            preferences_blob: Optional stored preference payload.

        Returns:
            A new login session for the created user.
        """
        user = self.storage.create_user(email=email, preferences=preferences_blob)
        token = self.storage.create_user_session(user.id)
        return LoginSession(session_token=token, user=user)

    def login(self, *, email: str) -> LoginSession:
        """Log in an existing user and return a fresh bearer token.

        Args:
            email: User email address.

        Returns:
            A new login session for the authenticated user.

        Raises:
            ValueError: If the user does not exist or is inactive.
        """
        user = self.storage.get_user_by_email(email)
        if user is None:
            raise ValueError("User not found")
        if not user.is_active:
            raise ValueError("User subscription is paused")
        token = self.storage.create_user_session(user.id)
        return LoginSession(session_token=token, user=user)

    def get_current_user(self, *, session_token: str) -> User:
        """Resolve a bearer token to the active user.

        Args:
            session_token: Plaintext bearer token.

        Returns:
            The active user associated with the session.

        Raises:
            ValueError: If the session is invalid or expired.
        """
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
        """Persist the preference blob for the logged-in user.

        Args:
            session_token: Plaintext bearer token.
            preferences_blob: Serialized user preferences payload.

        Returns:
            The updated user record.
        """
        user = self.get_current_user(session_token=session_token)
        return self.storage.update_user_preferences(user.id, preferences_blob)

    def logout(self, *, session_token: str) -> None:
        """Invalidate the active session.

        Args:
            session_token: Plaintext bearer token to revoke.
        """
        self.storage.revoke_user_session(session_token)
