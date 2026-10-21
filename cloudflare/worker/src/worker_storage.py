import hashlib
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from worker_runtime import to_python
from worker_time import localize_madrid, to_madrid

MAX_DELIVERY_ATTEMPTS = 3


def safe_event_url(value: Any) -> str | None:
    """Allow public HTTP links, never credential-bearing or ambiguous URLs."""
    if not isinstance(value, str) or not 1 <= len(value) <= 4096:
        return None
    try:
        if len(value.encode("utf-16-le")) > 8192:
            return None
    except UnicodeEncodeError:
        return None
    if re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return None
    try:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or "%" in parts.hostname
            or re.match(
                r"^/(?:api|account|login|signin|sign-in|verify|onboarding)(?:/|$)",
                parts.path,
                re.IGNORECASE,
            )
            or any(
                re.fullmatch(
                    r"token|access_token|auth|authorization|session|session_id|email|password|user_id|account_id|magic_link",
                    key,
                    re.IGNORECASE,
                )
                for key, _ in parse_qsl(parts.query, keep_blank_values=True)
            )
        ):
            return None
        _ = parts.port
    except ValueError:
        return None
    return urlunsplit(parts)


def public_text(value: Any, limit: int) -> str:
    """Bound by browser UTF-16 length and strip unsafe control characters."""
    if not isinstance(value, str):
        return ""
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value).strip()
    return value.encode("utf-16-le", errors="ignore")[: limit * 2].decode(
        "utf-16-le", errors="ignore"
    )


