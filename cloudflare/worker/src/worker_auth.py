import hashlib
import secrets
from typing import Any

from worker_runtime import env_value, header_get, record_to_dict, to_python

SESSION_COOKIE_NAME = "ve_session"
DEFAULT_SESSION_TTL_HOURS = 24
DEFAULT_MAGIC_LINK_TTL_MINUTES = 15


def normalize_email(email: Any) -> str:
    if not isinstance(email, str):
        raise ValueError("Invalid email")

    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("Invalid email")

    return normalized


def parse_cookie_header(cookie_header: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    if not cookie_header:
        return parsed

    for part in cookie_header.split(";"):
        key, separator, value = part.strip().partition("=")
        if not key or not separator:
            continue
        parsed[key] = value
    return parsed


def cookie_options(max_age_seconds: int) -> str:
    return "; ".join(
        [
            "Path=/",
            "HttpOnly",
            "Secure",
            "SameSite=Lax",
            f"Max-Age={max_age_seconds}",
        ]
    )


def clear_cookie_options() -> str:
    return "; ".join(
        [
            "Path=/",
            "HttpOnly",
            "Secure",
            "SameSite=Lax",
            "Max-Age=0",
        ]
    )


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def random_token() -> str:
    return secrets.token_urlsafe(32)


async def create_session(env: Any, user_id: int, ttl_hours: int) -> str:
    token = random_token()
    token_hash = sha256_hex(token)
    ttl_clause = f"+{ttl_hours} hours" if ttl_hours >= 0 else f"{ttl_hours} hours"

    await (
        env_value(env, "DB")
        .prepare(
            """
            INSERT INTO sessions (user_id, token_hash, expires_at)
            VALUES (?, ?, datetime('now', ?))
            """
        )
        .bind(user_id, token_hash, ttl_clause)
        .run()
    )

    return token


async def create_magic_link(
    env: Any,
    user_id: int,
    purpose: str,
    ttl_minutes: int,
) -> str:
    if purpose not in {"register", "login"}:
        raise ValueError("Invalid magic-link purpose")

    token = random_token()
    token_hash = sha256_hex(token)
    ttl_clause = (
        f"+{ttl_minutes} minutes" if ttl_minutes >= 0 else f"{ttl_minutes} minutes"
    )
    db = env_value(env, "DB")

    await (
        db.prepare(
            """
            DELETE FROM magic_links
            WHERE user_id = ? AND purpose = ?
            """
        )
        .bind(user_id, purpose)
        .run()
    )
    await (
        db.prepare(
            """
            INSERT INTO magic_links (user_id, token_hash, purpose, expires_at)
            VALUES (?, ?, ?, datetime('now', ?))
            """
        )
        .bind(user_id, token_hash, purpose, ttl_clause)
        .run()
    )
    return token


def result_changes(result: Any) -> int:
    result = to_python(result)
    if isinstance(result, dict):
        meta = result.get("meta", {})
        if isinstance(meta, dict):
            return int(meta.get("changes", 0))
    meta = getattr(result, "meta", None)
    return int(getattr(meta, "changes", 0))


def magic_link_record(record: Any) -> dict[str, Any] | None:
    if record is None:
        return None
    converted = to_python(record)
    if isinstance(converted, dict):
        return converted
    result = {}
    for key in ("id", "user_id", "purpose"):
        if hasattr(converted, key):
            result[key] = getattr(converted, key)
    return result or None


async def consume_magic_link(env: Any, token: Any) -> dict[str, Any] | None:
    if not isinstance(token, str) or not token.strip():
        return None

    token_hash = sha256_hex(token.strip())
    db = env_value(env, "DB")
    link = magic_link_record(
        await db.prepare(
            """
            SELECT ml.id, ml.user_id, ml.purpose
            FROM magic_links AS ml
            WHERE ml.token_hash = ?
              AND ml.consumed_at IS NULL
              AND ml.expires_at > CURRENT_TIMESTAMP
            LIMIT 1
            """
        )
        .bind(token_hash)
        .first()
    )
    if not link:
        return None

    result = await (
        db.prepare(
            """
            UPDATE magic_links
            SET consumed_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND consumed_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            """
        )
        .bind(link["id"])
        .run()
    )
    if result_changes(result) != 1:
        return None
    return link


async def resolve_session_user(env: Any, request: Any) -> dict[str, Any] | None:
    cookies = parse_cookie_header(header_get(request.headers, "cookie"))
    session_token = cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return None

    token_hash = sha256_hex(session_token)
    user = await (
        env_value(env, "DB")
        .prepare(
            """
            SELECT
              u.id,
              u.email,
              u.preferences_blob,
              u.is_active,
              s.id AS session_id
            FROM sessions AS s
            INNER JOIN users AS u ON u.id = s.user_id
            WHERE s.token_hash = ?
              AND s.expires_at > CURRENT_TIMESTAMP
              AND u.is_active = 1
            LIMIT 1
            """
        )
        .bind(token_hash)
        .first()
    )

    return record_to_dict(user)
