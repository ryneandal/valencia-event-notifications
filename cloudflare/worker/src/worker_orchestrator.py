import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from worker_collectors import collect_events, persist_events
from worker_email import deliver_digest, digest_message
from worker_jev import fallback_evaluation, jev_mode, selected_types
from worker_planning import cleanup_planning, delivery_allowed
from worker_ranking import rank_events
from worker_runtime import env_value
from worker_storage import (
    claim_delivery,
    clear_recommendations,
    delete_expired_auth,
    delete_expired_history,
    finish_digest_run,
    get_or_create_digest_run,
    get_preview_user,
    list_active_subscribers,
    list_events_by_keys,
    mark_delivery_failed,
    mark_delivery_sent,
    public_event,
    public_text,
    record_jev_evaluation,
    record_recommendation,
    record_source_checks,
)
from worker_time import validate_preview_date


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


def _coverage(
    diagnostics: list[dict[str, Any]], checked_at: str, collected_count: int
) -> dict[str, Any]:
    sources = []
    for diagnostic in diagnostics[:32]:
        name = diagnostic.get("source", "source")
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", name):
            name = "source"
        status = "ok" if diagnostic.get("status") == "ok" else "error"
        timestamp = diagnostic.get("checked_at", checked_at)
        try:
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None:
                raise ValueError("missing_offset")
            timestamp = parsed.isoformat()
        except (TypeError, ValueError):
            timestamp = checked_at

        def count(field: str) -> int:
            value = diagnostic.get(field, 0)
            return min(value, 1_000_000) if type(value) is int and value >= 0 else 0

        sources.append(
            {
                "name": name,
                "status": status,
                "fetched_count": count("parsed") if status == "ok" else 0,
                "event_count": count("matched") if status == "ok" else 0,
                "checked_at": timestamp,
            }
        )
    successes = sum(source["status"] == "ok" for source in sources)
    return {
        "state": "unavailable"
        if not successes
        else "complete"
        if successes == len(sources)
        else "partial",
        "collected_count": collected_count,
        "sources": sources,
    }


async def run_digest(
    env: Any,
    *,
    now: datetime | None = None,
    dry_run: bool = True,
    target_user_id: int | None = None,
    target_date: str | None = None,
) -> dict[str, Any]:
    """Collect once, then independently rank/render/deliver for subscribers."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    if target_date is not None and not dry_run:
        raise ValueError("Selected dates are available for previews only.")
    digest_date = validate_preview_date(target_date, current)
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
    collected_keys = await persist_events(db, collected)
    events = await list_events_by_keys(db, collected_keys)
    checked_at = current.astimezone(UTC).isoformat()
    coverage = _coverage(source_diagnostics, checked_at, len(events))
    source_diagnostics = [
        {
            "source": item["name"],
            "status": "ok" if item["status"] == "ok" else "failed",
            "parsed": item["fetched_count"],
            "matched": item["event_count"],
            "checked_at": item["checked_at"],
            **(
                {"error_code": "source_unavailable"}
                if item["status"] == "error"
                else {}
            ),
        }
        for item in coverage["sources"]
    ]
    for diagnostic in source_diagnostics:
        log_event("digest.source.completed", correlation_id, **diagnostic)
    await record_source_checks(db, digest_date, coverage["sources"])
    if dry_run and target_user_id is not None:
        target = await get_preview_user(db, target_user_id)
        subscribers = [target] if target else []
    else:
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
        "fallback_reasons": {},
    }

    ranker = env_value(env, "RANK_EVENTS", rank_events)
    preview_evaluations: list[dict[str, Any]] = []
    plans: dict[str, Any] = {
        "version": "brisa-plans-v1",
        "date": digest_date,
        "checked_at": checked_at,
        "delivery_enabled": str(
            env_value(env, "DIGEST_DELIVERY_ENABLED", "false")
        ).lower()
        in {"1", "true", "yes"},
        "coverage": coverage,
        "recommendations": [],
        "excluded_count": 0,
    }
    event_ids = {event["event_key"]: int(event["id"]) for event in events}
    for subscriber in subscribers:
        user_id = int(subscriber["id"])
        claimed = False
        try:
            if not (
                dry_run and target_user_id is not None
            ) and not await delivery_allowed(db, user_id, digest_date):
                summary["skipped_count"] += 1
                continue
            ranking = await ranker(env, subscriber.get("preferences_blob"), events)
            evaluations = ranking.evaluations
            for evaluation in evaluations:
                await record_jev_evaluation(
                    db,
                    digest_run_id=run_id,
                    user_id=user_id,
                    event_id=event_ids[evaluation["event"]["event_key"]],
                    evaluation=evaluation,
                )
            if dry_run and target_user_id == user_id:
                preview_evaluations = evaluations or [
                    fallback_evaluation(
                        event,
                        selected_types(subscriber.get("preferences_blob")),
                        "feature_disabled",
                    )
                    for event in events
                ]
                decisions = {
                    item["event"]["event_key"]: item["decision"] for item in evaluations
                }
                recommendations = []
                for event in ranking.events[:100]:
                    try:
                        public = public_event(event)
                    except ValueError:
                        continue
                    reason = event.get("relevance_reason", "")
                    decision = decisions.get(event["event_key"], "unknown")
                    recommendations.append(
                        {
                            **public,
                            "position": len(recommendations) + 1,
                            "reason": public_text(reason, 180)
                            or "Suggested from your saved choices.",
                            "used_fallback": bool(ranking.used_fallback),
                            "type_decision": decision
                            if decision in {"eligible", "irrelevant", "unknown"}
                            else "unknown",
                        }
                    )
                plans["recommendations"] = recommendations
                if jev_mode(env) == "filter":
                    plans["excluded_count"] = sum(
                        item["status"] == "evaluated"
                        and item["decision"] == "irrelevant"
                        for item in evaluations
                    )
            if evaluations:
                log_event(
                    "digest.jev.completed",
                    correlation_id,
                    evaluation_count=len(evaluations),
                    duration_ms=ranking.evaluation_duration_ms,
                    fallback_count=sum(
                        item["status"] == "fallback" for item in evaluations
                    ),
                    irrelevant_count=sum(
                        item["decision"] == "irrelevant" for item in evaluations
                    ),
                )
            if ranking.used_fallback:
                summary["fallback_count"] += 1
                error_code = ranking.error_code or "no_candidates"
                fallback_reasons = summary["fallback_reasons"]
                fallback_reasons[error_code] = fallback_reasons.get(error_code, 0) + 1
                log_event(
                    "digest.ranking.fallback",
                    correlation_id,
                    error_code=error_code,
                )
            await clear_recommendations(db, run_id, user_id)
            if not ranking.events:
                summary["skipped_count"] += 1
                continue

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
            **await cleanup_planning(db),
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
    if dry_run and target_user_id is not None:
        return {
            "contract_version": "jev-preview-v1",
            "summary": summary,
            "evaluations": preview_evaluations,
            "plans": plans,
        }
    return summary
