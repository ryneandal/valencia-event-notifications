"""Private account planning controls; public event evidence stays separate."""

import json
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from worker_http import AppResponse, json_response
from worker_runtime import env_value, request_json, to_python
from worker_storage import (
    _nullable_d1_value,
    public_event,
    result_changes,
    result_rows,
)
from worker_time import available_preview_dates, to_madrid, validate_preview_date

ALL_DAYS = list(range(7))


async def _first(db: Any, sql: str, *params: Any) -> dict[str, Any] | None:
    return to_python(await db.prepare(sql).bind(*params).first())


async def saved_events(db: Any, user_id: int) -> list[dict[str, Any]]:
    rows = result_rows(
        await db.prepare(
            "SELECT e.* FROM saved_events s JOIN events e ON e.id = s.event_id "
            "WHERE s.user_id = ? ORDER BY e.start_at, e.id LIMIT 50"
        )
        .bind(user_id)
        .all()
    )
    events = []
    for row in rows:
        try:
            events.append(public_event(row))
        except ValueError:
            continue  # Legacy unsafe records are never exposed as links.
    return events


async def delivery_days(db: Any, user_id: int) -> list[int]:
    row = await _first(
        db, "SELECT days FROM delivery_preferences WHERE user_id = ?", user_id
    )
    return json.loads(row["days"]) if row else ALL_DAYS.copy()


async def delivery_allowed(db: Any, user_id: int, digest_date: str) -> bool:
    """Days describe the event day, not the preceding day when mail is sent."""
    return date.fromisoformat(digest_date).weekday() in await delivery_days(db, user_id)


async def cleanup_planning(db: Any) -> dict[str, int]:
    feedback = await db.prepare(
        "DELETE FROM pilot_feedback "
        "WHERE julianday(created_at) <= julianday('now','-30 days') "
        "OR study_code IN (SELECT study_code FROM pilot_participants "
        "WHERE julianday(expires_at) <= julianday('now'))"
    ).run()
    links = await db.prepare(
        "DELETE FROM pilot_participants WHERE julianday(expires_at) <= julianday('now')"
    ).run()
    return {
        "pilot_feedback": result_changes(feedback),
        "pilot_participants": result_changes(links),
    }


async def _pilot(db: Any, user_id: int) -> dict[str, Any]:
    row = await _first(
        db,
        "SELECT expires_at FROM pilot_participants WHERE user_id = ? "
        "AND julianday(expires_at) > julianday('now')",
        user_id,
    )
    return {"consented": bool(row), "expires_at": row["expires_at"] if row else None}


