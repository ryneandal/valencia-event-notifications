"""Subscriber sources for scheduled digest delivery.

Production subscribers live in Cloudflare D1.  SQLite remains available as an
explicit local/test source and continues to own event deduplication state.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import User
from .storage import EventStorage

D1_API_BASE_URL = "https://api.cloudflare.com/client/v4"
DEFAULT_PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 20.0


class SubscriberLoadError(RuntimeError):
    """Raised when the configured subscriber source cannot be read safely."""


class SubscriberStore(Protocol):
    """Minimal store contract consumed by the digest CLI."""

    def get_active_users(self) -> list[User]: ...

    def get_user_by_email(self, email: str) -> User | None: ...


@dataclass(frozen=True)
class SubscriberSource:
    """Selected subscriber store and its legacy-recipient policy."""

    name: str
    store: SubscriberStore
    allow_recipient_fallback: bool


@dataclass(frozen=True)
class D1Config:
    """Credentials and identifiers required by Cloudflare's D1 HTTP API."""

    account_id: str
    database_id: str
    api_token: str
    api_base_url: str = D1_API_BASE_URL
    page_size: int = DEFAULT_PAGE_SIZE
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> D1Config:
        """Build configuration from the scheduled runner's environment."""
        names = {
            "account_id": "CLOUDFLARE_ACCOUNT_ID",
            "database_id": "CLOUDFLARE_D1_DATABASE_ID",
            "api_token": "CLOUDFLARE_API_TOKEN",
        }
        values = {
            field: os.environ.get(name, "").strip() for field, name in names.items()
        }
        missing = [names[field] for field, value in values.items() if not value]
        if missing:
            joined = ", ".join(sorted(missing))
            raise SubscriberLoadError(f"Missing D1 configuration: {joined}")
        return cls(**values)


ResponseOpener = Callable[[Request, float], Any]


