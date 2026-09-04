import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from worker_collectors import collect_events, persist_events
from worker_email import deliver_digest, digest_message
from worker_ranking import rank_events
from worker_runtime import env_value
from worker_storage import (
    claim_delivery,
    clear_recommendations,
    delete_expired_auth,
    delete_expired_history,
    finish_digest_run,
    get_or_create_digest_run,
    list_active_subscribers,
    list_events_for_date,
    mark_delivery_failed,
    mark_delivery_sent,
    record_recommendation,
)
from worker_time import to_madrid


def log_event(event_name: str, correlation_id: str, **fields: Any) -> None:
    """Emit a structured event containing aggregate, non-sensitive fields."""
    print(
        json.dumps(
            {
                "event.name": event_name,
                "correlation.id": correlation_id,
                **fields,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _error_code(error: Exception) -> str:
    value = "_".join(str(error).strip().lower().split())
    return value[:64] if value else error.__class__.__name__.lower()[:64]


def _run_identity(digest_date: str, run_id: int) -> str:
    return hashlib.sha256(f"{digest_date}:{run_id}".encode()).hexdigest()[:16]


async def run_digest(
    env: Any,
    *,
    now: datetime | None = None,
    dry_run: bool = True,
    target_user_id: int | None = None,
) -> dict[str, Any]:
    """Collect once, then independently rank/render/deliver for subscribers."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    digest_date = (to_madrid(current).date() + timedelta(days=1)).isoformat()
    db = env_value(env, "DB")
    if db is None:
        raise RuntimeError("missing_d1_binding")

    run = await get_or_create_digest_run(
        db,
        digest_date=digest_date,
        scheduled_for=current.astimezone(UTC).isoformat(),
    )
    run_id = int(run["id"])
    correlation_id = _run_identity(digest_date, run_id)
    log_event(
        "digest.run.started",
        correlation_id,
        digest_date=digest_date,
        dry_run=dry_run,
        targeted=target_user_id is not None,
    )

    collector = env_value(env, "COLLECT_EVENTS", collect_events)
    collected, source_diagnostics = await collector(
        env, datetime.fromisoformat(digest_date).date()
    )
    await persist_events(db, collected)
    events = await list_events_for_date(db, digest_date)
    subscribers = await list_active_subscribers(db)
    if target_user_id is not None:
        subscribers = [
            subscriber
            for subscriber in subscribers
            if int(subscriber["id"]) == target_user_id
        ]

    summary: dict[str, Any] = {
        "correlation_id": correlation_id,
        "digest_date": digest_date,
        "dry_run": dry_run,
        "sources": source_diagnostics,
        "event_count": len(events),
        "subscriber_count": len(subscribers),
        "rendered_count": 0,
        "sent_count": 0,
        "skipped_count": 0,
        "failure_count": 0,
        "fallback_count": 0,
    }

    ranker = env_value(env, "RANK_EVENTS", rank_events)
    for subscriber in subscribers:
        user_id = int(subscriber["id"])
        claimed = False
        try:
            ranking = await ranker(env, subscriber.get("preferences_blob"), events)
            if ranking.used_fallback:
                summary["fallback_count"] += 1
            if not ranking.events:
                summary["skipped_count"] += 1
                continue

            await clear_recommendations(db, run_id, user_id)
            for position, event in enumerate(ranking.events, start=1):
                await record_recommendation(
                    db,
                    digest_run_id=run_id,
                    user_id=user_id,
                    event_id=int(event["id"]),
                    position=position,
                    relevance_reason=event["relevance_reason"],
                    model_id=ranking.model_id,
                    used_fallback=ranking.used_fallback,
                )

            if dry_run:
                digest_message(
                    subscriber["email"],
                    str(env_value(env, "EMAIL_FROM", "Brisa <dry-run@example.com>")),
                    str(
                        env_value(
                            env,
                            "APP_BASE_URL",
                            "https://valencia-event-notifications.pages.dev",
                        )
                    ),
                    digest_date,
                    ranking.events,
                )
                summary["rendered_count"] += 1
                continue

            claimed = await claim_delivery(db, run_id, user_id)
            if not claimed:
                summary["skipped_count"] += 1
                continue
            provider_id = await deliver_digest(
                env,
                subscriber["email"],
                digest_date,
                ranking.events,
            )
            if not await mark_delivery_sent(db, run_id, user_id, provider_id):
                raise RuntimeError("delivery_finalize_failed")
            summary["sent_count"] += 1
        except Exception as error:
            summary["failure_count"] += 1
            if claimed:
                await mark_delivery_failed(db, run_id, user_id, _error_code(error))
            log_event(
                "digest.subscriber.failed",
                correlation_id,
                error_code=_error_code(error),
            )

    failure_count = int(summary["failure_count"])
    successful_count = int(summary["rendered_count"]) + int(summary["sent_count"])
    status = (
        "completed"
        if failure_count == 0
        else "partial"
        if successful_count > 0
        else "failed"
    )
    await finish_digest_run(
        db,
        run_id,
        status=status,
        event_count=len(events),
        subscriber_count=len(subscribers),
        sent_count=int(summary["sent_count"]),
        failure_count=failure_count,
    )

    try:
        history_cutoff = (current.date() - timedelta(days=90)).isoformat()
        event_cutoff = (current - timedelta(days=30)).astimezone(UTC).isoformat()
        summary["cleanup"] = {
            **await delete_expired_history(
                db,
                digest_date_before=history_cutoff,
                event_last_seen_before=event_cutoff,
            ),
            **await delete_expired_auth(db),
        }
    except Exception as error:
        summary["cleanup"] = {"error_code": _error_code(error)}
        log_event(
            "digest.cleanup.failed",
            correlation_id,
            error_code=_error_code(error),
        )

    log_event(
        "digest.run.completed",
        correlation_id,
        status=status,
        dry_run=dry_run,
        event_count=summary["event_count"],
        subscriber_count=summary["subscriber_count"],
        sent_count=summary["sent_count"],
        failure_count=summary["failure_count"],
        fallback_count=summary["fallback_count"],
    )
    return summary