async def handle_planning_request(
    env: Any, request: Any, user: dict[str, Any], path: str, method: str
) -> AppResponse:
    db, user_id = env_value(env, "DB"), int(user["id"])
    if path == "/api/planning" and method == "GET":
        await cleanup_planning(db)
        subscription = await _first(
            db, "SELECT is_subscribed FROM subscriptions WHERE user_id = ?", user_id
        )
        history = result_rows(
            await db.prepare(
                "SELECT checked_date, source, status, fetched_count, "
                "event_count, checked_at FROM source_checks "
                "WHERE julianday(checked_at) >= julianday('now','-14 days') "
                "ORDER BY checked_at DESC, id DESC LIMIT 40"
            ).all()
        )
        return json_response(
            {
                "version": "brisa-planning-v1",
                "today": to_madrid(datetime.now(UTC)).date().isoformat(),
                "available_dates": available_preview_dates(),
                "delivery_enabled": str(
                    env_value(env, "DIGEST_DELIVERY_ENABLED", "false")
                )
                .strip()
                .lower()
                in {"1", "true", "yes"},
                "delivery_days": await delivery_days(db, user_id),
                "subscribed": bool(subscription["is_subscribed"])
                if subscription
                else True,
                "saved_events": await saved_events(db, user_id),
                "pilot": await _pilot(db, user_id),
                "coverage_history": history,
            }
        )

    allowed = {
        ("/api/planning/delivery", "PATCH"),
        ("/api/planning/saved", "POST"),
        ("/api/planning/saved", "DELETE"),
        ("/api/planning/pilot", "PUT"),
        ("/api/planning/feedback", "POST"),
    }
    if (path, method) not in allowed:
        return json_response({"error": "Not found"}, 404)
    try:
        payload = await request_json(request)
    except Exception:
        return json_response({"error": "Invalid JSON payload"}, 400)

    if path.endswith("/delivery"):
        days, subscribed = payload.get("days"), payload.get("subscribed")
        if (
            not isinstance(days, list)
            or len(days) > 7
            or any(type(day) is not int or day not in ALL_DAYS for day in days)
            or len(set(days)) != len(days)
            or type(subscribed) is not bool
            or (subscribed and not days)
        ):
            return json_response(
                {
                    "error": "Choose unique weekdays, and at least one day "
                    "for an active digest."
                },
                422,
            )
        days = sorted(days)
        await (
            db.prepare(
                "INSERT INTO delivery_preferences(user_id,days) VALUES (?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET days=excluded.days, "
                "updated_at=CURRENT_TIMESTAMP"
            )
            .bind(user_id, json.dumps(days))
            .run()
        )
        await (
            db.prepare(
                "INSERT INTO subscriptions(user_id,is_subscribed) VALUES (?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "is_subscribed=excluded.is_subscribed, updated_at=CURRENT_TIMESTAMP"
            )
            .bind(user_id, int(subscribed))
            .run()
        )
        return json_response({"delivery_days": days, "subscribed": subscribed})

    if path.endswith("/saved"):
        event_id = payload.get("event_id")
        if type(event_id) is not int or not 0 < event_id <= 9_007_199_254_740_991:
            return json_response({"error": "Invalid event"}, 422)
        if method == "DELETE":
            await (
                db.prepare("DELETE FROM saved_events WHERE user_id=? AND event_id=?")
                .bind(user_id, event_id)
                .run()
            )
        else:
            event = await _first(db, "SELECT * FROM events WHERE id=?", event_id)
            try:
                public_event(event or {})
            except ValueError:
                return json_response({"error": "Event is no longer available"}, 404)
            # One statement keeps the cap safe when two requests arrive together.
            await (
                db.prepare(
                    "INSERT OR IGNORE INTO saved_events(user_id,event_id) SELECT ?,? "
                    "WHERE (SELECT COUNT(*) FROM saved_events WHERE user_id=?) < 50"
                )
                .bind(user_id, event_id, user_id)
                .run()
            )
            if not await _first(
                db,
                "SELECT event_id FROM saved_events WHERE user_id=? AND event_id=?",
                user_id,
                event_id,
            ):
                return json_response(
                    {"error": "Your shortlist is full. Remove a saved event first."},
                    409,
                )
        return json_response({"saved_events": await saved_events(db, user_id)})

    if path.endswith("/pilot"):
        consented = payload.get("consented")
        if type(consented) is not bool:
            return json_response({"error": "Consent must be an explicit choice"}, 422)
        await cleanup_planning(db)
        if consented:
            expires = (datetime.now(UTC) + timedelta(days=30)).isoformat()
            await (
                db.prepare(
                    "INSERT OR IGNORE INTO pilot_participants"
                    "(user_id,study_code,expires_at) VALUES (?,?,?)"
                )
                .bind(user_id, secrets.token_hex(16), expires)
                .run()
            )
        else:
            await (
                db.prepare("DELETE FROM pilot_participants WHERE user_id=?")
                .bind(user_id)
                .run()
            )
        return json_response({"pilot": await _pilot(db, user_id)})

    if path.endswith("/feedback"):
        useful, action, state = (
            payload.get("useful"),
            payload.get("action"),
            payload.get("result_state"),
        )
        try:
            if not isinstance(payload.get("date"), str):
                raise ValueError("missing_date")
            preview_date = validate_preview_date(payload["date"])
            if (
                state
                not in {
                    "recommendations",
                    "empty",
                    "filtered",
                    "partial",
                    "unavailable",
                }
                or (useful is not None and type(useful) is not bool)
                or action not in {None, "organizer", "save", "copy", "calendar"}
                or (useful is None and action is None)
            ):
                raise ValueError("invalid_feedback")
        except (ValueError, TypeError):
            return json_response({"error": "Invalid feedback"}, 422)
        result = (
            await db.prepare(
                "INSERT INTO pilot_feedback"
                "(study_code,preview_date,result_state,useful,action) "
                "SELECT p.study_code,?,?,?,? FROM pilot_participants p "
                "WHERE p.user_id=? "
                "AND julianday(p.expires_at)>julianday('now') "
                "AND (SELECT COUNT(*) FROM pilot_feedback f "
                "WHERE f.study_code=p.study_code)<500"
            )
            .bind(
                preview_date,
                state,
                _nullable_d1_value(int(useful) if useful is not None else None),
                _nullable_d1_value(action),
                user_id,
            )
            .run()
        )
        if not result_changes(result):
            return json_response(
                {
                    "error": "Feedback participation is unavailable. "
                    "Check your consent settings."
                },
                403,
            )
        return json_response({"ok": True})
    return json_response({"error": "Not found"}, 404)