class D1SubscriberStore:
    """Read subscribers through Cloudflare's authenticated D1 query API."""

    def __init__(
        self,
        config: D1Config,
        *,
        opener: ResponseOpener | None = None,
    ) -> None:
        if config.page_size < 1:
            raise ValueError("D1 page size must be positive")
        self._config = config
        self._opener = opener or self._open

    @staticmethod
    def _open(request: Request, timeout: float):
        return urlopen(request, timeout=timeout)  # noqa: S310

    @property
    def _query_url(self) -> str:
        account_id = quote(self._config.account_id, safe="")
        database_id = quote(self._config.database_id, safe="")
        base_url = self._config.api_base_url.rstrip("/")
        return f"{base_url}/accounts/{account_id}/d1/database/{database_id}/query"

    def _query(self, sql: str, params: list[object]) -> list[Mapping[str, object]]:
        body = json.dumps({"sql": sql, "params": params}).encode("utf-8")
        request = Request(
            self._query_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._config.api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            response = self._opener(request, self._config.timeout_seconds)
            try:
                payload = json.loads(response.read().decode("utf-8"))
            finally:
                close = getattr(response, "close", None)
                if close is not None:
                    close()
        except HTTPError as exc:
            raise SubscriberLoadError(
                f"Cloudflare D1 request failed with HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            raise SubscriberLoadError(
                "Cloudflare D1 request could not be completed"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SubscriberLoadError("Cloudflare D1 returned invalid JSON") from exc

        if not isinstance(payload, Mapping) or payload.get("success") is not True:
            raise SubscriberLoadError("Cloudflare D1 query was unsuccessful")
        result = payload.get("result")
        if not isinstance(result, list) or len(result) != 1:
            raise SubscriberLoadError("Cloudflare D1 returned an invalid query result")
        query_result = result[0]
        if (
            not isinstance(query_result, Mapping)
            or query_result.get("success") is not True
        ):
            raise SubscriberLoadError("Cloudflare D1 query execution failed")
        rows = query_result.get("results")
        if not isinstance(rows, list) or not all(
            isinstance(row, Mapping) for row in rows
        ):
            raise SubscriberLoadError("Cloudflare D1 returned invalid subscriber rows")
        return rows

    @staticmethod
    def _row_to_user(row: Mapping[str, object]) -> User:
        required = {"id", "email", "preferences_blob", "is_active", "created_at"}
        if not required.issubset(row):
            raise SubscriberLoadError("Cloudflare D1 subscriber row is incomplete")

        user_id = row["id"]
        email = row["email"]
        preferences = row["preferences_blob"]
        is_active = row["is_active"]
        created_at = row["created_at"]
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise SubscriberLoadError("Cloudflare D1 subscriber id is invalid")
        if not isinstance(email, str):
            raise SubscriberLoadError("Cloudflare D1 subscriber email is invalid")
        if preferences is not None and not isinstance(preferences, str):
            raise SubscriberLoadError("Cloudflare D1 preferences blob is invalid")
        if isinstance(is_active, bool):
            active = is_active
        elif isinstance(is_active, int) and is_active in (0, 1):
            active = bool(is_active)
        else:
            raise SubscriberLoadError("Cloudflare D1 active flag is invalid")
        if not isinstance(created_at, str):
            raise SubscriberLoadError("Cloudflare D1 subscriber timestamp is invalid")

        try:
            return User(
                id=user_id,
                email=email,
                preferences=preferences,
                is_active=active,
                created_at=created_at,
            )
        except ValueError as exc:
            raise SubscriberLoadError(
                "Cloudflare D1 subscriber row is invalid"
            ) from exc

    def get_active_users(self) -> list[User]:
        """Return every active D1 subscriber, ordered by ascending ID."""
        users: list[User] = []
        last_id = 0
        while True:
            rows = self._query(
                """
                SELECT id, email, preferences_blob, is_active, created_at
                FROM users
                WHERE is_active = 1 AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                [last_id, self._config.page_size],
            )
            page = [self._row_to_user(row) for row in rows]
            if any(user.id <= last_id for user in page):
                raise SubscriberLoadError("Cloudflare D1 pagination did not advance")
            if any(not user.is_active for user in page):
                raise SubscriberLoadError(
                    "Cloudflare D1 returned an inactive subscriber"
                )
            users.extend(page)
            if len(page) < self._config.page_size:
                return users
            last_id = page[-1].id

    def get_user_by_email(self, email: str) -> User | None:
        """Return an active D1 subscriber matching a normalized email."""
        normalized_email = email.strip().lower()
        if "@" not in normalized_email or " " in normalized_email:
            raise ValueError("Invalid email address")
        rows = self._query(
            """
            SELECT id, email, preferences_blob, is_active, created_at
            FROM users
            WHERE email = ? AND is_active = 1
            ORDER BY id ASC
            LIMIT 1
            """,
            [normalized_email],
        )
        if not rows:
            return None
        user = self._row_to_user(rows[0])
        if not user.is_active:
            raise SubscriberLoadError("Cloudflare D1 returned an inactive subscriber")
        return user


def subscriber_source_from_env(local_storage: EventStorage) -> SubscriberSource:
    """Select D1 for production or SQLite for explicit local/test operation."""
    backend = os.environ.get("SUBSCRIBER_BACKEND", "").strip().lower()
    if not backend:
        raise SubscriberLoadError(
            "Missing SUBSCRIBER_BACKEND; set it to 'd1' or explicitly to 'sqlite'"
        )
    if backend == "sqlite":
        return SubscriberSource(
            name="sqlite",
            store=local_storage,
            allow_recipient_fallback=True,
        )
    if backend == "d1":
        return SubscriberSource(
            name="d1",
            store=D1SubscriberStore(D1Config.from_env()),
            allow_recipient_fallback=False,
        )
    raise SubscriberLoadError(
        "Unsupported SUBSCRIBER_BACKEND; expected 'd1' or 'sqlite'"
    )