def public_event(event: dict[str, Any]) -> dict[str, Any]:
    """Project canonical public evidence without account or ranking data."""
    identifier = event.get("id")
    key = event.get("event_key")
    title = public_text(event.get("title"), 500)
    source = public_text(event.get("source"), 80)
    url = safe_event_url(event.get("url"))
    if (
        type(identifier) is not int
        or not 0 < identifier <= 9_007_199_254_740_991
        or not isinstance(key, str)
        or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key)
        or not title
        or not source
        or url is None
    ):
        raise ValueError("invalid_event")
    try:
        start = datetime.fromisoformat(event["start_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid_event") from exc
    precision = event.get("time_precision", "unverified")
    if precision not in {"date", "datetime", "unverified"}:
        precision = "unverified"
    if start.tzinfo is None:
        start = localize_madrid(start)
        precision = "unverified"
    try:
        start = to_madrid(start)
    except (OverflowError, ValueError) as exc:
        raise ValueError("invalid_event") from exc
    end = None
    if event.get("end_at"):
        try:
            candidate = datetime.fromisoformat(event["end_at"])
            if candidate.tzinfo is not None and candidate > start:
                end = to_madrid(candidate).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass

    return {
        "id": identifier,
        "event_key": key,
        "title": title,
        "url": url,
        "start_at": start.isoformat(),
        "end_at": end,
        "time_precision": precision,
        "location": public_text(event.get("location"), 500),
        "description": public_text(event.get("description"), 8000),
        "source": source,
    }


def _nullable_d1_value(value: Any) -> Any:
    """Bind SQL NULL explicitly: Pyodide turns Python None into JS undefined."""
    if value is not None:
        return value
    try:
        from pyodide.ffi import jsnull  # type: ignore[import-not-found]
    except ImportError:  # CPython's offline SQLite adapter accepts None directly.
        return None
    return jsnull


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


async def get_preview_user(db: Any, user_id: int) -> dict[str, Any] | None:
    """An authenticated active user can preview while delivery is paused."""
    result = to_python(
        await db.prepare(
            "SELECT id, email, preferences_blob FROM users "
            "WHERE id = ? AND is_active = 1"
        )
        .bind(user_id)
        .first()
    )
    return result if isinstance(result, dict) else None


async def list_events_for_date(db: Any, digest_date: str) -> list[dict[str, Any]]:
    """Return normalized events whose local ISO timestamp starts on a date."""
    result = await (
        db.prepare(
            """
            SELECT id, event_key, title, start_at, end_at, time_precision,
                   location, url, description, source
            FROM events
            WHERE substr(start_at, 1, 10) = ?
            ORDER BY start_at, title, event_key
            """
        )
        .bind(digest_date)
        .all()
    )
    return result_rows(result)


async def list_events_by_keys(db: Any, keys: list[str]) -> list[dict[str, Any]]:
    """Return the exact unique event batch selected by the collectors."""
    unique_keys = sorted(set(keys))
    if not unique_keys:
        return []

    placeholders = ", ".join("?" for _ in unique_keys)
    result = await (
        db.prepare(
            f"""
            SELECT id, event_key, title, start_at, end_at, time_precision,
                   location, url, description, source
            FROM events
            WHERE event_key IN ({placeholders})
            ORDER BY start_at, title, event_key
            """
        )
        .bind(*unique_keys)
        .all()
    )
    return result_rows(result)


async def upsert_event(
    db: Any,
    *,
    title: str,
    start_at: str,
    url: str,
    description: str,
    source: str,
    end_at: str | None = None,
    time_precision: str = "unverified",
    location: str = "",
) -> str:
    """Insert a normalized event or refresh its mutable source fields."""
    key = event_key(title, start_at, url)
    await (
        db.prepare(
            """
            INSERT INTO events (
              event_key, title, start_at, url, description, source,
              end_at, time_precision, location
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_key) DO UPDATE SET
              description = excluded.description,
              source = excluded.source,
              end_at = excluded.end_at,
              time_precision = excluded.time_precision,
              location = excluded.location,
              last_seen_at = CURRENT_TIMESTAMP
            """
        )
        .bind(
            key,
            title,
            start_at,
            url,
            description,
            source,
            _nullable_d1_value(end_at or None),
            time_precision,
            location,
        )
        .run()
    )
    return key


async def record_source_checks(
    db: Any, checked_date: str, sources: list[dict[str, Any]]
) -> None:
    """Store public collection evidence, independent of the requesting account."""
    for source in sources:
        await (
            db.prepare(
                """
                INSERT INTO source_checks (
                  checked_date, source, status, fetched_count, event_count,
                  checked_at, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """
            )
            .bind(
                checked_date,
                source["name"],
                source["status"],
                source["fetched_count"],
                source["event_count"],
                source["checked_at"],
                _nullable_d1_value(
                    "source_unavailable" if source["status"] == "error" else None
                ),
            )
            .run()
        )


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


async def clear_recommendations(db: Any, digest_run_id: int, user_id: int) -> None:
    """Clear a user's provisional ranking before replacing it on a retry."""
    await (
        db.prepare(
            "DELETE FROM recommendations WHERE digest_run_id = ? AND user_id = ?"
        )
        .bind(digest_run_id, user_id)
        .run()
    )


async def load_jev_answers(db: Any, cache_key: str, model: str) -> dict[str, Any]:
    """Read only identity-free answers with the exact content and model key."""
    result = await (
        db.prepare(
            """
            SELECT question_id, p_yes FROM jev_answer_cache
            WHERE cache_key = ? AND model = ?
              AND datetime(created_at) >= datetime('now', '-90 days')
            """
        )
        .bind(cache_key, model)
        .all()
    )
    return {
        row["question_id"]: {"type": "noul", "noul": row["p_yes"]}
        for row in result_rows(result)
    }


async def save_jev_answers(
    db: Any, cache_key: str, model: str, answers: dict[str, Any]
) -> None:
    for question_id, answer in answers.items():
        await (
            db.prepare(
                """
                INSERT INTO jev_answer_cache (cache_key, question_id, model, p_yes)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key, question_id) DO UPDATE SET
                  model = excluded.model,
                  p_yes = excluded.p_yes,
                  created_at = CURRENT_TIMESTAMP
                """
            )
            .bind(cache_key, question_id, model, answer["noul"])
            .run()
        )


async def record_jev_evaluation(
    db: Any,
    *,
    digest_run_id: int,
    user_id: int,
    event_id: int,
    evaluation: dict[str, Any],
) -> None:
    """Keep private, append-only provenance for included and rejected events."""
    await (
        db.prepare(
            """
            INSERT INTO jev_evaluations (
              digest_run_id, user_id, event_id, selected_event_types,
              taxonomy_version, question_version, scoring_version, model,
              components, threshold, irrelevance_score, decision, status,
              error_code, evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        )
        .bind(
            digest_run_id,
            user_id,
            event_id,
            json.dumps(evaluation["selected_event_types"]),
            evaluation["taxonomy_version"],
            evaluation["question_version"],
            evaluation["scoring_version"],
            _nullable_d1_value(evaluation["model"]),
            json.dumps(evaluation["components"], allow_nan=False),
            evaluation["threshold"],
            _nullable_d1_value(evaluation["irrelevance_score"]),
            evaluation["decision"],
            evaluation["status"],
            _nullable_d1_value(evaluation["error_code"]),
            evaluation["evaluated_at"],
        )
        .run()
    )


async def finish_digest_run(
    db: Any,
    digest_run_id: int,
    *,
    status: str,
    event_count: int,
    subscriber_count: int,
    sent_count: int,
    failure_count: int,
) -> None:
    """Record aggregate completion state without subscriber data."""
    if status not in {"completed", "partial", "failed"}:
        raise ValueError("invalid digest run status")
    await (
        db.prepare(
            """
            UPDATE digest_runs
            SET status = ?,
                event_count = ?,
                subscriber_count = ?,
                sent_count = ?,
                failure_count = ?,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """
        )
        .bind(
            status,
            event_count,
            subscriber_count,
            sent_count,
            failure_count,
            digest_run_id,
        )
        .run()
    )


async def claim_delivery(db: Any, digest_run_id: int, user_id: int) -> bool:
    """Claim a send once, applying bounded backoff to failed deliveries."""
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
              AND deliveries.attempt_count < ?
              AND datetime(deliveries.updated_at) <= datetime(
                'now',
                CASE deliveries.attempt_count
                  WHEN 1 THEN '-5 minutes'
                  ELSE '-15 minutes'
                END
              )
            """
        )
        .bind(digest_run_id, user_id, MAX_DELIVERY_ATTEMPTS)
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
        .bind(_nullable_d1_value(provider_message_id), digest_run_id, user_id)
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
    """Delete old private history, followed by now-unreferenced events."""
    await (
        db.prepare(
            """
            DELETE FROM jev_evaluations
            WHERE digest_run_id IN (
              SELECT id FROM digest_runs WHERE digest_date < ?
            )
            """
        )
        .bind(digest_date_before)
        .run()
    )
    await db.prepare(
        "DELETE FROM jev_answer_cache "
        "WHERE datetime(created_at) < datetime('now', '-90 days')"
    ).run()
    await (
        db.prepare("DELETE FROM source_checks WHERE checked_date < ?")
        .bind(digest_date_before)
        .run()
    )
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
              AND NOT EXISTS (
                SELECT 1 FROM jev_evaluations
                WHERE jev_evaluations.event_id = events.id
              )
              AND NOT EXISTS (
                SELECT 1 FROM saved_events
                WHERE saved_events.event_id = events.id
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


async def delete_expired_auth(db: Any) -> dict[str, int]:
    """Remove expired auth records without touching active accounts."""
    sessions = await db.prepare(
        "DELETE FROM sessions WHERE expires_at <= CURRENT_TIMESTAMP"
    ).run()
    magic_links = await db.prepare(
        """
        DELETE FROM magic_links
        WHERE expires_at <= CURRENT_TIMESTAMP OR consumed_at IS NOT NULL
        """
    ).run()
    return {
        "sessions": result_changes(sessions),
        "magic_links": result_changes(magic_links),
    }
