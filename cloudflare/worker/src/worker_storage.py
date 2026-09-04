import hashlib
import json
from typing import Any

from worker_runtime import to_python


def event_key(title: str, start_at: str, url: str) -> str:
    """Return the stable identity used to deduplicate a normalized event."""
    identity = json.dumps(
        [title.strip(), start_at.strip(), url.strip()],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def result_changes(result: Any) -> int:
    """Read the affected-row count from a Python or JavaScript D1 result."""
    value = to_python(result)
    if isinstance(value, dict):
        meta = to_python(value.get("meta"))
        if isinstance(meta, dict):
            return int(meta.get("changes", 0))

    meta = getattr(result, "meta", None)
    return int(getattr(meta, "changes", 0))


def result_rows(result: Any) -> list[dict[str, Any]]:
    """Convert a D1 ``all()`` result into ordinary Python dictionaries."""
    value = to_python(result)
    rows = value.get("results", []) if isinstance(value, dict) else []
    return [row for row in rows if isinstance(row, dict)]


async def list_active_subscribers(db: Any) -> list[dict[str, Any]]:
    """Load verified subscribers who have not paused digest delivery."""
    result = await db.prepare(
        """
        SELECT u.id, u.email, u.preferences_blob
        FROM users AS u
        LEFT JOIN subscriptions AS sub ON sub.user_id = u.id
        WHERE u.is_active = 1
          AND COALESCE(sub.is_subscribed, 1) = 1
        ORDER BY u.id
        """
    ).all()
    return result_rows(result)


async def upsert_event(
    db: Any,
    *,
    title: str,
    start_at: str,
    url: str,
    description: str,
    source: str,
) -> str:
    """Insert a normalized event or refresh its mutable source fields."""
    key = event_key(title, start_at, url)
    await (
        db.prepare(
            """
            INSERT INTO events (
              event_key, title, start_at, url, description, source
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_key) DO UPDATE SET
              description = excluded.description,
              source = excluded.source,
              last_seen_at = CURRENT_TIMESTAMP
            """
        )
        .bind(key, title, start_at, url, description, source)
        .run()
    )
    return key


async def get_or_create_digest_run(
    db: Any,
    *,
    digest_date: str,
    scheduled_for: str | None,
) -> dict[str, Any]:
    """Return the single run record for a local digest date."""
    await (
        db.prepare(
            """
            INSERT INTO digest_runs (digest_date, scheduled_for)
            VALUES (?, ?)
            ON CONFLICT(digest_date) DO NOTHING
            """
        )
        .bind(digest_date, scheduled_for)
        .run()
    )
    record = to_python(
        await db.prepare(
            """
            SELECT id, digest_date, scheduled_for, status
            FROM digest_runs
            WHERE digest_date = ?
            LIMIT 1
            """
        )
        .bind(digest_date)
        .first()
    )
    if not isinstance(record, dict):
        raise RuntimeError("D1 did not return the digest run")
    return record


async def record_recommendation(
    db: Any,
    *,
    digest_run_id: int,
    user_id: int,
    event_id: int,
    position: int,
    relevance_reason: str,
    model_id: str,
    used_fallback: bool,
) -> None:
    """Upsert one ranked event while preserving run/user uniqueness."""
    await (
        db.prepare(
            """
            INSERT INTO recommendations (
              digest_run_id, user_id, event_id, position,
              relevance_reason, model_id, used_fallback
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(digest_run_id, user_id, event_id) DO UPDATE SET
              position = excluded.position,
              relevance_reason = excluded.relevance_reason,
              model_id = excluded.model_id,
              used_fallback = excluded.used_fallback
            """
        )
        .bind(
            digest_run_id,
            user_id,
            event_id,
            position,
            relevance_reason,
            model_id,
            int(used_fallback),
        )
        .run()
    )


async def claim_delivery(db: Any, digest_run_id: int, user_id: int) -> bool:
    """Claim a send once, allowing only failed deliveries to be retried."""
    result = await (
        db.prepare(
            """
            INSERT INTO deliveries (digest_run_id, user_id, status)
            VALUES (?, ?, 'pending')
            ON CONFLICT(digest_run_id, user_id) DO UPDATE SET
              status = 'pending',
              attempt_count = deliveries.attempt_count + 1,
              provider_message_id = NULL,
              last_error_code = NULL,
              updated_at = CURRENT_TIMESTAMP,
              sent_at = NULL
            WHERE deliveries.status = 'failed'
            """
        )
        .bind(digest_run_id, user_id)
        .run()
    )
    return result_changes(result) == 1


async def mark_delivery_sent(
    db: Any,
    digest_run_id: int,
    user_id: int,
    provider_message_id: str | None,
) -> bool:
    """Finalize a claimed delivery without permitting a second success."""
    result = await (
        db.prepare(
            """
            UPDATE deliveries
            SET status = 'sent',
                provider_message_id = ?,
                last_error_code = NULL,
                updated_at = CURRENT_TIMESTAMP,
                sent_at = CURRENT_TIMESTAMP
            WHERE digest_run_id = ? AND user_id = ? AND status = 'pending'
            """
        )
        .bind(provider_message_id, digest_run_id, user_id)
        .run()
    )
    return result_changes(result) == 1


async def mark_delivery_failed(
    db: Any,
    digest_run_id: int,
    user_id: int,
    error_code: str,
) -> bool:
    """Record a sanitized failure code so a later run can retry the claim."""
    safe_error_code = " ".join(error_code.split())[:120] or "unknown"
    result = await (
        db.prepare(
            """
            UPDATE deliveries
            SET status = 'failed',
                last_error_code = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE digest_run_id = ? AND user_id = ? AND status = 'pending'
            """
        )
        .bind(safe_error_code, digest_run_id, user_id)
        .run()
    )
    return result_changes(result) == 1


async def delete_expired_history(
    db: Any,
    *,
    digest_date_before: str,
    event_last_seen_before: str,
) -> dict[str, int]:
    """Delete old delivery history, followed by now-unreferenced events."""
    deliveries = await (
        db.prepare(
            """
            DELETE FROM deliveries
            WHERE digest_run_id IN (
              SELECT id FROM digest_runs WHERE digest_date < ?
            )
            """
        )
        .bind(digest_date_before)
        .run()
    )
    recommendations = await (
        db.prepare(
            """
            DELETE FROM recommendations
            WHERE digest_run_id IN (
              SELECT id FROM digest_runs WHERE digest_date < ?
            )
            """
        )
        .bind(digest_date_before)
        .run()
    )
    runs = await (
        db.prepare("DELETE FROM digest_runs WHERE digest_date < ?")
        .bind(digest_date_before)
        .run()
    )
    events = await (
        db.prepare(
            """
            DELETE FROM events
            WHERE last_seen_at < ?
              AND NOT EXISTS (
                SELECT 1 FROM recommendations
                WHERE recommendations.event_id = events.id
              )
            """
        )
        .bind(event_last_seen_before)
        .run()
    )
    return {
        "deliveries": result_changes(deliveries),
        "recommendations": result_changes(recommendations),
        "digest_runs": result_changes(runs),
        "events": result_changes(events),
    }
